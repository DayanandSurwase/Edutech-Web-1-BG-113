from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from firebase_admin import auth
from uuid import uuid4
import firebase_config 

# Firestore DB from your config
db = firebase_config.db

app = FastAPI()

# -------- CORS -------- #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- MODELS -------- #
class UserSignup(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class Session(BaseModel):
    subject: str
    date: str
    duration: int


# -------- AUTH ROUTES -------- #

@app.post("/signup")
def signup(user: UserSignup):
    try:
        user_record = auth.create_user(
            email=user.email,
            password=user.password,
            display_name=user.name
        )

        return {"message": "User created", "uid": user_record.uid}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
def login(user: UserLogin):
    try:
        user_record = auth.get_user_by_email(user.email)

        custom_token = auth.create_custom_token(user_record.uid)

        return {
            "token": custom_token.decode("utf-8"),
            "name": user_record.display_name,
            "uid": user_record.uid
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")


# -------- SESSION ROUTES (FIREBASE) -------- #

@app.post("/sessions")
def create_session(session: Session):
    try:
        new_session = {
            "subject": session.subject,
            "date": session.date,
            "duration": session.duration
        }

        doc_ref = db.collection("sessions").add(new_session)

        return {
            "id": doc_ref[1].id,
            **new_session
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
def get_sessions():
    try:
        sessions = []
        docs = db.collection("sessions").stream()

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            sessions.append(data)

        return sessions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        db.collection("sessions").document(session_id).delete()
        return {"message": "Deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------- ROOT -------- #
@app.get("/")
def home():
    return {"message": "API running "}