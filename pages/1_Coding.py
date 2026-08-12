"""Coding page — thin wrapper around pilot_coding.main()."""
import sys
from pathlib import Path

# Ensure the app/ directory is on the path so pilot_coding is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from pilot_coding import main  # noqa: E402

main()
