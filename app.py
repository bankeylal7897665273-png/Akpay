import os
import imaplib
import json
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Firebase REST API Base URL
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/verify/<user_id>', methods=['POST'])
def verify_payment(user_id):
    data = request.get_json()
    utr = data.get('utr')
    amount = data.get('amount', '0')

    if not utr or len(utr) < 12:
        return jsonify({"status": "error", "message": "Invalid UTR"}), 400

    # 1. Fetch user API details from Firebase
    user_res = requests.get(f"{FIREBASE_URL}/apis/{user_id}.json")
    user_data = user_res.json()

    if not user_data:
        return jsonify({"status": "error", "message": "Invalid API Key"}), 401

    email_acc = user_data.get('email')
    app_pass = user_data.get('app_password')

    # 2. Check duplicate UTR globally for this user
    # (Assuming we log transactions in Firebase)
    txn_res = requests.get(f"{FIREBASE_URL}/transactions/{user_id}/{utr}.json")
    if txn_res.json() is not None:
        return jsonify({"status": "error", "message": "Duplicate UTR Request"}), 400

    # 3. Check Email
    is_valid = check_utr_in_email(email_acc, app_pass, utr)

    # 4. Save Transaction in Firebase
    txn_data = {
        "utr": utr,
        "amount": amount,
        "status": "Success" if is_valid else "Rejected",
        "timestamp": {".sv": "timestamp"}
    }
    requests.put(f"{FIREBASE_URL}/transactions/{user_id}/{utr}.json", json=txn_data)

    if is_valid:
        return jsonify({"status": "success", "message": "Payment Verified", "amount": amount})
    else:
        return jsonify({"status": "error", "message": "Payment Not Found or Rejected"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
