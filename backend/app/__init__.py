"""Taiwan Stock AI Platform — Backend."""
import sys
from pathlib import Path

# Make top-level analysis packages (chip_analysis, fundamental_analysis,
# technical_analysis, ai_engine) importable from anywhere in the backend.
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

__version__ = "0.1.0"
