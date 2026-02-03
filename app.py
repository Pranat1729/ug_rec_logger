import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, date, timedelta
import uuid
from streamlit_cookies_manager import EncryptedCookieManager

pd.set_option('future.no_silent_downcasting', True)

# -------------------- COOKIES --------------------
cookies = EncryptedCookieManager(
    prefix="work_auth",
    password=st.secrets["COOKIE_PASSWORD"]  
)

if not cookies.ready():
    st.stop()

# -------------------- MongoDB --------------------
client = MongoClient(st.secrets["API_KEY"])
db = client["infoDB"]
users_col = db["users"]
weekly_col = db["Log_In"]
allowed_devices = db["allowed_devices"]

# -------------------- DEVICE AUTH --------------------
def user_exists(username):
    return bool(users_col.find_one({"username": username}))
    
def get_device_id():
    if "device_id" not in cookies:
        cookies["device_id"] = str(uuid.uuid4())
        cookies.save()
    return cookies["device_id"]

def is_device_allowed(device_id):
    return bool(
        allowed_devices.find_one({
            "device_id": device_id,
            "active": True
        })
    )

device_id = get_device_id()

if not is_device_allowed(device_id):
    st.error("This computer is not authorized to access this system.")
    st.info("Provide the following ID to the administrator:")
    st.code(device_id)
    st.stop()


def get_weekbounds():
    today = date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return str(start), str(end)

def ensure_week_doc():
    week_start, week_end = get_weekbounds()
    if not weekly_col.find_one({"week_start": week_start}):
        weekly_col.insert_one({
            "week_start": week_start,
            "week_end": week_end,
            "logs": {}
        })

def get_user_sessions(username):
    """Helper to fetch the list of sessions for today."""
    week_start, _ = get_weekbounds()
    today = str(date.today())
    
    doc = weekly_col.find_one(
        {"week_start": week_start},
        {f"logs.{today}.{username}": 1}
    )

    return doc.get("logs", {}).get(today, {}).get(username, []) if doc else []

def is_currently_signed_in(username):
    sessions = get_user_sessions(username)
    if not sessions:
        return False
  
    last_session = sessions[-1]
    return "sign_out" not in last_session

def sign_in(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    new_session = {"sign_in": datetime.now()}
    
  
    weekly_col.update_one(
        {"week_start": week_start},
        {"$push": {f"logs.{today}.{username}": new_session}},
        upsert=True
    )

def sign_out(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    

    weekly_col.update_one(
        {"week_start": week_start},
        {"$set": {f"logs.{today}.{username}.$[last].sign_out": datetime.now()}},
        array_filters=[{"last": {"$exists": True}}], # Basic filter to target elements
        upsert=True
    )
    

ensure_week_doc()

# -------------------- UI --------------------
st.title("Workplace Time Logger")

username = st.text_input("Username").strip()

col1, col2 = st.columns(2)

with col1:
    if st.button("Sign In", use_container_width=True):
        if not username:
            st.warning("Enter a valid username.")
        elif not user_exists(username):           
            st.error("User not found in system.")
        elif is_currently_signed_in(username):
            st.warning("You are already signed in! Please sign out first.")
        else:
            sign_in(username)
            st.success(f"Sign-in recorded for {username}.")

with col2:
    if st.button("Sign Out", use_container_width=True):
        if not username:
            st.warning("Enter a valid username.")
        elif not user_exists(username):           
            st.error("User not found in system.")
        elif not is_currently_signed_in(username):
            st.warning("You are not currently signed in.")
        else:
            sign_out(username)
            st.success(f"Sign-out recorded for {username}.")

st.caption(f"Device ID: {device_id}")

st.markdown("------")
st.markdown("If you have any trouble logging in or out, reach out to the lead developer at: pranat32@gmail.com")
