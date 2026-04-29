import sys
from pathlib import Path

# Ensure tests can import `app.*` AND top-level analysis packages.
_here = Path(__file__).resolve().parent
_project_root = _here.parent

for p in (_here, _project_root):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
