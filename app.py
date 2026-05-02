import os
import imaplib
import json
import requests
import time
import random
import string
from flask import Flask, render_template, request, jsonify, redirect

app = Flask(__name__)

# Firebase Configuration
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
        print(f"IMAP Error: {e}")
        return False

def generate_txn_id(length=20):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/')
def index():
    return render_template('index.html')

# 1. GENERATE ID API (Acts like id.php)
@app.route('/<api_id>/id.php/<int:amount>', methods=['GET'])
def generate_payment_id(api_id, amount):
    # Fetch API details
    api_res = requests.get(f"{FIREBASE_URL}/apis/{api_id}.json")
    api_data = api_res.json()
    
    if not api_data or api_data.get('status') != 'active':
        return jsonify({"error": "Invalid or Inactive API ID"}), 400

    txn_id = generate_txn_id()
    expires_at = int(time.time()) + 300 # 5 Minutes valid
    
    # Save pending transaction
    txn_data = {
        "api_id": api_id,
        "amount": amount,
        "upi_id": api_data.get("upi_id"),
        "status": "pending",
        "expires_at": expires_at,
        "created_at": int(time.time())
    }
    requests.put(f"{FIREBASE_URL}/active_payments/{txn_id}.json", json=txn_data)
    
    # Return URL for redirection
    pay_url = f"/pay/{api_id}/{txn_id}"
    return jsonify({"status": "success", "txn_id": txn_id, "pay_url": pay_url})

# 2. PAYMENT GATEWAY PAGE
@app.route('/pay/<api_id>/<txn_id>', methods=['GET'])
def payment_page(api_id, txn_id):
    txn_res = requests.get(f"{FIREBASE_URL}/active_payments/{txn_id}.json")
    txn_data = txn_res.json()
    
    if not txn_data or txn_data.get('api_id') != api_id:
        return "<h1>Invalid Payment ID or Expired.</h1>", 404
        
    current_time = int(time.time())
    if current_time > txn_data.get('expires_at') or txn_data.get('status') != 'pending':
        return "<h1>This Payment Link has Expired or is already processed. Please generate a new one.</h1>", 400

    # Pass details to the HTML page
    return render_template('pay.html', 
                           api_id=api_id, 
                           txn_id=txn_id, 
                           amount=txn_data.get('amount'), 
                           upi_id=txn_data.get('upi_id'),
                           expires_at=txn_data.get('expires_at'))

# 3. VERIFY UTR FROM PAYMENT PAGE
@app.route('/api/verify_utr', methods=['POST'])
def verify_utr():
    data = request.get_json()
    txn_id = data.get('txn_id')
    utr = data.get('utr')
    api_id = data.get('api_id')

    if not utr or len(utr) < 12:
        return jsonify({"status": "error", "message": "Sahi 12-digit UTR daalein."}), 400

    # Get Txn Data
    txn_res = requests.get(f"{FIREBASE_URL}/active_payments/{txn_id}.json")
    txn_data = txn_res.json()
    
    if not txn_data or txn_data.get('status') != 'pending':
        return jsonify({"status": "error", "message": "Transaction expired or processed."}), 400
        
    # Get API Data
    api_res = requests.get(f"{FIREBASE_URL}/apis/{api_id}.json")
    api_data = api_res.json()
    user_id = api_data.get('uid')

    # Duplicate check globally for this user
    dup_res = requests.get(f"{FIREBASE_URL}/transactions/{user_id}/{utr}.json")
    if dup_res.json() is not None:
        return jsonify({"status": "error", "message": "Duplicate UTR! Ye UTR pehle use ho chuka hai."}), 400

    amount = txn_data.get('amount')
    # Check Email
    is_valid = check_utr_in_email(api_data.get('email'), api_data.get('app_password'), utr)

    # Update global user stats
    stats_res = requests.get(f"{FIREBASE_URL}/users/{user_id}/stats.json")
    stats = stats_res.json() if stats_res.json() else {"total_req": 0, "success_count": 0, "success_amount": 0, "reject_count": 0, "reject_amount": 0}
    stats["total_req"] += 1

    if is_valid:
        status_text = "success"
        stats["success_count"] += 1
        stats["success_amount"] += amount
    else:
        status_text = "rejected"
        stats["reject_count"] += 1
        stats["reject_amount"] += amount

    # Save Stats & Transaction
    requests.put(f"{FIREBASE_URL}/users/{user_id}/stats.json", json=stats)
    requests.patch(f"{FIREBASE_URL}/active_payments/{txn_id}.json", json={"status": status_text, "utr": utr})
    
    txn_log = { "utr": utr, "amount": amount, "status": status_text, "api_id": api_id, "timestamp": {".sv": "timestamp"} }
    requests.put(f"{FIREBASE_URL}/transactions/{user_id}/{utr}.json", json=txn_log)

    if is_valid:
        return jsonify({"status": "success", "message": "Payment Verified & Success!"})
    else:
        return jsonify({"status": "error", "message": "Payment Reject! UTR Verify nahi hua."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
