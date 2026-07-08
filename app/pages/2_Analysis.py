"""Analysis page — thin wrapper around pilot_analysis.main()."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pilot_analysis import main  # noqa: E402

main()
