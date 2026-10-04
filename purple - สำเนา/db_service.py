import os
import sqlite3
import re
import hashlib
import requests
from datetime import datetime, date, timedelta
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "study_app.db"
UPLOAD_DIR = "uploaded_slides"

def init_db():
    """สร้างตารางฐานข้อมูล SQLite และโฟลเดอร์เก็บไฟล์สไลด์"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. ตารางผู้ใช้งาน
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT,
            display_name TEXT,
            created_at TEXT
        )
    """)

    # 2. ตารางโฟลเดอร์วิชา
    c.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            subject_name TEXT,
            icon TEXT,
            created_at TEXT,
            UNIQUE(user_email, subject_name)
        )
    """)

    # 3. ตารางบันทึกการอ่านหนังสือรายวัน (Habit Tracker)
    c.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            log_date TEXT,
            study_minutes INTEGER DEFAULT 0,
            questions_done INTEGER DEFAULT 0,
            note TEXT,
            UNIQUE(user_email, log_date)
        )
    """)

    # 4. ตารางประวัติการทำข้อสอบแยกตามวิชา
    c.execute("""
        CREATE TABLE IF NOT EXISTS exam_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            subject_name TEXT,
            exam_date TEXT,
            total_questions INTEGER,
            correct_answers INTEGER,
            accuracy REAL,
            mean_time_sec REAL,
            weak_topics TEXT
        )
    """)

    # 5. ตาราง habit ที่ผู้ใช้สร้างเอง + บันทึกการติ๊กรายวัน (GitHub-style Habit Tracker)
    c.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            name TEXT,
            created_at TEXT,
            UNIQUE(user_email, name)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS habit_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            habit_id INTEGER,
            check_date TEXT,
            UNIQUE(habit_id, check_date)
        )
    """)

    # 6. ตารางโหมดโฟกัส: รอบที่จบแล้ว + รอบที่กำลังจับเวลาอยู่ (เก็บใน DB เพื่อให้รีเฟรชหน้าแล้วเวลาไม่หาย)
    c.execute("""
        CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            focus_date TEXT,
            duration_sec INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS focus_active (
            user_email TEXT PRIMARY KEY,
            start_ts REAL
        )
    """)

    # 7. ผลรายหัวข้อย่อยของการสอบแต่ละครั้ง (ใช้สรุปว่าเก่ง/อ่อนเรื่องอะไร) และสรุปวิชาจาก AI
    c.execute("""
        CREATE TABLE IF NOT EXISTS topic_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            subject_name TEXT,
            exam_date TEXT,
            topic TEXT,
            total_questions INTEGER,
            correct_answers INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS subject_overview (
            user_email TEXT,
            subject_name TEXT,
            content TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_email, subject_name)
        )
    """)

    # Migration: เพิ่มคอลัมน์ใหม่ให้ฐานข้อมูลเดิม (study_app.db ที่มีอยู่แล้วใช้ต่อได้เลย)
    _add_column_if_missing(c, "subjects", "term", "TEXT")
    _add_column_if_missing(c, "users", "habits_seeded", "INTEGER DEFAULT 0")

    _remove_untouched_default_folders(c)

    conn.commit()
    conn.close()


# โฟลเดอร์วิชาตั้งต้น 2 อันที่เวอร์ชันเก่าสร้างให้ทุกคนตอนสมัคร (ตอนนี้เลิกสร้างแล้ว)
LEGACY_DEFAULT_SUBJECTS = ("สถิติประยุกต์และการวิเคราะห์ข้อมูล", "Machine Learning & AI")


def _remove_untouched_default_folders(cursor):
    """
    ลบโฟลเดอร์ตั้งต้นเก่าออกจากบัญชีที่มีอยู่แล้ว "ครั้งเดียว" โดยลบเฉพาะอันที่ยังไม่เคยถูกใช้:
    ไม่มีไฟล์สไลด์, ไม่เคยสอบ, ไม่มีสรุป AI  อันไหนมีข้อมูลแล้วจะไม่แตะ
    """
    cursor.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
    done = cursor.execute("SELECT 1 FROM app_meta WHERE key = 'removed_default_folders_v1'").fetchone()
    if done:
        return

    rows = cursor.execute(
        f"SELECT id, user_email, subject_name FROM subjects WHERE subject_name IN ({','.join('?' * len(LEGACY_DEFAULT_SUBJECTS))})",
        LEGACY_DEFAULT_SUBJECTS,
    ).fetchall()
    for sid, email, name in rows:
        used = cursor.execute("SELECT 1 FROM exam_history WHERE user_email = ? AND subject_name = ? LIMIT 1", (email, name)).fetchone()
        used = used or cursor.execute("SELECT 1 FROM topic_results WHERE user_email = ? AND subject_name = ? LIMIT 1", (email, name)).fetchone()
        used = used or cursor.execute("SELECT 1 FROM subject_overview WHERE user_email = ? AND subject_name = ? LIMIT 1", (email, name)).fetchone()
        folder = _subject_dir(email, name)
        has_files = os.path.isdir(folder) and any(os.scandir(folder))
        if used or has_files:
            continue
        cursor.execute("DELETE FROM subjects WHERE id = ?", (sid,))
        if os.path.isdir(folder):
            try:
                os.rmdir(folder)  # ลบได้เฉพาะโฟลเดอร์ว่าง
            except OSError:
                pass

    cursor.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('removed_default_folders_v1', '1')")


def _add_column_if_missing(cursor, table: str, column: str, ddl: str):
    cols = [r[1] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ==========================================
# เทอมการศึกษา (ใช้จัดกลุ่มวิชาสำหรับ Radar Chart)
# ==========================================
NO_TERM_LABEL = "ยังไม่ระบุเทอม"


def current_term_label(today: date | None = None) -> str:
    """เดาเทอมปัจจุบันตามปฏิทินไทย: ส.ค.-ธ.ค.=เทอม 1, ม.ค.-พ.ค.=เทอม 2, มิ.ย.-ก.ค.=ฤดูร้อน"""
    today = today or date.today()
    be_year = today.year + 543
    if today.month >= 8:
        return f"เทอม 1/{be_year}"
    if today.month <= 5:
        return f"เทอม 2/{be_year - 1}"
    return f"ฤดูร้อน/{be_year - 1}"


def term_options(extra: list[str] | None = None) -> list[str]:
    """รายการเทอมให้เลือก (ใหม่ → เก่า) รวมเทอมที่ผู้ใช้เคยตั้งไว้แล้ว"""
    cur = current_term_label()
    cur_year = int(re.search(r"(\d{4})", cur).group(1))
    options = []
    for year in range(cur_year, cur_year - 4, -1):
        options += [f"เทอม 1/{year}", f"เทอม 2/{year}", f"ฤดูร้อน/{year}"]
    for t in (extra or []):
        if t and t != NO_TERM_LABEL and t not in options:
            options.append(t)
    return sorted(options, key=term_sort_key, reverse=True)


def term_sort_key(label: str) -> tuple:
    """คีย์เรียงเทอม: ปีการศึกษามาก่อน แล้วค่อยเทอม (1 < 2 < ฤดูร้อน); 'ยังไม่ระบุ' ไปท้ายสุด"""
    if not label or label == NO_TERM_LABEL:
        return (-1, 0)
    m = re.search(r"(\d{4})", label)
    year = int(m.group(1)) if m else 0
    if "ฤดูร้อน" in label:
        order = 3
    elif label.strip().startswith("เทอม 2"):
        order = 2
    else:
        order = 1
    return (year, order)

# ==========================================
# ระบบ Authentication (รองรับ Firebase + SQLite)
# ==========================================
def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def register_user(email: str, password: str, display_name: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not email or len(password) < 6:
        return False, "กรุณากรอกอีเมลและตั้งรหัสผ่านอย่างน้อย 6 ตัวอักษรค่ะ 🌸"

    firebase_key = os.getenv("FIREBASE_API_KEY", "").strip()
    if firebase_key and firebase_key != "...":
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_key}"
        resp = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", "สมัครไม่สำเร็จ")
            return False, f"Firebase Error: {err}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
            (email, _hash_pw(password), display_name or email.split("@")[0], datetime.now().isoformat())
        )
        conn.commit()
        return True, "ลงทะเบียนสำเร็จแล้ว! เข้าสู่ระบบได้เลยค่ะ 🎉"
    except sqlite3.IntegrityError:
        return False, "อีเมลนี้เคยลงทะเบียนไว้แล้วค่ะ ลองเข้าสู่ระบบดูนะคะ"
    finally:
        conn.close()

def login_user(email: str, password: str) -> tuple[bool, dict | str]:
    email = email.strip().lower()
    firebase_key = os.getenv("FIREBASE_API_KEY", "").strip()
    if firebase_key and firebase_key != "...":
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_key}"
        resp = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
        if resp.status_code != 200:
            return False, "อีเมลหรือรหัสผ่านไม่ถูกต้อง (Firebase Auth)"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, display_name, password_hash FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        if firebase_key and firebase_key != "...":
            # กรณีผ่าน Firebase แต่ยังไม่มีใน SQLite
            register_user(email, password, email.split("@")[0])
            return True, {"email": email, "name": email.split("@")[0]}
        return False, "ไม่พบบัญชีผู้ใช้นี้ กรุณากดสมัครสมาชิกก่อนนะคะ 🌷"

    if not (firebase_key and firebase_key != "...") and row[2] != _hash_pw(password):
        return False, "รหัสผ่านไม่ถูกต้อง ลองใหม่อีกครั้งนะคะ 🔐"

    return True, {"email": row[0], "name": row[1]}

# ==========================================
# ระบบจัดการโฟลเดอร์วิชาและไฟล์สไลด์
# ==========================================
def get_user_subjects(email: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, subject_name, icon, term FROM subjects WHERE user_email = ? ORDER BY id ASC", (email,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "icon": r[2], "term": r[3] or None} for r in rows]

def add_subject_folder(email: str, subject_name: str, icon: str = "📚", term: str | None = None) -> tuple[bool, str]:
    subject_name = subject_name.strip()
    if not subject_name:
        return False, "กรุณาตั้งชื่อโฟลเดอร์วิชาด้วยนะคะ"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        term = None if (not term or term == NO_TERM_LABEL) else term
        c.execute("INSERT INTO subjects (user_email, subject_name, icon, created_at, term) VALUES (?, ?, ?, ?, ?)",
                  (email, subject_name, icon, datetime.now().isoformat(), term))
        conn.commit()
        return True, f"สร้างโฟลเดอร์วิชา '{icon} {subject_name}' สำเร็จแล้ว!"
    except sqlite3.IntegrityError:
        return False, "มีชื่อโฟลเดอร์วิชานี้อยู่แล้วค่ะ"
    finally:
        conn.close()

def set_subject_term(email: str, subject_name: str, term: str | None):
    term = None if (not term or term == NO_TERM_LABEL) else term
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE subjects SET term = ? WHERE user_email = ? AND subject_name = ?", (term, email, subject_name))
    conn.commit()
    conn.close()


def _subject_dir(email: str, subject_name: str) -> str:
    """ที่อยู่โฟลเดอร์ไฟล์ของวิชา (ไม่สร้างโฟลเดอร์ใหม่)"""
    safe_email = email.replace("@", "_at_").replace(".", "_")
    safe_subj = "".join(c for c in subject_name if c.isalnum() or c in (" ", "_", "-")).strip()
    return os.path.join(UPLOAD_DIR, safe_email, safe_subj)


def get_subject_folder_path(email: str, subject_name: str) -> str:
    path = _subject_dir(email, subject_name)
    os.makedirs(path, exist_ok=True)
    return path

def save_uploaded_files_to_subject(email: str, subject_name: str, uploaded_files: list) -> list[str]:
    folder = get_subject_folder_path(email, subject_name)
    saved = []
    for f in uploaded_files:
        file_path = os.path.join(folder, f.name)
        with open(file_path, "wb") as out:
            out.write(f.getbuffer())
        saved.append(file_path)
    return saved

def list_files_in_subject(email: str, subject_name: str) -> list[str]:
    folder = get_subject_folder_path(email, subject_name)
    return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".pdf", ".txt"))]

# ==========================================
# ระบบ Habit Tracker & ประวัติการสอบ
# ==========================================
def log_daily_habit(email: str, add_minutes: int = 0, add_questions: int = 0, note: str = ""):
    today_str = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT study_minutes, questions_done, note FROM habit_logs WHERE user_email = ? AND log_date = ?",
              (email, today_str))
    row = c.fetchone()
    if row:
        new_min = row[0] + add_minutes
        new_q = row[1] + add_questions
        new_note = note if note else row[2]
        c.execute("UPDATE habit_logs SET study_minutes = ?, questions_done = ?, note = ? WHERE user_email = ? AND log_date = ?",
                  (new_min, new_q, new_note, email, today_str))
    else:
        c.execute("INSERT INTO habit_logs (user_email, log_date, study_minutes, questions_done, note) VALUES (?, ?, ?, ?, ?)",
                  (email, today_str, add_minutes, add_questions, note))
    conn.commit()
    conn.close()

def get_habit_dataframe(email: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT log_date, study_minutes, questions_done, note FROM habit_logs WHERE user_email = ? ORDER BY log_date ASC",
        conn, params=(email,)
    )
    conn.close()
    return df

def calculate_study_streak(email: str) -> int:
    """จำนวนวันต่อเนื่อง: นับวันที่มีกิจกรรมอย่างใดอย่างหนึ่ง (เวลาอ่าน/โจทย์/ติ๊ก habit) ย้อนจากวันนี้"""
    df = get_habit_dataframe(email)
    active_dates = set()
    if not df.empty:
        active_dates |= set(df[(df["study_minutes"] > 0) | (df["questions_done"] > 0)]["log_date"].tolist())
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT check_date FROM habit_checks WHERE user_email = ?", (email,)).fetchall()
    conn.close()
    active_dates |= {r[0] for r in rows}

    streak = 0
    curr = date.today()
    while curr.isoformat() in active_dates:
        streak += 1
        curr -= timedelta(days=1)
    return streak

def save_exam_result(email: str, subject_name: str, total_q: int, correct_q: int, accuracy: float, mean_time: float, weak_topics: list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO exam_history (user_email, subject_name, exam_date, total_questions, correct_answers, accuracy, mean_time_sec, weak_topics)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (email, subject_name, datetime.now().strftime("%Y-%m-%d %H:%M"), total_q, correct_q, accuracy, mean_time, ", ".join(weak_topics)))
    conn.commit()
    conn.close()
    # อัปเดตจำนวนข้อที่ทำลงใน Habit Tracker ของวันนี้ให้อัตโนมัติ!
    log_daily_habit(email, add_minutes=max(1, int((total_q * mean_time) // 60) + 1), add_questions=total_q)

def get_exam_history_df(email: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, subject_name, exam_date, total_questions, correct_answers, accuracy, mean_time_sec, weak_topics FROM exam_history WHERE user_email = ? ORDER BY id ASC",
        conn, params=(email,)
    )
    conn.close()
    return df


# ==========================================
# Habit Tracker แบบ GitHub-style (เพิ่ม habit เอง + ติ๊กรายวัน)
# ==========================================
DEFAULT_HABITS = ["📖 อ่านหนังสือ", "✍️ ทำโจทย์"]


def ensure_default_habits(email: str):
    """สร้าง habit เริ่มต้น 2 อันให้ผู้ใช้ครั้งแรกครั้งเดียว (ลบทิ้งทีหลังได้ จะไม่ถูกสร้างซ้ำ)"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT habits_seeded FROM users WHERE email = ?", (email,)).fetchone()
    if row is not None and not row[0]:
        for name in DEFAULT_HABITS:
            conn.execute("INSERT OR IGNORE INTO habits (user_email, name, created_at) VALUES (?, ?, ?)",
                         (email, name, datetime.now().isoformat()))
        conn.execute("UPDATE users SET habits_seeded = 1 WHERE email = ?", (email,))
        conn.commit()
    conn.close()


def get_habits(email: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name FROM habits WHERE user_email = ? ORDER BY id ASC", (email,)).fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]


def add_habit(email: str, name: str) -> tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "กรุณาตั้งชื่อ habit ด้วยนะคะ"
    if len(name) > 40:
        return False, "ชื่อ habit ยาวเกินไปค่ะ (ไม่เกิน 40 ตัวอักษร)"
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO habits (user_email, name, created_at) VALUES (?, ?, ?)",
                     (email, name, datetime.now().isoformat()))
        conn.commit()
        return True, f"เพิ่ม habit '{name}' แล้วค่ะ"
    except sqlite3.IntegrityError:
        return False, "มี habit ชื่อนี้อยู่แล้วค่ะ"
    finally:
        conn.close()


def delete_habit(email: str, habit_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM habit_checks WHERE habit_id = ? AND user_email = ?", (habit_id, email))
    conn.execute("DELETE FROM habits WHERE id = ? AND user_email = ?", (habit_id, email))
    conn.commit()
    conn.close()


def set_habit_check(email: str, habit_id: int, day: str, done: bool):
    conn = sqlite3.connect(DB_PATH)
    owner = conn.execute("SELECT 1 FROM habits WHERE id = ? AND user_email = ?", (habit_id, email)).fetchone()
    if owner:
        if done:
            conn.execute("INSERT OR IGNORE INTO habit_checks (user_email, habit_id, check_date) VALUES (?, ?, ?)",
                         (email, habit_id, day))
        else:
            conn.execute("DELETE FROM habit_checks WHERE habit_id = ? AND check_date = ?", (habit_id, day))
        conn.commit()
    conn.close()


def get_habit_checks(email: str, since: str) -> dict[int, set[str]]:
    """คืน {habit_id: {วันที่ที่ติ๊กแล้ว (YYYY-MM-DD)}} ตั้งแต่วัน since เป็นต้นไป"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT habit_id, check_date FROM habit_checks WHERE user_email = ? AND check_date >= ?",
                        (email, since)).fetchall()
    conn.close()
    result: dict[int, set[str]] = {}
    for hid, d in rows:
        result.setdefault(hid, set()).add(d)
    return result


# ==========================================
# โหมดโฟกัส (Focus Timer)
# ==========================================
MAX_FOCUS_SEC = 6 * 3600  # กันลืมกด Stop: นับสูงสุดรอบละ 6 ชั่วโมง


def get_active_focus(email: str) -> float | None:
    """เวลาเริ่ม (epoch วินาที) ของรอบที่กำลังโฟกัสอยู่ หรือ None ถ้าไม่ได้โฟกัส"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT start_ts FROM focus_active WHERE user_email = ?", (email,)).fetchone()
    conn.close()
    return float(row[0]) if row else None


def start_focus(email: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO focus_active (user_email, start_ts) VALUES (?, ?)",
                 (email, datetime.now().timestamp()))
    conn.commit()
    conn.close()


def stop_focus(email: str) -> dict | None:
    """หยุดจับเวลา บันทึกรอบนี้ และเพิ่มนาทีเรียนเข้า Study Tracker คืนสรุปรอบที่เพิ่งจบ"""
    start_ts = get_active_focus(email)
    if start_ts is None:
        return None
    raw_sec = max(0, int(datetime.now().timestamp() - start_ts))
    capped = raw_sec > MAX_FOCUS_SEC
    duration = min(raw_sec, MAX_FOCUS_SEC)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM focus_active WHERE user_email = ?", (email,))
    conn.execute("INSERT INTO focus_sessions (user_email, focus_date, duration_sec) VALUES (?, ?, ?)",
                 (email, date.today().isoformat(), duration))
    conn.commit()
    conn.close()

    minutes = int(round(duration / 60))
    if minutes > 0:
        log_daily_habit(email, add_minutes=minutes)
    return {"duration_sec": duration, "minutes": minutes, "capped": capped}


def get_focus_today(email: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT COUNT(*), COALESCE(SUM(duration_sec), 0) FROM focus_sessions WHERE user_email = ? AND focus_date = ?",
                       (email, date.today().isoformat())).fetchone()
    conn.close()
    return {"rounds": int(row[0]), "total_sec": int(row[1])}


# ==========================================
# ผลรายหัวข้อ + สรุปวิชา
# ==========================================
def save_topic_results(email: str, subject_name: str, topic_rows: list[dict]):
    """topic_rows: [{'topic', 'total_questions', 'correct_answers'}, ...] จาก stats_service"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "INSERT INTO topic_results (user_email, subject_name, exam_date, topic, total_questions, correct_answers) VALUES (?, ?, ?, ?, ?, ?)",
        [(email, subject_name, now, str(r["topic"]), int(r["total_questions"]), int(r["correct_answers"])) for r in topic_rows]
    )
    conn.commit()
    conn.close()


def get_subject_topic_stats(email: str, subject_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT topic, total_questions AS total, correct_answers AS correct FROM topic_results WHERE user_email = ? AND subject_name = ?",
        conn, params=(email, subject_name)
    )
    conn.close()
    return df


def get_legacy_weak_topics(email: str, subject_name: str) -> list[str]:
    """หัวข้อที่อ่อนจากการสอบรุ่นเก่าที่ยังไม่มีข้อมูลรายหัวข้อ (ดึงจากคอลัมน์ weak_topics เดิม)"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT weak_topics FROM exam_history WHERE user_email = ? AND subject_name = ?",
                        (email, subject_name)).fetchall()
    conn.close()
    seen, result = set(), []
    for (text,) in rows:
        for t in (text or "").split(", "):
            t = t.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                result.append(t)
    return result


def get_subject_overview(email: str, subject_name: str) -> tuple[str, str] | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT content, updated_at FROM subject_overview WHERE user_email = ? AND subject_name = ?",
                       (email, subject_name)).fetchone()
    conn.close()
    return (row[0], row[1]) if row else None


def save_subject_overview(email: str, subject_name: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO subject_overview (user_email, subject_name, content, updated_at) VALUES (?, ?, ?, ?)",
                 (email, subject_name, content, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()