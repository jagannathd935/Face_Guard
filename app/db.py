import sqlite3

import flask


def get_db():
    if "db" not in flask.g:
        flask.g.db = sqlite3.connect(
            flask.current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        flask.g.db.row_factory = sqlite3.Row
        flask.g.db.execute("PRAGMA foreign_keys = ON;")
        flask.g.db.execute("PRAGMA journal_mode = WAL;")
        flask.g.db.execute("PRAGMA synchronous = NORMAL;")
        flask.g.db.execute("PRAGMA busy_timeout = 5000;")
    return flask.g.db


def close_db(e=None):
    db = flask.g.pop("db", None)
    if db is not None:
        db.close()


def _migrate_face_profiles(db):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='face_profiles'"
    ).fetchone()
    if not row:
        return
    cols = {r[1] for r in db.execute("PRAGMA table_info(face_profiles)").fetchall()}
    if "encoding_json" in cols and "fr_encoding_json" not in cols:
        db.execute("ALTER TABLE face_profiles RENAME COLUMN encoding_json TO fr_encoding_json")
    if "fr_encoding_json" not in cols and "encoding_json" not in cols:
        db.execute("ALTER TABLE face_profiles ADD COLUMN fr_encoding_json TEXT")
    if "lbph_model_relpath" not in cols:
        db.execute("ALTER TABLE face_profiles ADD COLUMN lbph_model_relpath TEXT")


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('teacher', 'student', 'admin')),
            org_code TEXT NOT NULL,
            security_question TEXT,
            security_answer_hash TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL,
            teacher_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS class_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            teacher_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            network_prefix TEXT,
            lat REAL,
            lng REAL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (teacher_id) REFERENCES users(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        );

        CREATE TABLE IF NOT EXISTS session_joins (
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            joined_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES class_sessions(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS face_profiles (
            user_id INTEGER PRIMARY KEY,
            fr_encoding_json TEXT,
            lbph_model_relpath TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TEXT DEFAULT (datetime('now')),
            UNIQUE(session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES class_sessions(id),
            FOREIGN KEY (student_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_teacher ON class_sessions(teacher_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_session ON attendance(session_id);

        CREATE TABLE IF NOT EXISTS student_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            roll_number TEXT,
            department TEXT,
            batch_year TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS teacher_profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            employee_id TEXT,
            department TEXT,
            designation TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            org_code TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (admin_id) REFERENCES users(id)
        );
        """
    )
    _migrate_face_profiles(db)
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()
