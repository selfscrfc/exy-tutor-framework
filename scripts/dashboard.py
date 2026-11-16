#!/usr/bin/env python3
"""Run the local Exy dashboard for registered learning workspaces."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exy.dashboard import DashboardServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=Path('~/.config/exy-tutor/instances.json'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with DashboardServer(args.registry, args.port) as server:
        print(f'Exy dashboard: {server.origin}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
