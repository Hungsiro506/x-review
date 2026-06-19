#!/usr/bin/env python3
"""Run x-review from a source checkout without installing.

Prefer `pip install -e .` (gives you the `x-review` command). This shim
just lets `python review.py ...` work straight from the repo.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xreview.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
