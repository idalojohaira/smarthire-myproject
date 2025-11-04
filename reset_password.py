# final_reset.py - Save this in C:\xampp\htdocs\smarthire\myproject

from app import app, db, User, generate_password_hash
from flask import Flask
import sys

# --- Configuration ---
NEW_PASSWORD = "testpassword123" 
USERNAMES_TO_FIX = ["admin", "employer", "applicant1"] 

# --- Execution ---
with app.app_context():
    try:
        hashed_password = generate_password_hash(NEW_PASSWORD, method='scrypt')
        updated_count = 0
        
        for username in USERNAMES_TO_FIX:
            user = User.query.filter_by(username=username).first()
            
            if user:
                user.password = hashed_password
                updated_count += 1
            else:
                print(f"User NOT FOUND: {username}. Skipping.")

        db.session.commit()
        print(f"SUCCESS! {updated_count} user(s) updated. New password: {NEW_PASSWORD}")

    except Exception as e:
        db.session.rollback()
        print(f"FATAL ERROR: {e}. Check XAMPP MySQL and PyMySQL installation.")