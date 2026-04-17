import os
import uuid
import requests as http_requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Any
from groq import Groq
import firebase_config
from firebase_admin import auth
from firebase_config import db
from auth import verify_token

# Load Groq key from Backend/.env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama3-8b-8192")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "Frontend")

FIREBASE_API_KEY = "AIzaSyAdMrUTEZ0oghKVzlxB0WCxwB1-5KZPRqw"

# -------- MODELS -------- #
class UserSignup(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class GoalCreate(BaseModel):
    text: str

class GoalUpdate(BaseModel):
    done: bool

class Session(BaseModel):
    subject: str
    date: str
    duration: int

class ChatRequest(BaseModel):
    message: str
    history: List[Any] = []
    context: dict = {}


# -------- AUTH ROUTES -------- #

@app.post("/signup")
def signup(user: UserSignup):
    try:
        res = http_requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}",
            json={"email": user.email, "password": user.password, "displayName": user.name, "returnSecureToken": True}
        )
        data = res.json()
        if "error" in data:
            raise HTTPException(status_code=400, detail=data["error"]["message"])
        return {"message": "User created", "uid": data["localId"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
def login(user: UserLogin):
    try:
        res = http_requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
            json={"email": user.email, "password": user.password, "returnSecureToken": True}
        )
        data = res.json()
        if "error" in data:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {
            "token": data["idToken"],
            "name": data.get("displayName", "")
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")


# -------- GOALS ROUTES -------- #

@app.get("/goals")
def get_goals(user=Depends(verify_token)):
    uid = user["uid"]
    docs = db.collection("users").document(uid).collection("goals").stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@app.post("/goals", status_code=201)
def add_goal(goal: GoalCreate, user=Depends(verify_token)):
    uid = user["uid"]
    goal_id = str(uuid.uuid4())
    data = {"text": goal.text, "done": False}
    db.collection("users").document(uid).collection("goals").document(goal_id).set(data)
    return {"id": goal_id, **data}


@app.patch("/goals/{goal_id}")
def update_goal(goal_id: str, update: GoalUpdate, user=Depends(verify_token)):
    uid = user["uid"]
    ref = db.collection("users").document(uid).collection("goals").document(goal_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Goal not found")
    ref.update({"done": update.done})
    return {"id": goal_id, **ref.get().to_dict()}


@app.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: str, user=Depends(verify_token)):
    uid = user["uid"]
    ref = db.collection("users").document(uid).collection("goals").document(goal_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Goal not found")
    ref.delete()


# -------- SESSION ROUTES -------- #

@app.post("/sessions")
def create_session(session: Session):
    try:
        data = {"subject": session.subject, "date": session.date, "duration": session.duration}
        doc_ref = db.collection("sessions").add(data)
        return {"id": doc_ref[1].id, **data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def get_sessions():
    try:
        docs = db.collection("sessions").stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        db.collection("sessions").document(session_id).delete()
        return {"message": "Deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------- AI CHAT (RAG) -------- #

@app.post("/chat")
def chat_with_ai(req: ChatRequest):
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise HTTPException(
            status_code=503,
            detail="Groq API key not configured. Add GROQ_API_KEY to Backend/.env"
        )
    try:
        ctx = req.context

        # Build goals text
        goals = ctx.get("goals", [])
        if goals:
            goals_text = "\n".join(
                f"  - {'[DONE]' if g.get('done') else '[PENDING]'} {g.get('text', '')}"
                for g in goals
            )
        else:
            goals_text = "  No goals set yet."

        # Build progress text
        progress = ctx.get("progress", {})
        if progress:
            progress_text = "\n".join(
                f"  - {subject}: {score}%" for subject, score in progress.items()
            )
        else:
            progress_text = "  No progress data yet."

        # Build sessions text (fetch from Firestore)
        try:
            docs = db.collection("sessions").stream()
            sessions = [doc.to_dict() for doc in docs]
            if sessions:
                sessions_text = "\n".join(
                    f"  - {s.get('subject')} on {s.get('date')} ({s.get('duration')} min)"
                    for s in sessions[:10]  
                )
            else:
                sessions_text = "  No sessions planned yet."
        except Exception:
            sessions_text = "  Could not load sessions."

        system_prompt = f"""You are StudyPro AI, a smart and encouraging personal study assistant.
Here is the student's current data:

- Name: {ctx.get('name', 'Student')}
- Skill Level: {ctx.get('skillLevel', 'Intermediate')}
- Interests: {', '.join(ctx.get('interests', [])) or 'Not set'}
- Study Streak: {ctx.get('streak', 0)} days

Goals:
{goals_text}

Subject Progress:
{progress_text}

Upcoming Study Sessions:
{sessions_text}

Instructions:
- Answer based on the student's actual data shown above.
- Be encouraging, specific, and concise (2-4 sentences unless more detail is needed).
- If asked for a study plan, focus on weak subjects (lowest scores) and their interests.
- Do NOT say you are an AI or mention your model name; stay in role as StudyPro AI."""

        # Build Groq messages array
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (exclude the very last entry which is the current message)
        for h in req.history[:-1]:
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("text", "")})

        # Current user message
        messages.append({"role": "user", "content": req.message})

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )

        reply = response.choices[0].message.content
        return {"reply": reply}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------- FRONTEND STATIC SERVING -------- #

@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
