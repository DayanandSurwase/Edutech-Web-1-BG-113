import requests as http_requests
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
import firebase_config
from firebase_admin import auth
from firebase_config import db
from auth import verify_token

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- MODELS -------- #
FIREBASE_API_KEY = "AIzaSyAdMrUTEZ0oghKVzlxB0WCxwB1-5KZPRqw"  # Replace with your key from Firebase Console → Project Settings

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




# -------- ROUTES -------- #

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
    

@app.get("/")
def home():
    return {"message": "API running"}


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