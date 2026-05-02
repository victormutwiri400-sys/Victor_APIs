# import flask
from flask import *
# importing pymysql
import pymysql
# importing dictcursor
import pymysql.cursors
from flask_cors import CORS
import os
import requests
import datetime
import base64
from requests.auth import HTTPBasicAuth

# initializing the flask app
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# FOOLPROOF PATH CONFIGURATION (Fixed for Alwaysdata)
# ---------------------------------------------------------
# This finds the absolute path to your current directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define specific folders using absolute paths
app.config['UPLOAD_IMAGES'] = os.path.join(BASE_DIR, 'static', 'images')
app.config['UPLOAD_PROFILES'] = os.path.join(BASE_DIR, 'static', 'profiles')
app.config['UPLOAD_GALLERY'] = os.path.join(BASE_DIR, 'static', 'gallery')
app.config['UPLOAD_ROOMS'] = os.path.join(BASE_DIR, 'static', 'rooms')

# Ensure all folders exist
for folder in [app.config['UPLOAD_IMAGES'], app.config['UPLOAD_PROFILES'], 
               app.config['UPLOAD_GALLERY'], app.config['UPLOAD_ROOMS']]:
    os.makedirs(folder, exist_ok=True)


# signup route
@app.route("/api/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    email = request.form["email"]
    phone_number = request.form["phone_number"]
    password = request.form["password"]

    connection = pymysql.connect(
        host="mysql-victordesigner.alwaysdata.net",
        user="victordesigner",
        password="project_1234",
        database="victordesigner_fullstack",
    )
    cursor = connection.cursor()
    sql = "INSERT INTO users (username, email, phone_number, password) VALUES (%s, %s, %s, %s)"
    data = (username, email, phone_number, password,)
    cursor.execute(sql, data)
    connection.commit()
    connection.close()
    return jsonify({"Success": "Thank you for signing up"})


@app.route("/api/Profile", methods=['POST'])
def Profile():
    try:
        # 1. Collect Data using .get() to prevent 'KeyError' crashes
        user_id = request.form.get('user_id')
        
        # If user_id is missing, we can't update anything
        if not user_id:
            return jsonify({"Message": "Missing user_id"}), 400

        # 2. Collect Location Data
        county = request.form.get('county')
        sub_county = request.form.get('sub_county')
        specific_address = request.form.get('specific_address')

        # 3. Handle Photo Upload
        photo = request.files.get('photo') 
        filename = None
        if photo:
            filename = photo.filename
            photo.save(os.path.join(app.config['UPLOAD_PROFILES'], filename))

        # 4. Database Connection
        connection = pymysql.connect(
            host="mysql-victordesigner.alwaysdata.net",
            user="victordesigner",
            password="project_1234",
            database="victordesigner_fullstack",
        )
        cursor = connection.cursor()

        # 5. Build Dynamic SQL 
        if filename:
            sql = """UPDATE users SET photo = %s, county = %s, sub_county = %s, 
                     specific_address = %s WHERE user_id = %s"""
            data = (filename, county, sub_county, specific_address, user_id)
        else:
            sql = """UPDATE users SET county = %s, sub_county = %s, 
                     specific_address = %s WHERE user_id = %s"""
            data = (county, sub_county, specific_address, user_id)

        cursor.execute(sql, data)
        connection.commit()
        connection.close()
        
        return jsonify({
            "Message": "Profile updated successfully", 
            "photo": filename,
            "county": county,
            "sub_county": sub_county,
            "specific_address": specific_address
        })

    except Exception as e:
        # This prints the REAL error (like "Column 'county' not found") 
        # to your Alwaysdata console/logs
        print(f"Error: {e}") 
        return jsonify({"Message": "Database error", "details": str(e)}), 500

@app.route("/api/createAdmin", methods=["POST"])
def create_admin():
    admin_email = request.form["admin_email"]
    admin_password = request.form["admin_password"]

    connection = pymysql.connect(
        host="mysql-victordesigner.alwaysdata.net",
        user="victordesigner",
        password="project_1234",
        database="victordesigner_fullstack"
    )
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM admins WHERE email = %s AND password = %s AND role = 'superadmin'"
    data = (admin_email, admin_password)
    cursor.execute(sql, data)

    if cursor.rowcount == 0:
        connection.close()
        return jsonify({"message": "unauthorized"})
    else:
        name = request.form["name"]
        email = request.form["email"]
        new_password = request.form["new_password"]
        phone = request.form["phone"]
        insert_sql = "INSERT INTO admins (username, email, password, phone) VALUES (%s, %s, %s, %s)"
        insert_data = (name, email, new_password, phone)
        cursor.execute(insert_sql, insert_data)
        connection.commit()
        connection.close()
        return jsonify({"message": "admin account created successfully"})


@app.route("/api/signin", methods=["POST"])
def signin():
    email = request.form["email"]
    password = request.form["password"]

    connection = pymysql.connect(
        host="mysql-victordesigner.alwaysdata.net",
        user="victordesigner",
        password="project_1234",
        database="victordesigner_fullstack"
    )
    cursor = connection.cursor(pymysql.cursors.DictCursor)

    # Check regular users
    sql_user = "SELECT * FROM users WHERE email = %s AND password = %s"
    cursor.execute(sql_user, (email, password))
    if cursor.rowcount > 0:
        user = cursor.fetchone()
        connection.close()
        return jsonify({"message": "login successful", "role": "user", "user": user})

    # Check admins
    sql_admin = "SELECT * FROM admins WHERE email = %s AND password = %s"
    cursor.execute(sql_admin, (email, password))
    if cursor.rowcount > 0:
        admin = cursor.fetchone()
        connection.close()
        return jsonify({"message": "login successful", "role": "admin", "admin": admin})

    connection.close()
    return jsonify({"message": "login failed"})


@app.route("/api/bookroom", methods=["POST"])
def bookRoom():
    user_id = request.form["user_id"]
    room_number = request.form["room_number"]
    check_in = request.form["check_in"]
    check_out = request.form["check_out"]

    connection = pymysql.connect(
        host="mysql-victordesigner.alwaysdata.net",
        user="victordesigner",
        password="project_1234",
        database="victordesigner_fullstack"
    )
    cursor = connection.cursor()
    sql = "INSERT INTO bookings (user_id, room_number, check_in, check_out) VALUES (%s, %s, %s, %s)"
    data = (user_id, room_number, check_in, check_out)
    cursor.execute(sql, data)
    connection.commit()
    connection.close()
    return jsonify({"Success": "Room booked successfully"})

@app.route("/api/all_bookings")
def getAllBookings():
    db = pymysql.connect(user='victordesigner', host='mysql-victordesigner.alwaysdata.net', password='project_1234', database='victordesigner_fullstack', cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as cur:
        cur.execute("SELECT *, CASE WHEN CURDATE() > check_out THEN 'Free' WHEN CURDATE() BETWEEN check_in AND check_out THEN 'Occupied' ELSE 'Upcoming' END AS status FROM bookings ORDER BY check_in DESC")
        items = cur.fetchall()
    db.close(); return jsonify({"Bookings": items})



@app.route("/api/addDining", methods=['POST'])
def addDining():
    name = request.form['name']
    description = request.form['description']
    price = request.form['price']
    photo = request.files['photo'] 
    filename = photo.filename
    # Save using absolute path
    photo.save(os.path.join(app.config['UPLOAD_IMAGES'], filename))

    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    cursor = connection.cursor()
    sql = "INSERT INTO dining (name, description, price, photo) VALUES (%s, %s, %s, %s)"
    data = (name, description, price, filename)
    cursor.execute(sql, data)
    connection.commit()
    connection.close()
    return jsonify({"Message": "Dining item added successfully"})


@app.route("/api/addGallery", methods=['POST'])
def addGallery():
    name = request.form['name']
    description = request.form['description']
    photo = request.files['photo']
    filename = photo.filename
    # Save using absolute path
    photo.save(os.path.join(app.config['UPLOAD_GALLERY'], filename))

    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    cursor = connection.cursor()
    sql = "INSERT INTO gallery (name, description, photo) VALUES (%s, %s, %s)"
    data = (name, description, filename)
    cursor.execute(sql, data)
    connection.commit()
    connection.close()
    return jsonify({"Message": "Gallery item added successfully"})


@app.route("/api/placeorders", methods=['POST']) # This MUST be POST to save data
def placeOrders():
    data = request.get_json()
    
    # Information from the frontend "POST" bundle
    user_id = data.get('user_id')
    county = data.get('county')
    sub_county = data.get('sub_county')
    specific_address = data.get('specific_address')
    orders = data.get('orders', [])

    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    
    try:
        cursor = connection.cursor()
        for order in orders:
            # The SQL POST command (INSERT)
            sql = """INSERT INTO orders 
                     (user_id, dining_id, quantity, order_date, county, sub_county, specific_address) 
                     VALUES (%s, %s, %s, NOW(), %s, %s, %s)"""
            
            cursor.execute(sql, (
                user_id, 
                order['dining_id'], 
                order['quantity'], 
                county, 
                sub_county, 
                specific_address
            ))
            
        connection.commit()
        return jsonify({"Message": "Order placed successfully"}), 201
    except Exception as e:
        return jsonify({"Error": str(e)}), 500
    finally:
        connection.close()

@app.route("/api/all_orders")
def getAllOrders():
    db = pymysql.connect(user='victordesigner', host='mysql-victordesigner.alwaysdata.net', password='project_1234', database='victordesigner_fullstack', cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as cur:
        # We explicitly calculate total_cost here so the frontend can see it
        cur.execute("SELECT o.*, u.username, d.name, (d.price * o.quantity) AS total_cost FROM orders o JOIN dining d ON o.dining_id = d.dining_id LEFT JOIN users u ON o.user_id = u.user_id ORDER BY o.order_date DESC")
        items = cur.fetchall()
    db.close(); return jsonify({"Orders": items})

@app.route("/api/orders/<int:user_id>", methods=['GET'])
def getOrders(user_id):
    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    sql = """SELECT o.order_id, d.name, d.description, d.price, o.quantity,
                    (d.price * o.quantity) AS total_cost, o.order_date, d.photo, o.booking_id
             FROM orders o
             JOIN dining d ON o.dining_id = d.dining_id
             WHERE o.user_id = %s"""
    cursor.execute(sql, (user_id,))
    items = cursor.fetchall()
    connection.close()
    return jsonify({"Message": "Orders retrieved successfully", "Orders": items})


@app.route("/api/addRoom", methods=['POST'])
def addRoom():
    description = request.form['description']
    price = request.form['price']
    photo = request.files['photo'] 
    filename = photo.filename
    # Save using absolute path
    photo.save(os.path.join(app.config['UPLOAD_ROOMS'], filename))

    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    cursor = connection.cursor()
    sql = "INSERT INTO rooms (description, price, photo) VALUES (%s, %s, %s)"
    data = (description, price, filename)
    cursor.execute(sql, data)
    connection.commit()
    room_id = cursor.lastrowid
    connection.close()
    return jsonify({"Message": "Room added successfully", "Room": {"room_id": room_id, "photo": filename}})


@app.route("/api/user_bookings/<int:user_id>", methods=['GET'])
def getUserBookings(user_id):
    connection = pymysql.connect(
        user='victordesigner',
        host='mysql-victordesigner.alwaysdata.net',
        password='project_1234',
        database='victordesigner_fullstack'
    )
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Using ONLY the columns you confirmed + basic room info
        # We use r.* to get everything from rooms to avoid 'Unknown column' errors
        sql = """SELECT b.booking_id, b.room_number, b.check_in, b.check_out, b.booking_date, r.*
                 FROM bookings b
                 JOIN rooms r ON b.room_number = r.room_id
                 WHERE b.user_id = %s
                 ORDER BY b.booking_date DESC"""
        
        cursor.execute(sql, (user_id,))
        results = cursor.fetchall()
        return jsonify({"Message": "Bookings retrieved successfully", "Bookings": results})
    except Exception as e:
        return jsonify({"Message": "Database Error", "Error": str(e)}), 500
    finally:
        connection.close()


@app.route("/api/rooms", methods=['GET'])
def rooms():
    connection = pymysql.connect(user='victordesigner', host='mysql-victordesigner.alwaysdata.net', password='project_1234', database='victordesigner_fullstack')
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("select * from rooms")
    data = cursor.fetchall()
    connection.close()
    return jsonify(data)


@app.route("/api/dining", methods=['GET'])
def dining():
    connection = pymysql.connect(user='victordesigner', host='mysql-victordesigner.alwaysdata.net', password='project_1234', database='victordesigner_fullstack')
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("select * from dining")
    data = cursor.fetchall()
    connection.close()
    return jsonify(data)


@app.route("/api/gallery", methods=['GET'])
def gallery():
    connection = pymysql.connect(user='victordesigner', host='mysql-victordesigner.alwaysdata.net', password='project_1234', database='victordesigner_fullstack')
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("select * from gallery")
    data = cursor.fetchall()
    connection.close()
    return jsonify(data)


@app.route('/api/mpesa_payment', methods=['POST'])
def mpesa_payment():
    amount = request.form['amount']
    phone = request.form['phone']
    consumer_key = "GTWADFxIpUfDoNikNGqq1C3023evM6UH"
    consumer_secret = "amFbAoUByPV2rM5A"

    api_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(api_URL, auth=HTTPBasicAuth(consumer_key, consumer_secret))
    access_token = "Bearer " + r.json()['access_token']

    timestamp = datetime.datetime.today().strftime('%Y%m%d%H%M%S')
    passkey = 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
    password = base64.b64encode(("174379" + passkey + timestamp).encode()).decode('utf-8')

    payload = {
        "BusinessShortCode": "174379",
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": "174379",
        "PhoneNumber": phone,
        "CallBackURL": "https://modcom.co.ke/api/confirmation.php",
        "AccountReference": "account",
        "TransactionDesc": "account"
    }
    headers = {"Authorization": access_token, "Content-Type": "application/json"}
    response = requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=payload, headers=headers)
    return jsonify({"message": "Please Complete Payment in Your Phone."})
