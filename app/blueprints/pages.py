from flask import Blueprint, redirect, render_template, session, url_for

bp = Blueprint("pages", __name__)


@bp.route("/")
def home():
    if session.get("user_id"):
        r = session.get("role")
        if r == "teacher":
            return redirect(url_for("pages.teacher"))
        return redirect(url_for("pages.student"))
    return redirect(url_for("pages.login_page"))


@bp.route("/login")
def login_page():
    return render_template("login.html")


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
