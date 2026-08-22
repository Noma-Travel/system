#!/usr/bin/env python3
"""
One-shot: re-point EventBridge HTTPS targets from POST/_schd/ping to POST/v1/cron/ping.

Usage (staging credentials):
  python system/scripts/migrate_eventbridge_cron_ping.py --dry-run
  python system/scripts/migrate_eventbridge_cron_ping.py --apply

Requires AWS credentials with events:ListRules, events:ListTargetsByRule,
events:PutTargets.
"""

from __future__ import annotations

import argparse
import sys

import boto3

OLD_SUFFIX = '/POST/_schd/ping'
NEW_SUFFIX = '/POST/v1/cron/ping'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write PutTargets (default is dry-run)')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    dry_run = not args.apply

    client = boto3.client('events', region_name=args.region)
    updated = 0
    scanned = 0

    paginator = client.get_paginator('list_rules')
    for page in paginator.paginate():
        for rule in page.get('Rules', []):
            name = rule['Name']
            scanned += 1
            targets = client.list_targets_by_rule(Rule=name).get('Targets', [])
            changed = []
            for target in targets:
                arn = target.get('Arn') or ''
                if OLD_SUFFIX not in arn:
                    continue
                new_target = dict(target)
                new_target['Arn'] = arn.replace(OLD_SUFFIX, NEW_SUFFIX)
                changed.append(new_target)
            if not changed:
                continue
            print(f'{name}: {len(changed)} target(s)')
            for t in changed:
                print(f'  -> {t["Arn"]}')
            if dry_run:
                continue
            resp = client.put_targets(Rule=name, Targets=changed)
            if resp.get('FailedEntryCount', 0):
                print(f'  FAILED: {resp.get("FailedEntries")}', file=sys.stderr)
                return 1
            updated += 1

    mode = 'dry-run' if dry_run else 'applied'
    print(f'Done ({mode}): scanned={scanned} rules_updated={updated}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
