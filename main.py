# /// script
# requires-python = ">=3.9"
# dependencies = ["requests>=2.31"]
# ///
"""flight-kml-search entry point.

Run from anywhere with:
    uv run main.py UA888 2026-08-15 [--pick 1]
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from flight_kml.cli import main

if __name__ == "__main__":
    sys.exit(main())
