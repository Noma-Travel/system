#!/usr/bin/env python3
"""
Seed a synthetic trip that is already pending purchase approval.

Bypasses Rextur flight search so Lembretes / email / approve-deny can be tested
when the flight gateway DNS is down.

Usage (from C:\\Noma\\system, with AWS_PROFILE=noma):
  .\\venv\\Scripts\\python.exe scripts\\seed_pending_approval_trip.py \\
    --portfolio 3649c943c0ae --org 4bf37c7c99f1 \\
    --traveler-email 2015antonioj@gmail.com
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

system_dir = Path(__file__).resolve().parents[1]
root = system_dir.parent
for rel in (
    "extensions/backend/package",
    "dev/renglo-api",
    "dev/renglo-lib",
    str(system_dir),
):
    p = str(root / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("AWS_PROFILE", "noma")


def _fields(item: dict) -> dict:
    attrs = item.get("attributes")
    return attrs if isinstance(attrs, dict) else item


def find_attendant(DAC, portfolio: str, org: str, email: str) -> dict | None:
    response = DAC.get_a_b(portfolio, org, "noma_attendants", limit=1000)
    items = (response or {}).get("items") or []
    wanted = email.strip().lower()
    for row in items:
        f = _fields(row)
        if str(f.get("email") or "").strip().lower() == wanted:
            return {**f, "_id": row.get("_id") or f.get("_id")}
    return None


def build_trip(owner_user_id: str, traveler: dict) -> dict:
    outbound = (date.today() + timedelta(days=14)).isoformat()
    trip_id = f"approval-seed-{uuid.uuid4().hex[:10]}"
    flights = [
        {
            "search_key": f"approval-seed-{outbound}",
            "legs_params": [{"origin": "GIG", "destination": "GRU", "date": outbound}],
            "ages": [30],
            "total_legs": 1,
            "flights": [
                {
                    "departure_airport": {
                        "id": "GIG",
                        "name": "Galeão",
                        "time": f"{outbound}T08:00:00",
                    },
                    "arrival_airport": {
                        "id": "GRU",
                        "name": "Guarulhos",
                        "time": f"{outbound}T09:05:00",
                    },
                    "airline": "GOL",
                    "flight_number": "G31234",
                    "duration": 65,
                }
            ],
            "price": 420,
            "currency": "BRL",
        }
    ]
    travelers = [
        {
            "id": traveler.get("_id") or traveler.get("user_id"),
            "name": traveler.get("name") or "Traveler",
            "email": traveler.get("email"),
        }
    ]
    trip = {
        "_id": trip_id,
        "title": f"GIG→GRU ({outbound})",
        "status": "pending_approval",
        "approval_status": "pending",
        "approval_requested_at": datetime.now(timezone.utc).isoformat(),
        "approval_previous_status": "pending",
        "approval_requested_by": owner_user_id,
        "travelers": travelers,
        "flights": flights,
        "hotels": [],
        "ground_transportation": [],
        "owner_user_id": owner_user_id,
        "startDate": outbound,
        "endDate": outbound,
        "totalPrice": 420,
        "currency": "BRL",
    }
    # Must match purchase_approval.approval_snapshot_hash
    from noma.utilities.purchase_approval import approval_snapshot_hash

    trip["approval_snapshot_hash"] = approval_snapshot_hash(trip)
    return trip


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a pending-approval trip for QA")
    parser.add_argument("--portfolio", default="3649c943c0ae")
    parser.add_argument("--org", default="4bf37c7c99f1")
    parser.add_argument("--traveler-email", default="2015antonioj@gmail.com")
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Also send approval emails to org admins (requires RESEND_API_KEY)",
    )
    args = parser.parse_args()

    def _run() -> int:
        from renglo.common import load_config
        from renglo.data.data_controller import DataController
        from noma.utilities.purchase_approval_email import notify_approvers_of_pending_purchase

        config = load_config()
        DAC = DataController(config=config)

        attendant = find_attendant(DAC, args.portfolio, args.org, args.traveler_email)
        if not attendant:
            print(f"ERROR: no attendant for {args.traveler_email} in org {args.org}")
            return 1

        owner_user_id = str(attendant.get("user_id") or "").strip()
        if not owner_user_id:
            print("ERROR: attendant has no user_id")
            return 1

        trip = build_trip(owner_user_id, attendant)
        trip_id = trip["_id"]
        create_payload = {k: v for k, v in trip.items() if k != "_id"}
        created = DAC.post_a_b(args.portfolio, args.org, "noma_travels", create_payload)
        if isinstance(created, tuple):
            created = created[0]
        new_id = None
        if isinstance(created, dict):
            new_id = (
                created.get("_id")
                or (created.get("item") or {}).get("_id")
                or (created.get("document") or {}).get("_id")
            )
            if not created.get("success") and not new_id:
                print("ERROR creating trip:", json.dumps(created, default=str)[:800])
                return 1

        if new_id and new_id != trip_id:
            trip_id = str(new_id)
            trip["_id"] = trip_id

        put_body = {
            "status": "pending_approval",
            "approval_status": "pending",
            "approval_requested_at": trip["approval_requested_at"],
            "approval_previous_status": "pending",
            "approval_requested_by": owner_user_id,
            "approval_snapshot_hash": trip["approval_snapshot_hash"],
            "title": trip["title"],
            "owner_user_id": owner_user_id,
            "travelers": trip["travelers"],
            "flights": trip["flights"],
            "totalPrice": trip["totalPrice"],
            "currency": "BRL",
            "startDate": trip["startDate"],
            "endDate": trip["endDate"],
        }
        resp, status = DAC.put_a_b_c(
            args.portfolio, args.org, "noma_travels", trip_id, put_body
        )
        if not resp.get("success") and status != 200:
            print("ERROR updating trip approval fields:", resp)
            return 1

        print("Created pending-approval trip:")
        print(f"  trip_id={trip_id}")
        print(f"  title={trip['title']}")
        print(f"  owner_user_id={owner_user_id}")
        print(f"  traveler={args.traveler_email}")
        print("Log in as org admin (amachadojardim@gmail.com) → Lembretes to approve/deny.")

        if args.notify:
            mail = notify_approvers_of_pending_purchase(
                config, DAC, args.portfolio, args.org, {**trip, **put_body}, trip_id
            )
            print("Email notify:", mail)

        return 0

    try:
        from flask import Flask
    except ImportError:
        return _run()
    app = Flask(__name__)
    app.config.setdefault("BASE_URL", os.environ.get("BASE_URL", "http://127.0.0.1:3000"))
    with app.app_context():
        return _run()


if __name__ == "__main__":
    raise SystemExit(main())
