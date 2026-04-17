from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_config
from firebase_admin import auth

app = FastAPI()

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


# -------- ROUTES -------- #

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

        # create custom token
        custom_token = auth.create_custom_token(user_record.uid)

        return {
            "token": custom_token.decode("utf-8"),
            "name": user_record.display_name
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    

@app.get("/")
def home():
    return {"message": "API running"}