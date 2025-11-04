# db_connector.py - Save this file in the 'myproject' directory

import mysql.connector
from mysql.connector import Error

# --- Configuration for XAMPP MySQL ---
HOST = "localhost"
USER = "root"
PASSWORD = ""  # The default password in XAMPP is usually empty
DATABASE = "smartHire" # Confirmed from your previous phpMyAdmin image

def get_db_connection():
    """
    Attempts to establish and return a new connection object to the 'smartHire' database.
    Always returns a new connection object if successful, or None if it fails.
    """
    try:
        conn = mysql.connector.connect(
            host=HOST,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
        return conn
    except Error as e:
        # Print a clear error message if the connection fails
        print("----------------------------------------------------------------------")
        print("!!! Database Connection Error. Ensure XAMPP MySQL is RUNNING and")
        print(f"!!! the database '{DATABASE}' exists. Error details: {e}")
        print("----------------------------------------------------------------------")
        return None

# Simple function to get data, using dictionary cursors for easy column access
def fetch_data(sql_query, params=None):
    """Executes a SELECT query and returns the results as a list of dictionaries."""
    conn = get_db_connection()
    results = []

    if conn is not None:
        # Use dictionary=True so results are returned as dictionaries instead of tuples
        cursor = conn.cursor(dictionary=True) 
        try:
            cursor.execute(sql_query, params or ())
            results = cursor.fetchall()
        except Exception as e:
            print(f"Database Query Error: {e}")
        finally:
            cursor.close()
            conn.close()
    
    return results