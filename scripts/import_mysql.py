from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.services import import_csv


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        concerts = import_csv((ROOT / "data/raw/concerts.csv").open("rb"), "concerts")
        comments = import_csv((ROOT / "data/raw/comments.csv").open("rb"), "comments")
        print({"concerts": concerts, "comments": comments})
