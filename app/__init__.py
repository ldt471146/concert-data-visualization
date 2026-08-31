import os
from pathlib import Path

from flask import Flask

from config import Config

from .admin_routes import admin
from .auth import auth
from .extensions import db, login_manager
from .models import AdminUser
from .routes import main
from .services import load_local_comment_snapshot, load_local_concert_snapshot, seed_demo_data


def _ensure_admin(app):
    username = app.config["ADMIN_USERNAME"]
    user = AdminUser.query.filter_by(username=username).first()
    if user:
        return
    user = AdminUser(username=username, is_active=True)
    user.set_password(app.config["ADMIN_PASSWORD"])
    db.session.add(user)
    db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        _ensure_admin(app)
        seed_demo_data()
        if app.config.get("LOAD_LOCAL_SNAPSHOT", True) and not app.testing:
            raw_dir = Path(app.root_path).parent / "data" / "raw"
            merged = raw_dir / "concerts_merged.csv"
            snapshot = merged if merged.exists() else raw_dir / "concerts.csv"
            load_local_concert_snapshot(snapshot)
            comments_in = raw_dir / "comments_input.csv"
            if comments_in.exists() and not db.session.query(
                __import__("app.models", fromlist=["CommentInfo"]).CommentInfo.id
            ).first():
                load_local_comment_snapshot(comments_in)

    return app
