"""Điểm vào giữ lại cho tương thích (Docker, tài liệu cũ): tương đương `python scripts/seed.py`."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.seed import main  # noqa: E402

if __name__ == "__main__":
    main()
