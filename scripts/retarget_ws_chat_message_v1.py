#!/usr/bin/env python3
"""
Retarget API Gateway WebSocket `chat_message` HTTP integration to `/v1/chat/message`.

Z6 PR E — run AFTER the product Lambda serves POST /v1/chat/message (401 without
auth is fine; 404 means abort).

Staging defaults:
  API id: 1qefn6vt95
  REST:   https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging

Usage:
  python scripts/retarget_ws_chat_message_v1.py
  python scripts/retarget_ws_chat_message_v1.py --api-id 1qefn6vt95 --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_API_ID = "1qefn6vt95"
DEFAULT_REGION = "us-east-1"
DEFAULT_REST_BASE = (
    "https://2r4dlx8qdj.execute-api.us-east-1.amazonaws.com/noma_staging"
)
ROUTE_KEY = "chat_message"
NEW_SUFFIX = "/v1/chat/message"
OLD_SUFFIX = "/_chat/message"


def aws_json(args: list[str]) -> dict:
    raw = subprocess.check_output(["aws", *args, "--output", "json"], text=True)
    return json.loads(raw)


def probe(url: str) -> int:
    req = urllib.request.Request(
        url, data=b"{}", method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api-id", default=DEFAULT_API_ID)
    p.add_argument("--region", default=DEFAULT_REGION)
    p.add_argument("--rest-base", default=DEFAULT_REST_BASE)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Skip 404 probe gate")
    args = p.parse_args()

    new_uri = args.rest_base.rstrip("/") + NEW_SUFFIX
    code = probe(new_uri)
    print(f"probe POST {new_uri} -> {code}")
    if code == 404 and not args.force:
        print(
            "ABORT: /v1/chat/message is 404 — deploy backend wrappers before retarget.",
            file=sys.stderr,
        )
        return 2
    if code not in (200, 400, 401, 403, 422, 500) and not args.force:
        print(f"ABORT: unexpected probe status {code}", file=sys.stderr)
        return 2

    routes = aws_json(
        [
            "apigatewayv2",
            "get-routes",
            "--api-id",
            args.api_id,
            "--region",
            args.region,
        ]
    )
    route = next((r for r in routes.get("Items", []) if r.get("RouteKey") == ROUTE_KEY), None)
    if not route:
        print(f"ABORT: route {ROUTE_KEY} not found", file=sys.stderr)
        return 1
    target = route.get("Target") or ""
    if not target.startswith("integrations/"):
        print(f"ABORT: unexpected Target {target!r}", file=sys.stderr)
        return 1
    integration_id = target.split("/", 1)[1]

    integ = aws_json(
        [
            "apigatewayv2",
            "get-integration",
            "--api-id",
            args.api_id,
            "--integration-id",
            integration_id,
            "--region",
            args.region,
        ]
    )
    old_uri = integ.get("IntegrationUri") or ""
    print(f"current IntegrationUri={old_uri}")
    print(f"new      IntegrationUri={new_uri}")
    if old_uri.rstrip("/") == new_uri.rstrip("/"):
        print("already pointed at /v1/chat/message — nothing to do")
        return 0
    if OLD_SUFFIX not in old_uri and NEW_SUFFIX not in old_uri:
        print(f"ABORT: current URI does not look like chat message: {old_uri}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("dry-run: would update-integration")
        return 0

    subprocess.check_call(
        [
            "aws",
            "apigatewayv2",
            "update-integration",
            "--api-id",
            args.api_id,
            "--integration-id",
            integration_id,
            "--integration-uri",
            new_uri,
            "--region",
            args.region,
        ]
    )
    verify = aws_json(
        [
            "apigatewayv2",
            "get-integration",
            "--api-id",
            args.api_id,
            "--integration-id",
            integration_id,
            "--region",
            args.region,
        ]
    )
    print(f"updated IntegrationUri={verify.get('IntegrationUri')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
