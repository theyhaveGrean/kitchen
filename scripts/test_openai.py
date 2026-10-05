"""Deprecated command alias for source-based semantic post-processing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.postprocess_saved import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
