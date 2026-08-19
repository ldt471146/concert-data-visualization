from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db, login_manager
from .models import AdminUser


auth = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))


def _safe_next_url(value):
    if not value:
        return url_for("admin.dashboard")
    parsed = urlparse(value)
    if parsed.netloc or parsed.scheme:
        return url_for("admin.dashboard")
    return value if value.startswith("/") else url_for("admin.dashboard")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            login_user(user, remember=False)
            return redirect(_safe_next_url(request.args.get("next")))
        flash("账号或密码不正确。", "error")

    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出管理员会话。", "success")
    return redirect(url_for("main.dashboard"))
