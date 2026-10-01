import os
import uuid
import qrcode
import io
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import mysql.connector

app = Flask(__name__)

# Security PIN for Admin Page
ADMIN_SECRET_PIN = "1020"

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        port=int(os.environ.get('DB_PORT', 25123)),
        user=os.environ.get('DB_USER', 'avnadmin'),
        password=os.environ.get('DB_PASSWORD'),
        database=os.environ.get('DB_NAME', 'defaultdb'),
        ssl_disabled=False
    )

# ROUTE 0: Root Redirect to Admin Page
@app.route('/')
def home():
    return render_template('admin.html')

# ROUTE 1: Issue Passes (Admin Page)
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        admin_pin = request.form.get('admin_pin', '').strip()
        if admin_pin != ADMIN_SECRET_PIN:
            return jsonify({"status": "ERROR", "message": "Invalid Admin PIN!"}), 403

        student_name = request.form.get('student_name', '').strip()
        roll_number = request.form.get('roll_number', '').strip().upper()
        semester = request.form.get('semester', '').strip()
        department = request.form.get('department', '').strip()
        payment_mode = request.form.get('payment_mode', 'OFFLINE')

        pass_code = str(uuid.uuid4())

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO tickets (roll_number, student_name, semester, department, payment_mode, pass_code)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (roll_number, student_name, semester, department, payment_mode, pass_code))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({"status": "SUCCESS", "message": "Pass Generated!", "pass_code": pass_code})
        except mysql.connector.Error as err:
            return jsonify({"status": "ERROR", "message": f"DB Error: {str(err)}"}), 400

    # FIX: Explicitly render admin.html on GET request
    return render_template('admin.html')

# ROUTE 2: View E-Pass (Students)
@app.route('/pass/<pass_code>')
def view_pass(pass_code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets WHERE pass_code = %s", (pass_code,))
        ticket = cursor.fetchone()
        cursor.close()
        conn.close()

        if not ticket:
            return "<h2>Invalid or Expired Pass Link!</h2>", 404

        # Dynamically generate QR code in memory as Base64 string
        verify_url = f"https://{request.host}/api/verify/{pass_code}"
        qr_img = qrcode.make(verify_url)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return render_template('pass_view.html', ticket=ticket, qr_b64=qr_b64)
    except Exception as e:
        return f"Error: {str(e)}", 500

# ROUTE 3: Verification API (Called by Gate Scanner)
@app.route('/api/verify/<pass_code>', methods=['GET'])
def verify_pass(pass_code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets WHERE pass_code = %s", (pass_code,))
        ticket = cursor.fetchone()

        if not ticket:
            cursor.close()
            conn.close()
            return jsonify({"status": "INVALID", "message": "FAKE / UNREGISTERED PASS!"}), 404

        if ticket['is_used'] == 1:
            scanned_time = ticket['scanned_at'].strftime('%I:%M %p')
            cursor.close()
            conn.close()
            return jsonify({
                "status": "ALREADY_USED",
                "message": f"ENTRY DENIED! Already scanned today at {scanned_time}",
                "student_name": ticket['student_name']
            }), 400

        # Mark ticket as used
        now = datetime.now()
        cursor.execute("UPDATE tickets SET is_used = 1, scanned_at = %s WHERE pass_code = %s", (now, pass_code))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "VALID",
            "message": "ACCESS GRANTED",
            "student_name": ticket['student_name'],
            "roll_number": ticket['roll_number'],
            "semester": ticket['semester'],
            "department": ticket['department']
        }), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

# ROUTE 4: Scanner UI Page
@app.route('/scanner')
def scanner():
    return render_template('scanner.html')

if __name__ == '__main__':
    app.run(debug=True)
