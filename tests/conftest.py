"""Make project modules importable; fall back to test stand-ins ONLY for modules missing from the repo."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.append(str(Path(__file__).resolve().parent / "stubs"))  # appended: real modules win
