#!/usr/bin/env python3
"""Run the Exy Tutor CLI from any working directory."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from exy.cli import main
except ModuleNotFoundError as error:
    if error.name == 'fsrs':
        sys.exit('Install requirements.txt in .venv, then run .venv/bin/python scripts/tutor.py')
    raise

if __name__ == '__main__':
    sys.exit(main())
