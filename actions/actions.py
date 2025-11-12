# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher
# from pymongo import MongoClient

# class ActionShowTransactions(Action):

#     def name(self) -> str:
#         return "action_show_recent_transactions"

#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: dict):

#         # Connect to MongoDB
#         client = MongoClient("mongodb://localhost:27017/")
#         db = client["Bankbot"]
#         transactions = db["transactions"]

#         # Get account number (you can modify this to extract from slot)
#         account_number = "12345678"

#         # Fetch last 3 transactions
#         recent_txns = list(transactions.find(
#             {"account_number": account_number}
#         ).sort("date", -1).limit(3))

#         if not recent_txns:
#             dispatcher.utter_message(text="No recent transactions found.")
#             return []

#         # Format the reply
#         reply = "Here are your recent transactions:\n"
#         for txn in recent_txns:
#             reply += f"- {txn['date']}: {txn['description']} ₹{txn['amount']}\n"

#         dispatcher.utter_message(text=reply)
#         return []


import os
import smtplib
import ssl
import random
import string
import datetime
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from pymongo import MongoClient
from rasa_sdk.events import SlotSet
from email.message import EmailMessage


class ActionSubmitAccount(Action):

    def name(self):
        return "action_submit_account"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        # 1️⃣ Collect user inputs from slots
        name = tracker.get_slot("name")
        phone = tracker.get_slot("phone")
        email = tracker.get_slot("email")
        account_type_data = tracker.get_slot("account_type")

        # Handle if account_type comes as dict or text
        if isinstance(account_type_data, dict):
            account_type = account_type_data.get("text", "")
        else:
            account_type = account_type_data

        balance = tracker.get_slot("balance")

        # ✅ Basic input cleanup
        if not name or not phone or not email:
            dispatcher.utter_message(text="Some required details are missing. Please try again.")
            return []

        # 2️⃣ Connect to MongoDB
        client = MongoClient("mongodb://localhost:27017/")
        db = client["bankDB"]           # Replace with your DB name
        customers = db["customers"]     # Your collection

        # 3️⃣ Count existing records to generate sequential IDs
        total_customers = customers.count_documents({})
        customer_id = total_customers + 1

        # 4️⃣ Generate 10-digit Account Number (e.g., 10000001)
        account_no = str(10000000 + customer_id)

        # 5️⃣ Generate password based on first name and cust_id
        first_name = name.split()[0].capitalize()
        password = f"#{first_name}{customer_id}"

        # 6️⃣ Insert new record into MongoDB
        new_customer = {
            "customer_id": customer_id,
            "name": name,
            "account_no": account_no,
            "balance": float(balance),
            "phone": phone,
            "email": email,
            "account_type": account_type,
            "password": password
        }

        customers.insert_one(new_customer)

        # 7️⃣ Respond to user dynamically
        response = (
            f"Thank you {name}! 🎉 Your {account_type.capitalize()} account has been successfully created.\n\n"
            f"Customer ID: {customer_id}\n"
            f"Account Number: {account_no}\n"
            f"Temporary Password: {password}\n\n"
            f"Please log in using your registered phone number and change your password after first login."
        )

        dispatcher.utter_message(text=response)
        return []

class ActionMinimumBalance(Action):

    def name(self):
        return "action_minimum_balance"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):

        account_type = tracker.get_slot("account_type")

        # Minimum balance per type
        balances = {
            "savings": "₹500",
            "current": "₹5,000",
            "salary": "₹0 (No minimum balance)"
        }

        key = account_type.lower()
        minimum = balances.get(key, "not available")

        dispatcher.utter_message(
            text=f"The minimum balance for a **{account_type}** account is **{minimum}**."
        )

        return []
    
# ---------- Configuration from environment -----------
# -------------------- Imports & Config --------------------

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS", "300"))  # 5 minutes

client = MongoClient(MONGO_URI)
db = client["bankDB"]
customers = db["customers"]
otps = db["otps"]


def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

# Send email
def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


# =============== SEND OTP ============================
class ActionSendOtpEmail(Action):
    def name(self):
        return "action_send_otp_email"

    def run(self, dispatcher, tracker, domain):

        email = tracker.get_slot("email")

        if not email:
            dispatcher.utter_message("Please provide your email.")
            return []

        otp_code = generate_otp()
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=OTP_EXPIRY_SECONDS)

        otps.update_one(
            {"email": email},
            {"$set": {"otp": otp_code, "expires_at": expires_at}},
            upsert=True
        )

        subject = "Your OTP for Phone Update"
        body = f"Your OTP is: {otp_code}\nIt expires in 5 minutes."

        try:
            send_email(email, subject, body)
        except Exception as e:
            print("EMAIL ERROR:", e)
            dispatcher.utter_message("Could not send OTP. Please try again.")
            return []

        dispatcher.utter_message(f"OTP has been sent to {email}.")
        return []


# =============== VALIDATE OTP ============================
class ActionValidateOtp(Action):
    def name(self):
        return "action_validate_otp"

    def run(self, dispatcher, tracker, domain):

        email = tracker.get_slot("email")
        user_otp = tracker.latest_message.get("text")
        # user_otp = tracker.get_slot("otp")

        rec = otps.find_one({"email": email})

        if not rec or rec.get("otp") != user_otp:
            dispatcher.utter_message("Invalid OTP.")
            return []

        if datetime.datetime.utcnow() > rec["expires_at"]:
            dispatcher.utter_message("OTP expired.")
            return []

        otps.delete_one({"email": email})

        dispatcher.utter_message("✅ OTP verified successfully.")
        return []

class ActionRecoverAccountNumber(Action):
    def name(self):
        return "action_recover_account_number"

    def run(self, dispatcher, tracker, domain):
        email = tracker.get_slot("email")

        if not email:
            dispatcher.utter_message("Email not found.")
            return []

        rec = otps.find_one({"email": email})

        if not rec:
            dispatcher.utter_message("No account found for this email.")
            return []

        account_number = rec.get("account_number")

        if not account_number:
            dispatcher.utter_message("Account number not available in database.")
            return []

        dispatcher.utter_message(
            response="utter_account_number_recovered",
            account_number=account_number
        )

        return [SlotSet("account_number", account_number)]

class ActionCheckBalance(Action):
    def name(self):
        return "action_check_balance"

    def run(self, dispatcher, tracker, domain):

        email = tracker.get_slot("email")
        if not email:
            dispatcher.utter_message("Email missing!")
            return []

        user = customers.find_one({"email": email})

        if not user:
            dispatcher.utter_message("No account found with this email.")
            return []

        balance = user.get("balance", "Not available")

        return [SlotSet("balance", str(balance))]


