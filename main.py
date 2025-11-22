from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from googletrans import Translator

# Create FastAPI app
app = FastAPI()

# Allow frontend (HTML) to connect to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates folder
templates = Jinja2Templates(directory="templates")

# Translator instance
translator = Translator()

# User message model (sender required)
class UserMessage(BaseModel):
    message: str
    sender: str


# -------------------------------
# Home route -> loads chat UI
# -------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


# -------------------------------------------------
# HUMAN AGENT NOTIFICATION ENDPOINT (NEW ADDITION)
# -------------------------------------------------
@app.post("/notify-agent")
def notify_agent(data: dict):
    sender = data["sender_id"]
    message = data["message"]

    print("\n📢 HUMAN AGENT ALERT!")
    print(f"User ID   : {sender}")
    print(f"Message   : {message}")
    print("➡ A human agent needs to join this conversation.\n")

    # Later you can:
    # - Send email
    # - Notify WhatsApp group
    # - Push to admin dashboard
    # - Store in database

    return {"status": "Human agent notified"}


# -------------------------------------------------
# CHAT API (Frontend -> FastAPI -> Rasa)
# -------------------------------------------------
@app.post("/chat")
def chat_with_rasa(user_msg: UserMessage):

    rasa_url = "http://localhost:5005/webhooks/rest/webhook"
    original_msg = user_msg.message

    # Translate Hinglish → English
    try:
        translated_text = translator.translate(original_msg, src="auto", dest="en").text
    except Exception:
        translated_text = original_msg  # fallback

    print(f"\n🎤 USER SAID (Original): {original_msg}")
    print(f"🌐 Translated to English: {translated_text}")

    # Payload with UNIQUE sender ID
    payload = {
        "sender": user_msg.sender,
        "message": translated_text
    }

    try:
        response = requests.post(rasa_url, json=payload)
        rasa_messages = response.json()

        print("🤖 Raw Rasa Response:", rasa_messages)

        if response.status_code == 200:
            if rasa_messages:
                bot_replies = [msg.get("text", "") for msg in rasa_messages if "text" in msg]
                return {"bot_replies": bot_replies}
            else:
                return {"bot_replies": ["No response from bot."]}
        else:
            return {"bot_replies": [f"Error: Rasa returned {response.status_code}"]}

    except Exception as e:
        return {"bot_replies": [f"Error connecting to Rasa: {str(e)}"]}
