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

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash, role FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and bcrypt.check_password_hash(user[1], password):
            user_obj = User(user[0], username, user[2])
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
            cursor.execute("INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           (username, email, password, 'Manager'))
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
    cursor.execute("SELECT id, location FROM outlets WHERE manager_id IS NULL")
    available_outlets = cursor.fetchall()
    conn.close()

    return render_template("create_manager.html", outlets=available_outlets)



@app.route("/create_outlet", methods=["GET", "POST"])
@login_required
def create_outlet():
    if current_user.role != "Owner":
        flash("Access Denied! Only Owners can create outlets.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        location = request.form["location"]

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO outlets (location) VALUES (%s)", (location,))
            conn.commit()
            flash("Outlet created successfully!", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for("dashboard"))

    return render_template("create_outlet.html")


# Protected Dashboard Route
@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if current_user.role == "Owner":
        # Get all unique outlet locations
        cursor.execute("SELECT DISTINCT location FROM outlets")
        outlets = cursor.fetchall()

        # Fetch all inventory across outlets
        cursor.execute("""
            SELECT o.location, i.id AS inventory_id, i.item_name, i.stock_count, i.image_url
            FROM inventory i
            JOIN outlets o ON i.outlet_id = o.id
        """)
        inventory_data = cursor.fetchall()

    else:
        # Fetch the single outlet assigned to the manager
        cursor.execute("SELECT id, location FROM outlets WHERE manager_id = %s", (current_user.id,))
        outlet = cursor.fetchone()  # ✅ Get a single outlet, not a list

        if outlet:
            outlets = [outlet]  # ✅ Wrap single outlet in a list
            cursor.execute("""
                SELECT o.location, i.id AS inventory_id, i.item_name, i.stock_count, i.image_url
                FROM inventory i
                JOIN outlets o ON i.outlet_id = o.id
                WHERE o.id = %s
            """, (outlet["id"],))
            inventory_data = cursor.fetchall()
        else:
            outlets = []
            inventory_data = []

    conn.close()
    return render_template("dashboard.html", inventory=inventory_data, outlets=outlets)




@app.route("/add_item", methods=["GET", "POST"])
@login_required
def add_item():
    if current_user.role not in ["Owner", "Manager"]:
        flash("Access Denied! Only Managers and Owners can add items.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if current_user.role == "Manager":
        # For managers, fetch their assigned outlet.
        cursor.execute("SELECT id, location FROM outlets WHERE manager_id = %s", (current_user.id,))
        outlet = cursor.fetchone()
        if not outlet:
            flash("No outlet assigned to you. Contact the Owner.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("dashboard"))
        context = {"outlet": outlet}
    else:  # Owner
        # For owners, fetch all outlets so they can choose one.
        cursor.execute("SELECT id, location FROM outlets")
        outlets = cursor.fetchall()
        if not outlets:
            flash("No outlets available. Contact the Administrator.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("dashboard"))
        context = {"outlets": outlets}

    if request.method == "POST":
        # If Owner, get the selected outlet_id from the form.
        if current_user.role == "Owner":
            outlet_id = request.form.get("outlet_id")
            if not outlet_id:
                flash("Please select an outlet.", "danger")
                return redirect(url_for("add_item"))
        else:
            outlet_id = context.get("outlet")["id"]

        item_name = request.form["item_name"]
        stock_count = request.form["stock_count"]
        image_url = request.form["image_url"] if request.form["image_url"] else "default.jpg"

        try:
            cursor.execute("""
                INSERT INTO inventory (outlet_id, item_name, stock_count, image_url) 
                VALUES (%s, %s, %s, %s)
            """, (outlet_id, item_name, stock_count, image_url))
            conn.commit()
            flash("Item added successfully!", "success")
        except mysql.connector.Error as e:
            flash(f"Error: {str(e)}", "danger")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for("dashboard"))

    cursor.close()
    conn.close()
    return render_template("add_item.html", **context)


@app.route("/update_stock", methods=["POST"])
@login_required
def update_stock():
    if current_user.role not in ["Owner", "Manager"]:
        flash("Access Denied!", "danger")
        return redirect(url_for("dashboard"))

    item_id = request.form.get("item_id")
    new_stock = request.form.get("stock_count")

    if not item_id or not new_stock.isdigit():
        flash("Invalid input!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE inventory SET stock_count = %s WHERE id = %s", (new_stock, item_id))
        conn.commit()
        flash("Stock updated successfully!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("dashboard"))


@app.route("/delete_item/<int:item_id>")
@login_required
def delete_item(item_id):
    if current_user.role not in ["Owner", "Manager"]:  # ✅ Allow both Owner and Manager
        flash("Access Denied!", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM inventory WHERE id = %s", (item_id,))
        conn.commit()
        flash("Item deleted successfully!", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("dashboard"))


# Logout Route
@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
