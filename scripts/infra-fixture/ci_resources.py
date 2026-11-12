#!/usr/bin/env python3
"""Own and reclaim only Infra's disposable CI Docker fixtures.

Run cleanup in the workflow's always() step. The bounded pre-job sweep recovers
interrupted older runs, including pre-label fixtures from issue #776. No global
Docker prune, host processes, shared fixtures or unrelated volumes are touched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import secrets
import subprocess

OWNER = 'com.fyberlabs.ci'
REPO = 'com.fyberlabs.ci.repository'
RUN = 'com.fyberlabs.ci.run'
WORKFLOW = 'terraform-ci'
REPOSITORY = 'FyberLabs/infra'
LOCAL_RUN = 'local-' + secrets.token_hex(16)
# Exact historical UUID suffixes, including Compose's container rename prefix.
LEGACY = re.compile(r'(?:[0-9a-f]{12}_)?(?:canonical-loopback-(?:private|backend)-[0-9a-f]{32}|canonical-loopback-test-[0-9a-f]{32}(?:-ingress|-loopback-relays-1)?|canonical-proxy-(?:test|backend|process)-[0-9a-f]{32}|fixture-native-[0-9a-f]{32})')


def run_identity():
    identity = os.environ.get('INFRA_CI_RUN', LOCAL_RUN)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', identity):
        raise ValueError('Invalid CI run identity')
    return identity


def labels():
    return {OWNER: WORKFLOW, REPO: REPOSITORY, RUN: run_identity()}


def label_args():
    return [arg for key, value in labels().items() for arg in ('--label', key + '=' + value)]


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=30, check=True).stdout


def eligible(item, kind, run, stale_hours, now):
    metadata = item.get('Config', {}).get('Labels', {}) if kind in ('container', 'image') else item.get('Labels', {})
    metadata = metadata or {}
    owned = metadata.get(OWNER) == WORKFLOW and metadata.get(REPO) == REPOSITORY and bool(metadata.get(RUN))
    if run is not None:
        return owned and metadata.get(RUN) == run
    name = item.get('Name', '').lstrip('/')
    # Never adopt a resource explicitly labelled for a different owner.
    legacy = not any(key in metadata for key in (OWNER, REPO, RUN)) and LEGACY.fullmatch(name)
    if not (owned or (kind in ('container', 'network') and legacy)):
        return False
    try:
        timestamp = item.get('Created') or item.get('CreatedAt')
        if not isinstance(timestamp, str):
            return False
        created = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return created.tzinfo is not None and (now-created).total_seconds() >= stale_hours * 3600
    except (KeyError, ValueError, TypeError):
        return False


def cleanup(*, run=None, stale_hours=None, invoke=docker, now=None):
    now = now or datetime.now(timezone.utc)
    failures = []
    for kind in ('container', 'network', 'volume', 'image'):
        try:
            args = [kind, 'ls', '-q']
            if kind == 'container':
                args.append('--all')
            if run is not None:
                for key, value in ((OWNER, WORKFLOW), (REPO, REPOSITORY), (RUN, run)):
                    args.extend(['--filter', 'label=' + key + '=' + value])
            for identity in invoke(*args).splitlines():
                try:
                    items = json.loads(invoke(kind, 'inspect', identity))
                    if len(items) != 1 or not eligible(items[0], kind, run, stale_hours, now):
                        continue
                    # Remove by immutable ID, never a name another job can reuse.
                    remove = [kind, 'rm']
                    if kind == 'container':
                        remove.extend(['--force', '--volumes'])
                    invoke(*remove, identity)
                except (subprocess.SubprocessError, OSError, ValueError, TypeError) as exc:
                    # Concurrent cleanup may already have removed this identity.
                    try:
                        remaining = invoke(kind, 'ls', '-q', *(['--all'] if kind == 'container' else []), '--no-trunc' if kind != 'volume' else '--quiet').splitlines()
                    except (subprocess.SubprocessError, OSError):
                        remaining = [identity]
                    # image ls -q abbreviates IDs while --no-trunc prefixes them
                    # with sha256:. Compare the same representation so an in-use
                    # image is not mistaken for a concurrent successful removal.
                    if any(value.removeprefix('sha256:').startswith(identity.removeprefix('sha256:'))
                           for value in remaining):
                        failures.append(f'{kind} cleanup failed: {type(exc).__name__}')
        except (subprocess.SubprocessError, OSError) as exc:
            failures.append(f'{kind} enumeration failed: {type(exc).__name__}')
    if failures:
        raise RuntimeError('; '.join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--run')
    group.add_argument('--stale-hours', type=float)
    args = parser.parse_args()
    if args.stale_hours is not None and args.stale_hours < 6:
        parser.error('stale recovery must allow at least six hours')
    cleanup(run=args.run, stale_hours=args.stale_hours)


if __name__ == '__main__':
    main()
