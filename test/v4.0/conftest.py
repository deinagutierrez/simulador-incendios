import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CODIGO = REPO / "src" / "v4.0"
sys.path.insert(0, str(CODIGO / "src"))
