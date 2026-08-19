from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.analysis import run_analysis


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        print(run_analysis())
