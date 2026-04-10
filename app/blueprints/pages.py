from flask import Blueprint, redirect, render_template, session, url_for

bp = Blueprint("pages", __name__)


@bp.route("/")
def home():
    if session.get("user_id"):
        r = session.get("role")
        if r == "teacher":
            return redirect(url_for("pages.teacher"))
        return redirect(url_for("pages.student"))
    return render_template("index.html")


@bp.route("/login")
def login_page():
    return render_template("login.html")


@bp.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")


@bp.route("/teacher")
def teacher():
    return render_template("teacher.html")


@bp.route("/student")
def student():
    return render_template("student.html")


@bp.route("/register-face")
def register_face_page():
    return render_template("register_face.html")


@bp.route("/attend")
def attend_page():
    return render_template("attend.html")


@bp.route("/complete-profile")
def complete_profile_page():
    if not session.get("user_id"):
        return redirect(url_for("pages.home"))
    return render_template("profile_setup.html")


@bp.route("/admin")
def admin_page():
    return render_template("admin.html")

