#!/usr/bin/env python3
"""Serve registered Exy Tutor instances over local MCP stdio."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from exy.mcp_server import build_server

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    args = parser.parse_args()
    build_server(args.registry).run(transport='stdio')
