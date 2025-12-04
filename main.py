from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from passlib.context import CryptContext
import requests
from googletrans import Translator
import subprocess
from datetime import datetime

# ----------------------------------------
# FastAPI App
# ----------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Translator
translator = Translator()

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017")
db = client["bankbot_db"]
users = db["users"]

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ==========================================================
# USER DATA MODEL
# ==========================================================
class UserMessage(BaseModel):
    message: str
    sender: str


# ==========================================================
# SIGNUP PAGE (GET)
# ==========================================================
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


# ==========================================================
# SIGNUP ACTION (POST)
# ==========================================================
@app.post("/signup")
def signup_user(username: str = Form(...), password: str = Form(...)):

    if users.find_one({"username": username}):
        return JSONResponse({"error": "Username already exists!"}, status_code=400)

    hashed_pwd = pwd_context.hash(password)

    users.insert_one({
        "username": username,
        "password": hashed_pwd
    })

    return RedirectResponse("/login", status_code=302)


# ==========================================================
# LOGIN PAGE (GET)
# ==========================================================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# ==========================================================
# LOGIN ACTION (POST)  →  3 MIN COOKIE EXPIRY ADDED
# ==========================================================
@app.post("/login")
def login_user(request: Request, username: str = Form(...), password: str = Form(...)):

    user = users.find_one({"username": username})

    if not user or not pwd_context.verify(password, user["password"]):
        return JSONResponse({"error": "Invalid username or password"}, status_code=400)

    response = RedirectResponse("/", status_code=302)

    # 🔥 Auto-logout in 3 minutes (180 sec)
    response.set_cookie(
        key="logged_in",
        value="true",
        max_age=180,
        expires=180,
        httponly=True,
        samesite="lax",
        path="/"
    )

    response.set_cookie(
        key="username",
        value=username,
        max_age=180,
        expires=180,
        httponly=False,
        samesite="lax",
        path="/"
    )

    return response


# ==========================================================
# LOGOUT
# ==========================================================
@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("logged_in")
    response.delete_cookie("username")
    return response


# ==========================================================
# HOME (CHAT UI) – Protected + SESSION EXPIRY CHECK
# ==========================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    logged = request.cookies.get("logged_in")

    # 🔥 Cookie expired OR missing = redirect to login
    if logged != "true":
        return RedirectResponse("/login")

    return templates.TemplateResponse("chat.html", {"request": request})


# ==========================================================
# HUMAN AGENT ALERT
# ==========================================================
@app.post("/notify-agent")
def notify_agent(data: dict):
    sender = data["sender_id"]
    message = data["message"]

    print("\n📢 HUMAN AGENT ALERT")
    print(f"User ID   : {sender}")
    print(f"Message   : {message}")

    return {"status": "Human agent notified"}

@app.post("/chat")
def chat_with_rasa(user_msg: UserMessage):

    rasa_url = "http://localhost:5005/webhooks/rest/webhook"
    original_msg = user_msg.message

    # Hinglish → English translation
    try:
        translated_text = translator.translate(original_msg, src="auto", dest="en").text
    except:
        translated_text = original_msg

    print(f"\n🎤 USER SAID (Original): {original_msg}")
    print(f"🌐 Translated: {translated_text}")

    payload = {
        "sender": user_msg.sender,
        "message": translated_text
    }

    try:
        resp = requests.post(rasa_url, json=payload)
        rasa_messages = resp.json()

        print("🤖 Raw Rasa Response:", rasa_messages)

        if rasa_messages:
            result = [msg.get("text", "") for msg in rasa_messages if "text" in msg]

            # ------------------------------------
            #  ⭐ SAVE CHAT LOG TO MONGO HERE ⭐
            # ------------------------------------
            log_entry = {
                "user_id": user_msg.sender,
                "user_message": original_msg,
                "bot_reply": result,
                "timestamp": datetime.now()
            }
            db.chat_logs.insert_one(log_entry)
            # ------------------------------------

            return {"bot_replies": result}

        return {"bot_replies": ["No response from bot"]}

    except Exception as e:
        return {"bot_replies": [f"Connection error: {str(e)}"]}
    
# ==========================================================
# ADMIN LOGIN PAGE (GET)
# ==========================================================

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


# ==========================================================
# ADMIN LOGIN ACTION (POST)
# ==========================================================
@app.post("/admin/login")
def admin_login(username: str = Form(...), password: str = Form(...)):

    admin = db.admin.find_one({"username": username})
    print("ADMIN FROM DB:", admin)  # <--- ADD THIS LIN

    if not admin or not pwd_context.verify(password, admin["password"]):
        print("PASSWORD VERIFY FAILED")  # <---- ADD THIS TOO
        return JSONResponse({"error": "Invalid admin credentials"}, status_code=400)

    response = RedirectResponse("/admin/dashboard", status_code=302)
    response.set_cookie("admin_logged", "true", max_age=3600)
    return response


# ==========================================================
# ADMIN LOGOUT
# ==========================================================
@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie("admin_logged")
    return response


# ==========================================================
# ADMIN DASHBOARD (Protected)
# ==========================================================
@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):

    if request.cookies.get("admin_logged") != "true":
        return RedirectResponse("/admin/login")

    return templates.TemplateResponse("admin_dashboard.html", {"request": request})


# ==========================================================
# ADMIN — VIEW CHAT LOGS
# ==========================================================
@app.get("/admin/chats", response_class=HTMLResponse)
def admin_chats(request: Request):

    if request.cookies.get("admin_logged") != "true":
        return RedirectResponse("/admin/login")

    logs = list(db.chat_logs.find().sort("timestamp", -1))

    return templates.TemplateResponse("admin_chats.html", {
        "request": request,
        "logs": logs
    })


# ==========================================================
# ADMIN — EDIT TRAINING DATA (Protected)
# ==========================================================
@app.get("/admin/edit/nlu", response_class=HTMLResponse)
def edit_nlu(request: Request):

    if request.cookies.get("admin_logged") != "true":
        return RedirectResponse("/admin/login")

    nlu_path = "C:/RasaBot/BankBot/data/nlu.yml"   # Update path!

    with open(nlu_path, "r", encoding="utf-8") as f:
        content = f.read()

    return templates.TemplateResponse(
        "admin_edit_training.html",
        {"request": request, "content": content}
    )


@app.post("/admin/edit/nlu")
def save_nlu(content: str = Form(...)):

    nlu_path = "C:/RasaBot/BankBot/data/nlu.yml"   # Update path!

    with open(nlu_path, "w", encoding="utf-8") as f:
        f.write(content)

    return RedirectResponse("/admin/dashboard", status_code=302)

# ==========================================================
# ADMIN — TRAIN RASA MODEL (Protected)
# ==========================================================
@app.get("/admin/train")
def train_model(request: Request):

    if request.cookies.get("admin_logged") != "true":
        return RedirectResponse("/admin/login")

    # Correct way to run rasa inside current venv
    subprocess.Popen(
        ["python", "-m", "rasa", "train"],
        cwd="C:/RasaBot/BankBot",   # <-- IMPORTANT! Set your project folder path
        shell=True
    )

    return {"status": "Training started!"}

