# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse
# from fastapi.templating import Jinja2Templates
# from fastapi.staticfiles import StaticFiles
# from pydantic import BaseModel
# import requests

# # Create FastAPI app
# app = FastAPI()

# # Mount static folder (optional for images/css)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# # Load HTML templates folder
# templates = Jinja2Templates(directory="templates")


# # Pydantic model for incoming user messages
# class UserMessage(BaseModel):
#     message: str
#     sender: str = "user"  # optional sender name


# # Home route (renders chat UI)
# @app.get("/", response_class=HTMLResponse)
# def get_chat_page(request: Request):
#     return templates.TemplateResponse("chat.html", {"request": request})


# # API route that connects to Rasa backend
# @app.post("/chat")
# def chat_with_rasa(user_msg: UserMessage):
#     rasa_url = "http://localhost:5005/webhooks/rest/webhook"

#     payload = {
#         "sender": user_msg.sender,
#         "message": user_msg.message
#     }

#     # Send message to Rasa server
#     try:
#         response = requests.post(rasa_url, json=payload)
#         if response.status_code == 200:
#             messages = response.json()
#             if messages:
#                 bot_reply = messages[0].get("text", "No reply from bot")
#                 return {"bot_reply": bot_reply}
#             else:
#                 return {"bot_reply": "No response from bot"}
#         else:
#             return {"error": "Failed to connect to Rasa server"}
#     except Exception as e:
#         return {"error": str(e)}

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

# Create FastAPI app
app = FastAPI()

# Allow frontend (HTML) to connect to FastAPI (avoid CORS issues)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can replace "*" with specific domain if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder (for CSS, JS, images)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates folder for HTML
templates = Jinja2Templates(directory="templates")


# Define structure of incoming user message
class UserMessage(BaseModel):
    message: str
    sender: str = "user"


# Home route to serve chatbot UI
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


# Chat route: receives message → sends to Rasa → returns response
@app.post("/chat")
def chat_with_rasa(user_msg: UserMessage):
    rasa_url = "http://localhost:5005/webhooks/rest/webhook"
    payload = {
        "sender": user_msg.sender,
        "message": user_msg.message
    }

    try:
        # Send request to Rasa backend
        response = requests.post(rasa_url, json=payload)
        print("🧩 Raw Rasa Response:", response.json())  # Debug print for backend check

        if response.status_code == 200:
            messages = response.json()
            if messages:
                # Handle multiple text messages (Rasa may send several)
                bot_replies = [msg.get("text", "") for msg in messages if "text" in msg]
                return {"bot_replies": bot_replies}
            else:
                return {"bot_replies": ["No response from bot."]}
        else:
            return {"bot_replies": [f"Error: Rasa server returned {response.status_code}"]}
    except Exception as e:
        return {"bot_replies": [f"Error connecting to Rasa: {str(e)}"]}
