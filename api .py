# import flask
from flask import *
from flask import g
# importing pymysql
import pymysql
# importing dictcursor
import pymysql.cursors
from flask_cors import CORS
import requests
import datetime
import base64
from requests.auth import HTTPBasicAuth
import cloudinary
import cloudinary.uploader
import cloudinary.api

# =====================================================================
# SECRETS & CONFIGURATION â€” environment variables only.
# The application FAILS FAST at startup if a required variable is
# missing. The error names the variable but NEVER its value.
# =====================================================================

import os


def _required_env(var_name, default=None):
    value = os.environ.get(var_name, "").strip()
    if not value:
        if default is not None:
            return default
        raise RuntimeError("Missing required environment variable: " + var_name)
    return value


# Host / user / database may have defaults (not secrets); PASSWORD is required.
MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql-victordesigner.alwaysdata.net")
MYSQL_USER = os.environ.get("MYSQL_USER", "victordesigner")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "victordesigner_fullstack")
MYSQL_PASSWORD = _required_env("MYSQL_PASSWORD", default="")

CLOUDINARY_CLOUD_NAME = _required_env("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY = _required_env("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = _required_env("CLOUDINARY_API_SECRET", default="")

MPESA_CONSUMER_KEY = _required_env("MPESA_CONSUMER_KEY", default="")
MPESA_CONSUMER_SECRET = _required_env("MPESA_CONSUMER_SECRET", default="")
MPESA_PASSKEY = _required_env("MPESA_PASSKEY", default="")
MPESA_CALLBACK_URL = _required_env("MPESA_CALLBACK_URL", default="")

# Optional: Flask session/signing key. Used only when configured.
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "")


cloudinary.config(
  cloud_name = CLOUDINARY_CLOUD_NAME,
  api_key = CLOUDINARY_API_KEY,
  api_secret = CLOUDINARY_API_SECRET,
  secure = True
)

# Allowed image extensions for upload validation.
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _allowed_image(filename):
    """Return True if the filename has an allowed image extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _upload_to_cloudinary(photo, folder):
    """Validate and upload a FileStorage image to Cloudinary.

    Returns the secure_url on success. Raises ValueError on validation failure
    or RuntimeError on Cloudinary/upload failure. Never exposes Cloudinary
    credentials to the caller.
    """
    if not photo or not photo.filename:
        raise ValueError("No photo provided")
    if not _allowed_image(photo.filename):
        raise ValueError(
            "Invalid image type. Allowed: jpg, jpeg, png, gif, webp"
        )
    try:
        upload_result = cloudinary.uploader.upload(
            photo,
            folder=folder,
            resource_type="image",
            use_filename=True,
            unique_filename=True,
        )
        return upload_result["secure_url"]
    except Exception as exc:
        raise RuntimeError("Cloudinary upload failed: " + str(exc))


# initializing the flask app
app = Flask(__name__)
# Use an explicit signing key when one is provided (sessions/tokens only;
# the API keeps using localStorage-based auth, so this is optional).
if FLASK_SECRET_KEY:
    app.secret_key = FLASK_SECRET_KEY

# CORS: allow ONLY explicitly configured trusted origins. Never unrestricted.
# Set CORS_ALLOWED_ORIGINS (comma-separated full origins) in the environment,
# Set CORS_ALLOWED_ORIGINS to comma-separated full origins. An unset allowlist
# permits no cross-origin API requests.
CORS_ORIGINS_DEFAULT = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in CORS_ORIGINS_DEFAULT.split(",")
    if origin.strip().rstrip("/")
]
CORS(app, resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS}})

# signup route
@app.route("/api/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    email = request.form["email"]
    phone_number = request.form["phone_number"]
    password = request.form["password"]

    connection = get_db_connection()
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
        photo_url = None
        if photo and photo.filename:
            upload_result = cloudinary.uploader.upload(
                photo,
                folder="hotel_management/profiles",
                resource_type="image",
                use_filename=True,
                unique_filename=True
            )
            photo_url = upload_result["secure_url"]

        # 4. Database Connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # 5. Build Dynamic SQL 
        if photo_url:
            sql = """UPDATE users SET photo = %s, county = %s, sub_county = %s, 
                     specific_address = %s WHERE user_id = %s"""
            data = (photo_url, county, sub_county, specific_address, user_id)
        else:
            sql = """UPDATE users SET county = %s, sub_county = %s, 
                     specific_address = %s WHERE user_id = %s"""
            data = (county, sub_county, specific_address, user_id)

        cursor.execute(sql, data)
        connection.commit()
        connection.close()
        
        return jsonify({
            "Message": "Profile updated successfully", 
            "photo": photo_url,
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

    connection = get_db_connection()
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

    connection = get_db_connection()
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

    connection = get_db_connection()
    cursor = connection.cursor()
    
    # ONLY perform the insertion into bookings
    sql = "INSERT INTO bookings (user_id, room_number, check_in, check_out) VALUES (%s, %s, %s, %s)"
    data = (user_id, room_number, check_in, check_out)
    cursor.execute(sql, data)
    
    # REMOVED: The UPDATE statement that was causing the error
    
    connection.commit()
    connection.close()
    
    return jsonify({"Success": "Room booked successfully"})

@app.route("/api/all_bookings")
def getAllBookings():
    db = get_db_connection(cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as cur:
        cur.execute("SELECT *, CASE WHEN CURDATE() > check_out THEN 'Free' WHEN CURDATE() BETWEEN check_in AND check_out THEN 'Occupied' ELSE 'Upcoming' END AS status FROM bookings ORDER BY check_in DESC")
        items = cur.fetchall()
    db.close(); return jsonify({"Bookings": items})



@app.route("/api/addDining", methods=['POST'])
def addDining():
    """Legacy endpoint retained for compatibility; images are Cloudinary-only."""
    name = request.form['name']
    description = request.form['description']
    price = request.form['price']
    category = request.form['category']

    photo = request.files.get('photo')
    if not photo or not photo.filename:
        return jsonify({"Error": "No photo uploaded in the 'photo' field"}), 400

    try:
        photo_url = _upload_to_cloudinary(photo, "home/hotel dining")
    except ValueError as ve:
        return jsonify({"Error": str(ve)}), 400
    except RuntimeError as re:
        return jsonify({"Error": str(re)}), 500

    connection = get_db_connection()
    cursor = connection.cursor()
    
    sql = "INSERT INTO dining (name, description, price, photo, category) VALUES (%s, %s, %s, %s, %s)"
    data = (name, description, price, photo_url, category)
    
    cursor.execute(sql, data)
    connection.commit()
    connection.close()
    
    return jsonify({"Message": "Dining item added successfully", "photo_url": photo_url})


@app.route("/api/addDiningCloudinary", methods=['POST'])
def addDiningCloudinary():
    try:
        # 1. Retrieve text fields from the form
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')

        # 2. Retrieve the file from the form
        photo = request.files.get('photo')

        try:
            photo_url = _upload_to_cloudinary(photo, "home/hotel dining")
        except ValueError as ve:
            return jsonify({"Error": str(ve)}), 400
        except RuntimeError as re:
            return jsonify({"Error": str(re)}), 500

        # 3. Save the URL into the database instead of a local file path
        connection = get_db_connection()
        cursor = connection.cursor()
        sql = "INSERT INTO dining (name, description, price, photo, category) VALUES (%s, %s, %s, %s, %s)"
        data = (name, description, price, photo_url, category)
        cursor.execute(sql, data)
        connection.commit()
        connection.close()

        # Return the secure_url so the frontend can use it or store it
        return jsonify({
            "Message": "Dining item added successfully",
            "photo_url": photo_url
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"Message": "Database error", "details": str(e)}), 500
@app.route("/api/addGallery", methods=['POST'])
def addGallery():
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        photo = request.files.get('photo')

        try:
            photo_url = _upload_to_cloudinary(photo, "home/hotel gallery")
        except ValueError as ve:
            return jsonify({"Error": str(ve)}), 400
        except RuntimeError as re:
            return jsonify({"Error": str(re)}), 500

        connection = get_db_connection()
        cursor = connection.cursor()
        sql = "INSERT INTO gallery (name, description, photo) VALUES (%s, %s, %s)"
        data = (name, description, photo_url)
        cursor.execute(sql, data)
        connection.commit()
        connection.close()
        return jsonify({"Message": "Gallery item added successfully", "photo_url": photo_url})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"Message": "Database error", "details": str(e)}), 500


@app.route("/api/placeorders", methods=['POST']) # This MUST be POST to save data
def placeOrders():
    data = request.get_json()
    
    # Information from the frontend "POST" bundle
    user_id = data.get('user_id')
    county = data.get('county')
    sub_county = data.get('sub_county')
    specific_address = data.get('specific_address')
    orders = data.get('orders', [])

    connection = get_db_connection()
    
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
    db = get_db_connection(cursorclass=pymysql.cursors.DictCursor)
    with db.cursor() as cur:
        # We explicitly calculate total_cost here so the frontend can see it
        cur.execute("SELECT o.*, u.username, d.name, (d.price * o.quantity) AS total_cost FROM orders o JOIN dining d ON o.dining_id = d.dining_id LEFT JOIN users u ON o.user_id = u.user_id ORDER BY o.order_date DESC")
        items = cur.fetchall()
    db.close(); return jsonify({"Orders": items})

@app.route("/api/orders/<int:user_id>", methods=['GET'])
def getOrders(user_id):
    connection = get_db_connection()
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
    try:
        description = request.form.get('description')
        price = request.form.get('price')
        photo = request.files.get('photo')

        try:
            photo_url = _upload_to_cloudinary(photo, "home/hotel rooms")
        except ValueError as ve:
            return jsonify({"Error": str(ve)}), 400
        except RuntimeError as re:
            return jsonify({"Error": str(re)}), 500

        connection = get_db_connection()
        cursor = connection.cursor()
        sql = "INSERT INTO rooms (description, price, photo) VALUES (%s, %s, %s)"
        data = (description, price, photo_url)
        cursor.execute(sql, data)
        connection.commit()
        room_id = cursor.lastrowid
        connection.close()

        return jsonify({"Message": "Room added successfully", "Room": {"room_id": room_id, "photo": photo_url}})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"Message": "Database error", "details": str(e)}), 500


@app.route("/api/user_bookings/<int:user_id>", methods=['GET'])
def getUserBookings(user_id):
    connection = get_db_connection()
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
    try:
        connection = get_db_connection(cursorclass=pymysql.cursors.DictCursor)
        cursor = connection.cursor()
        
        # This query joins on room_id (from rooms) and room_number (from bookings)
        query = """
            SELECT r.*, 
            CASE 
                WHEN b.booking_id IS NOT NULL THEN 'booked' 
                ELSE 'available' 
            END as status
            FROM rooms r
            LEFT JOIN bookings b ON r.room_id = b.room_number 
            AND CURRENT_DATE BETWEEN b.check_in AND b.check_out
            GROUP BY r.room_id
        """
        
        cursor.execute(query)
        data = cursor.fetchall()
        connection.close()
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dining", methods=['GET'])
def dining():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("select * from dining")
    data = cursor.fetchall()
    connection.close()
    return jsonify(data)


@app.route("/api/gallery", methods=['GET'])
def gallery():
    connection = get_db_connection()
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    cursor.execute("select * from gallery")
    data = cursor.fetchall()
    connection.close()
    return jsonify(data)

def get_db_connection(cursorclass=None):
    """Open a NEW MySQL connection for this request and register it for
    guaranteed teardown close (serverless-safe). One connection per request,
    never shared across requests. Routes keep their own explicit close();
    the teardown hook below is the safety net for error paths.
    """
    connection = pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=cursorclass,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )
    if "db_connections" not in g:
        g.db_connections = []
    g.db_connections.append(connection)
    return connection


@app.teardown_request
def _close_db_connections(exception=None):
    """Guaranteed cleanup of every request-scoped connection on serverless."""
    connections = g.pop("db_connections", None)
    if not connections:
        return
    for connection in connections:
        try:
            connection.close()
        except Exception:
            # Already closed by the route, or closing failed; never 500.
            pass


# ==========================================================
# 1. THE COMPLETE DINING UPDATE API
# ==========================================================
@app.route('/api/updateDining', methods=['POST'])
def update_dining():
    dining_id = request.form.get("dining_id")
    name = request.form.get("name")
    description = request.form.get("description")
    price = request.form.get("price")
    
    if not dining_id:
        return jsonify({"Error": "Missing dining_id"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    update_fields = []
    data_values = []

    if name:
        update_fields.append("name = %s")
        data_values.append(name)
    if description:
        update_fields.append("description = %s")
        data_values.append(description)
    if price:
        update_fields.append("price = %s")
        data_values.append(float(price))

    if 'photo' in request.files:
        photo = request.files['photo']
        if photo and photo.filename:
            try:
                photo_url = _upload_to_cloudinary(photo, "home/hotel dining")
            except ValueError as ve:
                return jsonify({"Error": str(ve)}), 400
            except RuntimeError as re:
                return jsonify({"Error": str(re)}), 500
            update_fields.append("photo = %s")
            data_values.append(photo_url)

    if not update_fields:
        return jsonify({"Message": "No update fields were provided."}), 400

    sql = f"UPDATE dining SET {', '.join(update_fields)} WHERE dining_id = %s"
    data_values.append(dining_id)
    
    cursor.execute(sql, tuple(data_values))
    connection.commit()
    connection.close()

    return jsonify({"Success": "Dining menu changes saved perfectly!"}), 200


@app.route('/api/updateRoom', methods=['POST'])
def update_room():
    room_id = request.form.get("room_id")
    description = request.form.get("description")
    price = request.form.get("price")

    print(f"[updateRoom] ENTERED route - room_id={room_id!r}, description={description!r}, price={price!r}", flush=True)

    if not room_id:
        print("[updateRoom] Missing room_id, returning 400", flush=True)
        return jsonify({"Error": "Missing room_id"}), 400

    try:
        print("[updateRoom] Calling get_db_connection()...", flush=True)
        connection = get_db_connection()
        print(f"[updateRoom] get_db_connection() returned: {connection!r} (type={type(connection).__name__})", flush=True)
        if connection is None:
            print("[updateRoom] connection is None", flush=True)
            return jsonify({"Message": "Database error", "details": "Failed to establish database connection"}), 500

        print("[updateRoom] Calling connection.cursor()...", flush=True)
        cursor = connection.cursor()
        print(f"[updateRoom] connection.cursor() returned: {cursor!r} (type={type(cursor).__name__})", flush=True)

        update_fields = []
        data_values = []

        if description:
            update_fields.append("description = %s")
            data_values.append(description)
        if price:
            update_fields.append("price = %s")
            data_values.append(float(price))

        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename:
                try:
                    photo_url = _upload_to_cloudinary(photo, "home/hotel rooms")
                except ValueError as ve:
                    connection.close()
                    return jsonify({"Error": str(ve)}), 400
                except RuntimeError as re:
                    connection.close()
                    return jsonify({"Error": str(re)}), 500
                update_fields.append("photo = %s")
                data_values.append(photo_url)

        if not update_fields:
            connection.close()
            return jsonify({"Message": "No update fields were provided."}), 400

        sql = f"UPDATE rooms SET {', '.join(update_fields)} WHERE room_id = %s"
        data_values.append(room_id)
        print(f"[updateRoom] About to execute SQL: {sql!r} with params: {tuple(data_values)!r}", flush=True)

        cursor.execute(sql, tuple(data_values))
        print("[updateRoom] cursor.execute() succeeded", flush=True)

        print("[updateRoom] Calling connection.commit()...", flush=True)
        connection.commit()
        print("[updateRoom] connection.commit() succeeded", flush=True)

        print("[updateRoom] Calling connection.close()...", flush=True)
        connection.close()
        print("[updateRoom] connection.close() succeeded", flush=True)

        return jsonify({"Success": "Room criteria changes saved perfectly!"}), 200
    except Exception as e:
        print(f"[updateRoom] EXCEPTION: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"Message": "Database error", "details": str(e)}), 500

@app.route('/api/updateGallery', methods=['POST'])
def update_gallery():
    gallery_id = request.form.get("gallery_id")
    name = request.form.get("name")
    description = request.form.get("description")

    if not gallery_id:
        return jsonify({"Error": "Missing gallery_id"}), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    update_fields = []
    data_values = []

    if name:
        update_fields.append("name = %s")
        data_values.append(name)
    if description:
        update_fields.append("description = %s")
        data_values.append(description)

    if 'photo' in request.files:
        photo = request.files['photo']
        if photo and photo.filename:
            try:
                photo_url = _upload_to_cloudinary(photo, "home/hotel gallery")
            except ValueError as ve:
                return jsonify({"Error": str(ve)}), 400
            except RuntimeError as re:
                return jsonify({"Error": str(re)}), 500
            update_fields.append("photo = %s")
            data_values.append(photo_url)

    if not update_fields:
        return jsonify({"Message": "No update fields were provided."}), 400

    sql = f"UPDATE gallery SET {', '.join(update_fields)} WHERE gallery_id = %s"
    data_values.append(gallery_id)

    cursor.execute(sql, tuple(data_values))
    connection.commit()
    connection.close()

    return jsonify({"Success": "Gallery changes saved perfectly!"}), 200



@app.route('/api/mpesa_payment', methods=['POST'])
def mpesa_payment():
    amount = request.form['amount']
    phone = request.form['phone']
    consumer_key = MPESA_CONSUMER_KEY
    consumer_secret = MPESA_CONSUMER_SECRET

    api_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(api_URL, auth=HTTPBasicAuth(consumer_key, consumer_secret))
    access_token = "Bearer " + r.json()['access_token']

    timestamp = datetime.datetime.today().strftime('%Y%m%d%H%M%S')
    passkey = MPESA_PASSKEY
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
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": "account",
        "TransactionDesc": "account"
    }
    headers = {"Authorization": access_token, "Content-Type": "application/json"}
    response = requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=payload, headers=headers)
    return jsonify({"message": "Please Complete Payment in Your Phone."})



