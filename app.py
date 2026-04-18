import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps

import psycopg2
import pytz
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from forms import CourseForm, LoginForm, ReturnForm

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
csrf = CSRFProtect(app)

HISTORY_PASSWORD = os.getenv("HISTORY_PASSWORD", "")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SERVICE_ACCOUNT_FILE = "cameracheckout-b1ce1b6816c0.json"

credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build("sheets", "v4", credentials=credentials)

CACHE_DURATION = timedelta(minutes=5)
last_fetch_times = {}
cached_data = {}
constraints_initialized = False


def get_db_connection():
    return psycopg2.connect(
        host="drhscit.org",
        database=os.getenv("DB"),
        user=os.getenv("DB_UN"),
        password=os.getenv("DB_PW"),
    )


def get_est_now():
    est = pytz.timezone("US/Eastern")
    now_est = datetime.now(est)
    return now_est.date(), now_est.strftime("%H:%M:%S")


def clear_sheet_cache():
    students_sheet = os.getenv("students_sheet")
    inventory_sheet = os.getenv("inventory_sheet")
    last_fetch_times.pop(students_sheet, None)
    last_fetch_times.pop(inventory_sheet, None)
    cached_data.pop(students_sheet, None)
    cached_data.pop(inventory_sheet, None)


def fetch_sheet_data(sheet_id, retry_count=3):
    now = datetime.now(pytz.timezone("US/Eastern"))

    if sheet_id in last_fetch_times and now - last_fetch_times[sheet_id] < CACHE_DURATION:
        return cached_data.get(sheet_id)

    for attempt in range(retry_count):
        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range="A1:Z")
                .execute()
            )
            data = result.get("values", [])
            cached_data[sheet_id] = data
            last_fetch_times[sheet_id] = now
            return data
        except HttpError as exc:
            if exc.resp.status == 429 and attempt < retry_count - 1:
                time.sleep(2**attempt)
                continue
            if exc.resp.status == 429:
                return cached_data.get(sheet_id, [])
            raise

    return []


def get_sheet_lookup_maps():
    students_sheet = os.getenv("students_sheet")
    inventory_sheet = os.getenv("inventory_sheet")

    students_rows = fetch_sheet_data(students_sheet)
    inventory_rows = fetch_sheet_data(inventory_sheet)

    if not students_rows or not inventory_rows:
        raise ValueError("Unable to load Google Sheets data.")

    student_header = students_rows[0]
    inventory_header = inventory_rows[0]

    try:
        badge_index_students = student_header.index("Badge #")
        badge_index_inventory = inventory_header.index("Badge #")
    except ValueError as exc:
        raise ValueError("Required 'Badge #' column is missing in Google Sheets.") from exc

    student_map = {}
    for row in students_rows[1:]:
        if len(row) <= badge_index_students:
            continue

        student_id = row[badge_index_students].strip()
        if not student_id:
            continue

        first_name = row[badge_index_students - 4] if badge_index_students >= 4 and len(row) > badge_index_students - 4 else ""
        last_name = row[badge_index_students - 3] if badge_index_students >= 3 and len(row) > badge_index_students - 3 else ""
        student_map[student_id] = (first_name, last_name)

    equipment_map = {}
    for row in inventory_rows[1:]:
        if len(row) <= badge_index_inventory:
            continue

        equipment_id = row[badge_index_inventory].strip()
        if not equipment_id:
            continue

        brand = row[badge_index_inventory - 3] if badge_index_inventory >= 3 and len(row) > badge_index_inventory - 3 else ""
        camera_number = row[badge_index_inventory - 4] if badge_index_inventory >= 4 and len(row) > badge_index_inventory - 4 else ""
        equipment_map[equipment_id] = f"{brand} {camera_number}".strip()

    return student_map, equipment_map


def get_student_name(student_id, student_map):
    return student_map.get(str(student_id).strip(), ("Unknown", "Unknown"))


def get_equipment_name(equipment_id, equipment_map):
    return equipment_map.get(str(equipment_id).strip(), f"Equipment {equipment_id}")


def insert_history_row(cur, first_name, last_name, equipment, returned_date, returned_time, checked_out_date, checked_out_time):
    cur.execute(
        """
        INSERT INTO history (
            first_name,
            last_name,
            equipment,
            date,
            time,
            checked_out_date,
            checked_out_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            first_name,
            last_name,
            equipment,
            returned_date,
            returned_time,
            checked_out_date,
            checked_out_time,
        ),
    )


def return_checked_out_equipment(cur, student_id, equipment_id, returned_date, returned_time, student_map, equipment_map):
    cur.execute(
        """
        SELECT date, time
        FROM currently_checked_out
        WHERE student_id = %s AND equipment_id = %s
        FOR UPDATE
        """,
        (student_id, equipment_id),
    )
    row = cur.fetchone()

    if not row:
        return False, "No active checkout found for that student and equipment."

    checked_out_date, checked_out_time = row
    cur.execute(
        "DELETE FROM currently_checked_out WHERE student_id = %s AND equipment_id = %s",
        (student_id, equipment_id),
    )

    first_name, last_name = get_student_name(student_id, student_map)
    equipment = get_equipment_name(equipment_id, equipment_map)
    insert_history_row(
        cur,
        first_name,
        last_name,
        equipment,
        returned_date,
        returned_time,
        checked_out_date,
        checked_out_time,
    )
    return True, None


def process_equipment(cur, student_id, equipment_id, now_date, now_time, student_map, equipment_map):
    if not equipment_id:
        return

    cur.execute(
        """
        SELECT student_id
        FROM currently_checked_out
        WHERE equipment_id = %s
        FOR UPDATE
        """,
        (equipment_id,),
    )
    active_checkout = cur.fetchone()

    if not active_checkout:
        cur.execute(
            """
            INSERT INTO currently_checked_out (student_id, equipment_id, date, time)
            VALUES (%s, %s, %s, %s)
            """,
            (student_id, equipment_id, now_date, now_time),
        )
        return

    checked_out_by = str(active_checkout[0]).strip()
    if checked_out_by != student_id:
        raise ValueError(f"Equipment ID {equipment_id} is already checked out by another student.")

    success, message = return_checked_out_equipment(
        cur,
        student_id,
        equipment_id,
        now_date,
        now_time,
        student_map,
        equipment_map,
    )
    if not success:
        raise ValueError(message)


def first_form_error(form, fallback_message):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return fallback_message


def get_current_checkouts_for_display():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT student_id, equipment_id, date, time
            FROM currently_checked_out
            ORDER BY date DESC, time DESC
            """
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if not rows:
        return []

    student_map, equipment_map = get_sheet_lookup_maps()

    result = []
    for student_id, equipment_id, checked_out_date, checked_out_time in rows:
        first_name, last_name = get_student_name(student_id, student_map)
        equipment = get_equipment_name(equipment_id, equipment_map)
        result.append(
            (
                first_name,
                last_name,
                equipment,
                checked_out_date,
                checked_out_time,
                student_id,
                equipment_id,
            )
        )
    return result


def get_history_for_display():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM history WHERE date < CURRENT_DATE - INTERVAL '12 months'")
        cur.execute(
            """
            SELECT
                first_name,
                last_name,
                equipment,
                checked_out_date,
                checked_out_time,
                date,
                time
            FROM history
            ORDER BY date DESC, time DESC
            """
        )
        return cur.fetchall()
    finally:
        conn.commit()
        cur.close()
        conn.close()


def operator_authenticated():
    return bool(session.get("operator_authenticated"))


def require_operator_auth(route_function):
    @wraps(route_function)
    def wrapped(*args, **kwargs):
        if not operator_authenticated():
            flash("Please sign in before making changes.", "danger")
            return redirect(url_for("history", next=request.path))
        return route_function(*args, **kwargs)

    return wrapped


def get_safe_next_path(next_path):
    if not next_path:
        return url_for("history")
    if next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return url_for("history")


def ensure_db_constraints():
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_currently_checked_out_equipment_unique
            ON currently_checked_out (equipment_id)
            """
        )
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_currently_checked_out_student_equipment_unique
            ON currently_checked_out (student_id, equipment_id)
            """
        )
    finally:
        cur.close()
        conn.close()


@app.before_request
def initialize_db_constraints_once():
    global constraints_initialized
    if constraints_initialized:
        return

    try:
        ensure_db_constraints()
    except Exception as exc:
        print(f"Failed to initialize DB constraints: {exc}")
    finally:
        constraints_initialized = True


@app.context_processor
def inject_template_state():
    return {"is_authenticated": operator_authenticated()}


@app.errorhandler(CSRFError)
def handle_csrf_error(_error):
    flash("Your form session expired or was invalid. Please try again.", "danger")
    return redirect(request.referrer or url_for("create"))


@app.route("/", methods=["GET", "POST"])
def create():
    form = CourseForm()

    if request.method == "POST":
        if not operator_authenticated():
            flash("Please sign in before checking items in or out.", "danger")
            return redirect(url_for("history", next=url_for("create")))

        if not form.validate_on_submit():
            flash(first_form_error(form, "Please correct the form input."), "danger")
        else:
            student_id = form.studentId.data.strip()
            equipment_ids_raw = [
                form.equipmentId1.data,
                form.equipmentId2.data,
                form.equipmentId3.data,
                form.equipmentId4.data,
                form.equipmentId5.data,
            ]

            equipment_ids = []
            seen = set()
            for equipment_id in equipment_ids_raw:
                clean_id = (equipment_id or "").strip()
                if not clean_id or clean_id in seen:
                    continue
                seen.add(clean_id)
                equipment_ids.append(clean_id)

            now_date, now_time = get_est_now()

            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("LOCK TABLE currently_checked_out IN SHARE ROW EXCLUSIVE MODE")
                student_map, equipment_map = get_sheet_lookup_maps()

                for equipment_id in equipment_ids:
                    process_equipment(
                        cur,
                        student_id,
                        equipment_id,
                        now_date,
                        now_time,
                        student_map,
                        equipment_map,
                    )

                conn.commit()
                clear_sheet_cache()
                return redirect(url_for("create"))
            except ValueError as exc:
                conn.rollback()
                flash(str(exc), "danger")
            except Exception:
                conn.rollback()
                flash("An error occurred while processing your request.", "danger")
            finally:
                cur.close()
                conn.close()

    checked_out = []
    try:
        checked_out = get_current_checkouts_for_display()
    except Exception:
        flash("Unable to load checked-out equipment right now.", "danger")

    return render_template("create.html", form=form, checked_out=checked_out)


@app.route("/return", methods=["POST"])
@require_operator_auth
def return_item():
    form = ReturnForm()
    if not form.validate_on_submit():
        flash(first_form_error(form, "Invalid return request."), "danger")
        return redirect(url_for("create"))

    student_id = form.hStudentId.data.strip()
    equipment_id = form.hEquipmentId.data.strip()
    now_date, now_time = get_est_now()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("LOCK TABLE currently_checked_out IN SHARE ROW EXCLUSIVE MODE")
        student_map, equipment_map = get_sheet_lookup_maps()

        success, message = return_checked_out_equipment(
            cur,
            student_id,
            equipment_id,
            now_date,
            now_time,
            student_map,
            equipment_map,
        )
        if not success:
            conn.rollback()
            flash(message, "danger")
            return redirect(url_for("create"))

        conn.commit()
        clear_sheet_cache()
        flash("Equipment marked as returned.", "success")
    except Exception:
        conn.rollback()
        flash("Unable to mark that equipment as returned.", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("create"))


@app.route("/history", methods=["GET"])
def history():
    login_form = LoginForm()
    login_form.next.data = request.args.get("next", "")

    if not operator_authenticated():
        return render_template("history.html", returned=[], login_form=login_form, authenticated=False)

    returned = []
    try:
        returned = get_history_for_display()
    except Exception:
        flash("Unable to load history right now.", "danger")

    return render_template("history.html", returned=returned, login_form=login_form, authenticated=True)


@app.route("/login", methods=["POST"])
def login():
    form = LoginForm()
    if not form.validate_on_submit():
        flash(first_form_error(form, "Please enter a password."), "danger")
        return redirect(url_for("history"))

    if not HISTORY_PASSWORD:
        flash("History password is not configured.", "danger")
        return redirect(url_for("history"))

    if secrets.compare_digest(form.password.data, HISTORY_PASSWORD):
        session["operator_authenticated"] = True
        flash("Signed in successfully.", "success")
        return redirect(get_safe_next_path(form.next.data))

    flash("Incorrect password.", "danger")
    return redirect(url_for("history"))


@app.route("/logout", methods=["POST"])
@require_operator_auth
def logout():
    session.pop("operator_authenticated", None)
    flash("Signed out.", "success")
    return redirect(url_for("create"))


if __name__ == "__main__":
    app.run(debug=False)
