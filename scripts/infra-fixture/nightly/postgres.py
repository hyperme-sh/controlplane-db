#!/usr/bin/env python3
"""Create the nightly job's labelled, loopback-only disposable database."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_resources import label_args, run_identity

IMAGE = 'postgres:16-alpine@sha256:20edbde7749f822887a1a022ad526fde0a47d6b2be9a8364433605cf65099416'


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True,
                          check=True, timeout=120).stdout.strip()


def start(invoke=docker, sleep=time.sleep):
    name = 'infra-nightly-postgres-' + run_identity()
    try:
        invoke('run', '--detach', '--name', name, *label_args(),
               '--publish', '127.0.0.1::5432', '--tmpfs', '/var/lib/postgresql/data',
               '--env', 'POSTGRES_PASSWORD=disposable-nightly-only',
               '--health-cmd', 'pg_isready -U postgres', '--health-interval', '2s',
               '--health-timeout', '2s', '--health-retries', '30', IMAGE)
        for _ in range(60):
            info = json.loads(invoke('container', 'inspect', name))[0]
            state = info['State']
            if not state['Running']:
                raise RuntimeError('Disposable nightly PostgreSQL exited')
            if state.get('Health', {}).get('Status') == 'healthy':
                ports = info['NetworkSettings']['Ports']['5432/tcp']
                if len(ports) != 1 or ports[0]['HostIp'] != '127.0.0.1':
                    raise RuntimeError('Disposable database must publish only on loopback')
                port = int(ports[0]['HostPort'])
                if not 1 <= port <= 65535:
                    raise ValueError('Invalid disposable database port')
                return f'postgresql+psycopg://postgres:disposable-nightly-only@127.0.0.1:{port}/postgres'
            sleep(1)
        raise TimeoutError('Disposable nightly PostgreSQL did not become healthy')
    except BaseException:
        # The workflow also cleans by labels if this process is killed before
        # its local cleanup can finish. Never enumerate/remove foreign objects.
        try:
            invoke('container', 'rm', '--force', '--volumes', name)
        except (OSError, subprocess.SubprocessError):
            pass
        raise


def main():
    if not os.environ.get('INFRA_CI_RUN'):
        raise RuntimeError('Workflow-owned run identity is required')
    url = start()
    with open(os.environ['GITHUB_ENV'], 'a') as stream:
        stream.write('TEST_DATABASE_URL=' + url + '\n')


if __name__ == '__main__':
    main()
