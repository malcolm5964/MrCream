from flask import Flask, jsonify
import mysql.connector  # MySQL Connector for Python
import os

app = Flask(__name__)

# Replace these with your actual RDS instance details
DB_HOST = "database-1.cxqhjpfrxikd.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "testtest"
DB_NAME = "MrCreamdb"

# Function to connect to RDS
def connect_to_database():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

@app.route("/")
def home():
    return "Flask App Running on EC2 with Auto Scaling!"

@app.route("/db-status")
def db_status():
    conn = connect_to_database()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")
        db_name = cursor.fetchone()
        conn.close()
        return jsonify({"message": "Connected to database!", "database": db_name})
    else:
        return jsonify({"error": "Database connection failed"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
