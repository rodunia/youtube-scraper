"""Calibration page — thin wrapper around pilot_calibration.main()."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from pilot_calibration import main  # noqa: E402

main()
