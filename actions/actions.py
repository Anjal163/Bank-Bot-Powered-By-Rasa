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
import requests

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

        subject = "Your OTP for balance enquiry "
        body = f"Your OTP is: {otp_code}\nIt expires in 5 minutes.If not you contact immediately to the nearest bank or on online portal"

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

class ActionVerifyBalance(Action):
    
    def name(self) -> str:
        return "action_verify_balance"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        email = tracker.get_slot("email")

        if not email:
            dispatcher.utter_message("Please provide your registered email address.")
            return []

        # ✅ Look up the customer's balance using their email
        customer = customers.find_one({"email": email})

        if not customer:
            dispatcher.utter_message(f"❌ No account found with the email: {email}.")
            return []

        balance = customer.get("balance", None)
        if not balance:
            dispatcher.utter_message("⚠️ Unable to fetch your balance at the moment.")
            return []

        # 🟢 If everything is fine
        dispatcher.utter_message(
            text=f"💰 Your current account balance (linked to {email}) is ₹{balance}."
        )

        return []

from rasa_sdk import Action
from rasa_sdk.events import SlotSet

class ActionMiniStatement(Action):
    def name(self):
        return "action_mini_statement"

    def run(self, dispatcher, tracker, domain):
        phone = tracker.get_slot("phone")

        if not phone:
            dispatcher.utter_message(text="Please provide your registered phone number.")
            return []

        dispatcher.utter_message(text=f"Here’s your mini statement for {phone}:")
        dispatcher.utter_message(text="""
            10 Nov: Coffee Shop ☕ ₹250  
            08 Nov: Salary Credit 💸 ₹45,000  
            07 Nov: Electricity Bill ⚡ ₹1,200  
            06 Nov: Online Shopping 🛒 ₹2,500  
            05 Nov: Movie Tickets 🎬 ₹400
        """)
        return []

class ActionHandoffToAgent(Action):

    def name(self):
        return "action_handoff_to_agent"

    def run(self, dispatcher, tracker, domain):

        user_message = tracker.latest_message.get("text")
        sender_id = tracker.sender_id

        # Send notification to your backend admin panel / email / support
        requests.post(
            "http://localhost:8000/notify-agent",   # FastAPI endpoint for agents
            json={
                "sender_id": sender_id,
                "message": user_message
            }
        )

        dispatcher.utter_message(
            text="You can connect with a human support agent. Please call at this number 1800 900 321"
        )

        return []


