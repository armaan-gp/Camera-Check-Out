import os
import psycopg2
import secrets
from datetime import datetime, timedelta
from forms import CourseForm
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from flask import Flask, render_template, request, url_for, redirect
from googleapiclient.errors import HttpError
import time
import pytz
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
HISTORY_PASSWORD = os.getenv('HISTORY_PASSWORD', '')

SCOPES=['https://www.googleapis.com/auth/spreadsheets'] #.readonly
SERVICE_ACCOUNT_FILE = "cameracheckout-b1ce1b6816c0.json"

credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

service = build('sheets', 'v4', credentials=credentials)

def get_db_connection():
    conn = psycopg2.connect(
        host = "drhscit.org",
        database = os.getenv('DB'),
        user = os.getenv('DB_UN'),
        password = os.getenv('DB_PW')
    )
    return conn

def process_equipment(student_id, equipment_id, date, time, cur, service):
    if not equipment_id:
        return
    cur.execute('DELETE FROM currently_checked_out WHERE student_id = %s AND equipment_id = %s', (student_id, equipment_id))
    if cur.rowcount > 0:
        student_ids = [student_id]
        equipment_ids = [equipment_id]

        sheet = service.spreadsheets()
        students_sheet_id = os.getenv('students_sheet')
        range_students = 'A1:Z'
        students_result = sheet.values().get(spreadsheetId=students_sheet_id, range=range_students).execute()
        students_rows = students_result.get('values', [])

        inventory_sheet_id = os.getenv('inventory_sheet')
        range_inventory = 'A1:Z'
        inventory_result = sheet.values().get(spreadsheetId=inventory_sheet_id, range=range_inventory).execute()
        inventory_rows = inventory_result.get('values', [])

        student_header = students_rows[0]
        inventory_header = inventory_rows[0]

        try:
            badge_index_students = student_header.index('Badge #')
        except ValueError:
            raise Exception("Couldn't find 'Badge #' in sheet header.")
        try:
            badge_index_inventory = inventory_header.index('Badge #')
        except ValueError:
            raise Exception("Couldn't find 'Badge #' in inventory sheet header.")

        id_to_name = {}
        for row in students_rows[1:]:
            if len(row) > badge_index_students:
                sid = row[badge_index_students]
                if badge_index_students >= 4:
                    first_name = row[badge_index_students - 4] if len(row) > badge_index_students - 4 else ''
                    last_name = row[badge_index_students - 3] if len(row) > badge_index_students - 3 else ''
                    id_to_name[sid] = (first_name, last_name)

        equipment_info = {}
        for row in inventory_rows[1:]:
            if len(row) > badge_index_inventory:
                eid = row[badge_index_inventory]
                brand = row[badge_index_inventory - 3] if badge_index_inventory >= 3 and len(row) > badge_index_inventory - 3 else ''
                camera_number = row[badge_index_inventory - 4] if badge_index_inventory >= 4 and len(row) > badge_index_inventory - 4 else ''
                concatenated = f"{brand} {camera_number}"
                equipment_info[eid] = concatenated

        result_list = []
        for sid, eid in zip(student_ids, equipment_ids):
            name = id_to_name.get(str(sid), ("Unknown", "Unknown"))
            if name != ("Unknown", "Unknown"):
                concatenated_info = equipment_info.get(str(eid), "Unknown")
                result_list.append((name[0], name[1], concatenated_info))
            else:
                return
        #now = datetime.now()
        #now_date = now.date()
        #now_time = now.strftime("%H:%M:%S")
        now = datetime.now()
        est = pytz.timezone('US/Eastern')
        now_est = now.astimezone(est)
        now_date = now_est.date()
        now_time = now_est.strftime("%H:%M:%S")

        for tup in result_list:
            cur.execute('INSERT INTO history (first_name, last_name, equipment, date, time, checked_out_date, checked_out_time) VALUES(%s, %s, %s, %s, %s, %s, %s)',
                        (tup[0], tup[1], tup[2], date, time, now_date, now_time))
    else:
        cur.execute('INSERT INTO currently_checked_out(student_id, equipment_id, date, time) VALUES (%s, %s, %s, %s)',
                    (student_id, equipment_id, date, time))

@app.route('/', methods=['GET', 'POST'])
def create():
    form = CourseForm()
    result_list = []

    try:
        if request.method == 'POST':
            student_id = request.form['studentId'].strip()
            
            # Validate student ID is numeric
            if not student_id.isdigit():
                return render_template('create.html', form=form, checked_out=[], 
                                    error="Student ID must contain only numbers")
            

            equipment_ids = [
                request.form['equipmentId1'].strip(),
                request.form['equipmentId2'].strip(),
                request.form['equipmentId3'].strip(),
                request.form['equipmentId4'].strip(),
                request.form['equipmentId5'].strip()
            ]

            #now = datetime.now()
            #date = now.date()
            #time = now.strftime("%H:%M:%S")

            now = datetime.now()
            est = pytz.timezone('US/Eastern')
            now_est = now.astimezone(est)
            date = now_est.date()
            time = now_est.strftime("%H:%M:%S")
            
            conn = get_db_connection()
            cur = conn.cursor()
            for equipment_id in equipment_ids:
                process_equipment(student_id, equipment_id, date, time, cur, service)
            conn.commit()
            cur.close()
            conn.close()

            # Clear cache for both sheets
            last_fetch_times.pop(os.getenv('students_sheet'), None)
            last_fetch_times.pop(os.getenv('inventory_sheet'), None)
            cached_data.pop(os.getenv('students_sheet'), None)
            cached_data.pop(os.getenv('inventory_sheet'), None)


            return redirect(url_for('create'))
        

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute('''
        SELECT 
            co.student_id,
            co.equipment_id,
            co.date,
            co.time
        FROM currently_checked_out AS co
        ORDER BY co.date DESC, co.time DESC
        ''')



        rows = cur.fetchall()
        student_ids = [row[0] for row in rows]
        equipment_ids = [row[1] for row in rows]
        dates = [row[2] for row in rows]
        times = [row[3] for row in rows]
        cur.close()
        conn.close()

        # Only fetch sheets data if we have rows to process
        if rows:
            students_rows = fetch_sheet_data(os.getenv('students_sheet'))
            inventory_rows = fetch_sheet_data(os.getenv('inventory_sheet'))
            
            if not students_rows or not inventory_rows:
                return render_template('create.html', form=form, checked_out=[], 
                                    error="Unable to get Google Sheets data. Please check your subscription.")
            
            # First, find which column has 'student_id' (in case header order changes)
            student_header = students_rows[0]
            inventory_header = inventory_rows[0]

            try:
                badge_index_students = student_header.index('Badge #')
            except ValueError:
                raise Exception("Couldn't find 'Badge #' in sheet header.")

            try:
                badge_index_inventory = inventory_header.index('Badge #')
            except ValueError:
                raise Exception("Couldn't find 'Badge #' in inventory sheet header.")

            id_to_name = {}
            for row in students_rows[1:]:
                if len(row) > badge_index_students:
                    sid = row[badge_index_students]
                    if badge_index_students >= 4:
                        first_name = row[badge_index_students - 4] if len(row) > badge_index_students - 4 else ''
                        last_name = row[badge_index_students - 3] if len(row) > badge_index_students - 3 else ''
                        id_to_name[sid] = (first_name, last_name)


            equipment_info = {}
            for row in inventory_rows[1:]:
                if len(row) > badge_index_inventory:
                    eid = row[badge_index_inventory]
                    brand = row[badge_index_inventory - 3] if badge_index_inventory >= 3 and len(row) > badge_index_inventory - 3 else ''
                    camera_number = row[badge_index_inventory - 4] if badge_index_inventory >= 4 and len(row) > badge_index_inventory - 4 else ''
                    concatenated = f"{brand} {camera_number}"
                    equipment_info[eid] = concatenated

            result_list = []

            for sid, eid, date, time in zip(student_ids, equipment_ids, dates, times):
                name = id_to_name.get(str(sid).strip(), ("Unknown", "Unknown"))
                concatenated_info = equipment_info.get(str(eid), "Unknown")
                result_list.append((name[0], name[1], concatenated_info, date, time, sid, eid))



            print(result_list)
            print("results:")
            print(result_list)
            print("-------")
        
    except Exception as e:
        # Log the error (you might want to use proper logging here)
        print(f"Error: {str(e)}")
        return render_template('create.html', form=form, checked_out=[], 
                            error="An error occurred while processing your request")
    
    return render_template('create.html', form=form, checked_out=result_list)

@app.route('/history', methods=['GET', 'POST'])
def history():
    if request.method == 'POST':
        print("POST METHOD!")
        student_id = request.form['hStudentId']
        equipment_id = request.form['hEquipmentId']
        equipment = request.form['equipment']

        first_name = request.form['firstName']
        last_name = request.form['lastName']

        checked_out_date = request.form['checkedOutDate']
        checked_out_time = request.form['checkedOutTime']

        #now = datetime.now()
        #date = now.date()
        #time = now.strftime("%H:%M:%S")
        now = datetime.now()
        est = pytz.timezone('US/Eastern')
        now_est = now.astimezone(est)
        date = now_est.date()
        time = now_est.strftime("%H:%M:%S")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM currently_checked_out WHERE student_id = %s AND equipment_id = %s', (student_id, equipment_id))
        cur.execute('INSERT INTO history (first_name, last_name, equipment, date, time, checked_out_date, checked_out_time)'
                    'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (first_name, last_name, equipment, date, time, checked_out_date, checked_out_time))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('create'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM history WHERE date < CURRENT_DATE - INTERVAL '12 months'")
    conn.commit()
    cur.execute('''
    SELECT * FROM history
    ORDER BY date desc, time desc
    ''')
    data = cur.fetchall()
    cur.close()
    conn.close()

    # Format the returned date (assuming date is at index 4 in each row)
    formatted_data = []
    for row in data:
        row = list(row)
        # Format the returned date (row[4] is 'date' column)
        if row[4]:
            try:
                formatted_date = row[4].strftime("%B, %d, '%y")
                print("formatted_date = " + formatted_date)
            except Exception:
                formatted_date = str(row[4])
            row[4] = formatted_date
        formatted_data.append(tuple(row))

    return render_template('history.html', returned=formatted_data, history_password=HISTORY_PASSWORD)
CACHE_DURATION = timedelta(minutes=5)
last_fetch_times = {}
cached_data = {}

def fetch_sheet_data(sheet_id, retry_count=3):
    now = datetime.now()
    est = pytz.timezone('US/Eastern')
    now = now.astimezone(est)

    # Check cache validity for this sheet_id
    if sheet_id in last_fetch_times and now - last_fetch_times[sheet_id] < CACHE_DURATION:
        return cached_data.get(sheet_id)

    for attempt in range(retry_count):
        try:
            sheet = service.spreadsheets()
            range_name = 'A1:Z'
            result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
            data = result.get('values', [])

            # Update cache
            cached_data[sheet_id] = data
            last_fetch_times[sheet_id] = now
            return data

        except HttpError as e:
            if e.resp.status == 429:
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)
                    continue
                # Return cached if available
                return cached_data.get(sheet_id, [])
            else:
                raise
    return []

def force_refresh_cache():
    global last_fetch_time, cached_students_data, cached_inventory_data
    last_fetch_time = None
    cached_students_data = None
    cached_inventory_data = None

if __name__ == '__main__':
    app.run(debug=True)
