from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import mysql.connector
import os
import boto3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_default")

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Load DB credentials from environment variables
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# AWS S3 Configuration
S3_BUCKET = "ict2006-images"
S3_REGION = "us-east-1"  # Change to your AWS region

# Initialize S3 client (uses AWS CLI credentials)
s3_client = boto3.client("s3")

# Allowed image extensions
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def get_db_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)


# User Class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return User(user["id"], user["username"], user["role"])
    return None


# Utility: Check allowed file type
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/add_item", methods=["GET", "POST"])
@login_required
def add_item():
    if current_user.role != "Manager" and current_user.role != "Owner":
        flash("Access Denied! Only Managers and Owners can add items.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, location FROM outlets WHERE manager_id = %s", (current_user.id,))
    outlet = cursor.fetchone()

    if not outlet:
        flash("No outlet assigned to you. Contact the Owner.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        item_name = request.form["item_name"]
        stock_count = request.form["stock_count"]
        file = request.files["file"]

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            s3_key = f"inventory/{filename}"

            try:
                # Upload file to S3
                s3_client.upload_fileobj(file, S3_BUCKET, s3_key)

                # Get S3 URL
                s3_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"

                # Save item in database
                cursor.execute(
                    "INSERT INTO inventory (outlet_id, item_name, stock_count, image_url) VALUES (%s, %s, %s, %s)",
                    (outlet["id"], item_name, stock_count, s3_url),
                )
                conn.commit()
                flash("Item added successfully!", "success")

            except Exception as e:
                flash(f"Error uploading file: {str(e)}", "danger")

        else:
            flash("Invalid file type! Only images are allowed.", "danger")

        cursor.close()
        conn.close()
        return redirect(url_for("dashboard"))

    return render_template("add_item.html", outlet=outlet)


@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if current_user.role == "Owner":
        cursor.execute("SELECT DISTINCT location FROM outlets")
        outlets = cursor.fetchall()

        cursor.execute(
            "SELECT o.location, i.id AS inventory_id, i.item_name, i.stock_count, i.image_url "
            "FROM inventory i "
            "JOIN outlets o ON i.outlet_id = o.id"
        )
        inventory_data = cursor.fetchall()

    else:
        cursor.execute("SELECT id, location FROM outlets WHERE manager_id = %s", (current_user.id,))
        outlet = cursor.fetchone()

        if outlet:
            outlets = [outlet]
            cursor.execute(
                "SELECT o.location, i.id AS inventory_id, i.item_name, i.stock_count, i.image_url "
                "FROM inventory i "
                "JOIN outlets o ON i.outlet_id = o.id "
                "WHERE o.id = %s",
                (outlet["id"],),
            )
            inventory_data = cursor.fetchall()
        else:
            outlets = []
            inventory_data = []

    conn.close()
    return render_template("dashboard.html", inventory=inventory_data, outlets=outlets)


# Logout Route
@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
