"""
Lets `pytest` find the package without requiring `pip install -e .` first
(useful right after a fresh clone). If you do install the package
(recommended — see README.md), this has no effect either way.
"""

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
