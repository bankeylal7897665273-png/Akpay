import os
import imaplib
import json
import requests
import time
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Aapka Firebase Database URL
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
        print(f"Email Check Error: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

# EXACT URL JO AAPNE MANGA THA: /username/id.html/50
@app.route('/<username>/id.html/<int:amount>')
def generate_id_html(username, amount):
    # 1. Firebase se username (API ID) ki details nikalo
    api_res = requests.get(f"{FIREBASE_URL}/apis/{username}.json")
    api_data = api_res.json()
    
    if not api_data or api_data.get('status') != 'active':
        return "<h1>Error: API Username galat hai ya inactive hai.</h1>", 404

    # 2. id.html page ko render karo (UPI aur Amount bhej kar)
    # Timer page ke andar JavaScript handle karega
    return render_template('id.html', 
                           username=username, 
                           amount=amount, 
                           upi_id=api_data.get('upi_id'))

# Auto-Deposit Verification API (id.html isko call karega)
@app.route('/api/verify', methods=['POST'])
def verify_payment():
    data = request.get_json()
    username = data.get('username')
    utr = data.get('utr')
    amount = int(data.get('amount'))

    if not utr or len(utr) < 12:
        return jsonify({"status": "error", "message": "12-digit UTR required."}), 400

    # Get API Details (Email & Password)
    api_res = requests.get(f"{FIREBASE_URL}/apis/{username}.json")
    api_data = api_res.json()
    if not api_data:
        return jsonify({"status": "error", "message": "Invalid API."}), 400

    user_uid = api_data.get('uid')

    # Duplicate UTR Check
    dup_res = requests.get(f"{FIREBASE_URL}/transactions/{user_uid}/{utr}.json")
    if dup_res.json() is not None:
        return jsonify({"status": "error", "message": "Duplicate UTR! Ye pehle use ho chuka hai."}), 400

    # Email Checker Engine
    is_valid = check_utr_in_email(api_data.get('email'), api_data.get('app_password'), utr)

    # Dashboard Stats Update
    stats_res = requests.get(f"{FIREBASE_URL}/users/{user_uid}/stats.json")
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

    # Firebase mein Save karo
    requests.put(f"{FIREBASE_URL}/users/{user_uid}/stats.json", json=stats)
    
    txn_log = { "utr": utr, "amount": amount, "status": status_text, "api_id": username, "timestamp": {".sv": "timestamp"} }
    requests.put(f"{FIREBASE_URL}/transactions/{user_uid}/{utr}.json", json=txn_log)

    if is_valid:
        return jsonify({"status": "success", "message": "Payment Verified!"})
    else:
        return jsonify({"status": "error", "message": "Payment Reject! UTR nahi mila."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
