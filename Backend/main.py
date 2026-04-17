import os
import uuid
import requests as http_requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import firebase_config
from firebase_admin import auth
from firebase_config import db
from auth import verify_token

load_dotenv()

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

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")

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


# -------- FRONTEND STATIC SERVING -------- #

@app.get("/")
def home():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")
