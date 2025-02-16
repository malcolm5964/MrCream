from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import mysql.connector
import os

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

# Function to get a database connection
def get_db_connection():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)

# User Class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

# Load User Function
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)  # Fetch results as dictionary
    cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return User(user["id"], user["username"], user["role"])
    return None


# Login Route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and bcrypt.check_password_hash(user[1], password):
            user_obj = User(user[0], username)
            login_user(user_obj)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password!", "danger")

    return render_template("login.html")

@app.route("/create_manager", methods=["GET", "POST"])
@login_required
def create_manager():
    if current_user.role != "Owner":
        flash("Access Denied! Only Owners can create Managers.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = bcrypt.generate_password_hash(request.form["password"]).decode("utf-8")
        outlet_id = request.form["outlet_id"]

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert new manager into users table
            cursor.execute("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'Manager')",
                           (username, email, password))
            manager_id = cursor.lastrowid  # Get the new manager's ID

            # Assign the manager to an outlet
            cursor.execute("UPDATE outlets SET manager_id = %s WHERE id = %s", (manager_id, outlet_id))

            conn.commit()
            flash("Manager created and assigned to outlet!", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for("dashboard"))

    # Fetch outlets that don't have a manager assigned
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM outlets WHERE manager_id IS NULL")
    available_outlets = cursor.fetchall()
    conn.close()

    return render_template("create_manager.html", outlets=available_outlets)


@app.route("/create_owner", methods=["GET", "POST"])
def create_owner():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if an Owner already exists
    cursor.execute("SELECT id FROM users WHERE role = 'Owner'")
    existing_owner = cursor.fetchone()

    if existing_owner:
        flash("An Owner account already exists!", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = bcrypt.generate_password_hash(request.form["password"]).decode("utf-8")

        try:
            cursor.execute("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, 'Owner')",
                           (username, email, password))
            conn.commit()
            flash("Owner account created! You can now log in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as e:
            flash(f"Error: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

    return render_template("create_owner.html")



# Protected Dashboard Route
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=current_user.username)

# Logout Route
@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
