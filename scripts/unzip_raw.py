from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.load import extract_zip_archives

for target in extract_zip_archives(PROJECT_ROOT / "data/raw"):
    print(f"압축 해제: {target}")
