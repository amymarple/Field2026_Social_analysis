"""selftest_field_motion.py — offline PASS/FAIL for the burst-motion core (synthetic; no ffmpeg/GPU/data).

Wraps field_motion._selftest so the module is discoverable alongside the other selftest_*.py files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_motion as fm

if __name__ == "__main__":
    raise SystemExit(fm._selftest())
