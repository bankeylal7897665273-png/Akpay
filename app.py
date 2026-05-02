import os
import imaplib
import json
import requests
import random
import string
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect

app = Flask(__name__)

# Firebase Config Route
FIREBASE_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com/VaultPay_System"

def generate_secure_id(length=20):
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(letters_and_digits) for i in range(length))

def check_utr_in_email(email_account, app_password, utr_number):
    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(email_account, app_password)
        mail.select('inbox')
        status, messages = mail.search(None, f'TEXT "{utr_number}"')
        if status == 'OK' and messages[0]:
            mail.logout()
            return True
        mail.logout()
        return False
    except Exception as e:
        print(f"Email Error: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

# --- 1. ID Generation API (Dynamic Amount locked) ---
@app.route('/api/create_id/<username>/<amount>', methods=['GET'])
def create_payment_id(username, amount):
    # Check if API exists
    apis_res = requests.get(f"{FIREBASE_URL}/apis.json")
    all_apis = apis_res.json()
    
    api_data = None
    api_id_key = None
    for key, val in all_apis.items():
        if val.get('username') == username and val.get('status') == 'active':
            api_data = val
            api_id_key = key
            break

    if not api_data:
        return jsonify({"status": "error", "message": "Invalid or Disabled Username"}), 400

    new_id = generate_secure_id()
    expiry_time = time.time() + 300 # 5 minutes expiry
    
    # Save ID securely in Firebase
    requests.put(f"{FIREBASE_URL}/payment_ids/{new_id}.json", json={
        "username": username,
        "amount": amount,
        "upi_id": api_data.get('upi_id'),
        "api_id": api_id_key,
        "expiry": expiry_time,
        "status": "pending"
    })
    
    return jsonify({"status": "success", "payment_id": new_id, "amount": amount, "expires_in": "5 mins"})

# --- 2. Secure Verification API ---
@app.route('/api/verify', methods=['POST'])
def verify_payment():
    data = request.get_json()
    utr = data.get('utr')
    payment_id = data.get('payment_id')

    if not utr or len(utr) < 12:
        return jsonify({"status": "error", "message": "Invalid UTR"}), 400

    # Fetch Payment ID Details
    id_res = requests.get(f"{FIREBASE_URL}/payment_ids/{payment_id}.json")
    id_data = id_res.json()

    if not id_data: return jsonify({"status": "error", "message": "Invalid Payment ID"}), 404
    if id_data.get('status') != 'pending': return jsonify({"status": "error", "message": "Payment ID already used or expired"}), 400
    if time.time() > id_data.get('expiry'):
        requests.patch(f"{FIREBASE_URL}/payment_ids/{payment_id}.json", json={"status": "expired"})
        return jsonify({"status": "error", "message": "ID Expired. Please generate a new one."}), 400

    # Fetch User API Details
    api_res = requests.get(f"{FIREBASE_URL}/apis/{id_data['api_id']}.json")
    api_data = api_res.json()

    # Check Email
    is_valid = check_utr_in_email(api_data['email'], api_data['app_password'], utr)

    # Log Transaction
    txn_status = "Success" if is_valid else "Rejected"
    amount = id_data['amount']
    uid = api_data['uid']
    
    txn_data = { "utr": utr, "amount": amount, "status": txn_status, "payment_id": payment_id, "timestamp": {".sv": "timestamp"} }
    requests.put(f"{FIREBASE_URL}/transactions/{uid}/{utr}.json", json=txn_data)
    requests.patch(f"{FIREBASE_URL}/payment_ids/{payment_id}.json", json={"status": txn_status})

    if is_valid:
        return jsonify({"status": "success", "message": "Payment Verified!", "amount": amount})
    else:
        return jsonify({"status": "error", "message": "UTR not found in bank records. Rejected."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
