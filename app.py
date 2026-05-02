import os
import imaplib
import json
import requests
import time
import random
import string
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

FIREBASE_URL = "https://earning-a9b0c-default-rtdb.firebaseio.com/VaultPay_System"

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
        return False

def generate_txn_id(length=15):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/')
def index():
    return render_template('index.html')

# API 1: GENERATE ID (Ye JSON response dega)
@app.route('/<username>/id.html/<int:amount>', methods=['GET'])
def generate_payment_id(username, amount):
    api_res = requests.get(f"{FIREBASE_URL}/apis/{username}.json")
    api_data = api_res.json()
    
    if not api_data or api_data.get('status') != 'active':
        return jsonify({"status": "error", "message": "Invalid API Username"}), 404

    txn_id = generate_txn_id()
    expires_at = int(time.time()) + 300 # 5 Minutes
    
    txn_data = {
        "username": username,
        "amount": amount,
        "upi_id": api_data.get("upi_id"),
        "status": "pending",
        "expires_at": expires_at
    }
    # Save active transaction
    requests.put(f"{FIREBASE_URL}/active_payments/{txn_id}.json", json=txn_data)
    
    return jsonify({
        "status": "success", 
        "id": txn_id, 
        "payment_url": f"https://vaultpay-gateway.onrender.com/{username}/{txn_id}"
    })

# API 2: OPEN PAYMENT PAGE (User ko yahan bhejna hai)
@app.route('/<username>/<txn_id>', methods=['GET'])
def payment_page(username, txn_id):
    txn_res = requests.get(f"{FIREBASE_URL}/active_payments/{txn_id}.json")
    txn_data = txn_res.json()
    
    if not txn_data or txn_data.get('username') != username:
        return "<h1>Invalid Payment ID.</h1>", 404
        
    if int(time.time()) > txn_data.get('expires_at') or txn_data.get('status') != 'pending':
        return "<h1>Link Expired or Processed. Please generate a new one.</h1>", 400

    return render_template('pay.html', 
                           username=username, 
                           txn_id=txn_id, 
                           amount=txn_data.get('amount'), 
                           upi_id=txn_data.get('upi_id'))

# Auto-Deposit Verification
@app.route('/api/verify', methods=['POST'])
def verify_payment():
    data = request.get_json()
    username = data.get('username')
    txn_id = data.get('txn_id')
    utr = data.get('utr')
    amount = int(data.get('amount'))

    if not utr or len(utr) < 12:
        return jsonify({"status": "error", "message": "12-digit UTR required."}), 400

    api_res = requests.get(f"{FIREBASE_URL}/apis/{username}.json")
    api_data = api_res.json()
    user_uid = api_data.get('uid')

    # Duplicate UTR Check
    dup_res = requests.get(f"{FIREBASE_URL}/transactions/{user_uid}/{utr}.json")
    if dup_res.json() is not None:
        return jsonify({"status": "error", "message": "Duplicate UTR!"}), 400

    # Verification Engine
    is_valid = check_utr_in_email(api_data.get('email'), api_data.get('app_password'), utr)

    # Dashboard Stats Update
    stats_res = requests.get(f"{FIREBASE_URL}/users/{user_uid}/stats.json")
    stats = stats_res.json() if stats_res.json() else {"total_req": 0, "success_count": 0, "success_amount": 0, "reject_count": 0, "reject_amount": 0, "pending_count": 0}
    stats["total_req"] += 1

    if is_valid:
        status_text = "success"
        stats["success_count"] += 1
        stats["success_amount"] += amount
    else:
        # PENDING FOR ADMIN LOGIC
        status_text = "pending_admin"
        stats["pending_count"] += 1

    requests.put(f"{FIREBASE_URL}/users/{user_uid}/stats.json", json=stats)
    requests.patch(f"{FIREBASE_URL}/active_payments/{txn_id}.json", json={"status": status_text, "utr": utr})
    
    txn_log = { "utr": utr, "amount": amount, "status": status_text, "api_id": username, "timestamp": {".sv": "timestamp"} }
    requests.put(f"{FIREBASE_URL}/transactions/{user_uid}/{utr}.json", json=txn_log)

    if is_valid:
        return jsonify({"status": "success", "message": "Payment Successful & Verified!"})
    else:
        return jsonify({"status": "pending", "message": "Payment sent to Admin for manual review (Not found in email)."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
