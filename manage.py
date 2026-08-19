from app import create_app
from app.extensions import db
from app.services import import_csv, run_analysis, seed_demo_data


app = create_app()


@app.cli.command("seed")
def seed_command():
    """Ensure the local demo snapshot exists."""
    with app.app_context():
        print(seed_demo_data())


@app.cli.command("analyze")
def analyze_command():
    """Rebuild keyword, sentiment and distribution aggregates."""
    with app.app_context():
        print(run_analysis())
