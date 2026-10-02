"""Assert this block's vendored panns_small.py matches the harness copy.

Edge Impulse uploads a block directory and nothing outside it, so the backbone
definition has to be duplicated here. A duplicate that drifts is worse than no
duplicate: the released checkpoints only load into the exact architecture, so a
divergence surfaces as a state_dict key mismatch during a Studio training run -
a long way from the edit that caused it.

Run: python vendor_check.py
"""

from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MINE = os.path.join(HERE, "panns_small.py")
HARNESS = os.path.join(HERE, "..", "..", "harness", "panns_small.py")


def digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main() -> int:
    a, b = digest(MINE), digest(os.path.normpath(HARNESS))
    print(f"block   {a[:16]}  {MINE}")
    print(f"harness {b[:16]}  {os.path.normpath(HARNESS)}")
    if a != b:
        print("\nFAIL: vendored backbone has drifted from the harness copy.\n"
              "Re-copy it: cp ../../harness/panns_small.py .", file=sys.stderr)
        return 1
    print("\nOK - identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
