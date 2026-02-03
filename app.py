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

# -------------------- LOGGING LOGIC --------------------
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

def already_signed_in(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())

    doc = weekly_col.find_one(
        {"week_start": week_start},
        {f"logs.{today}.{username}": 1}
    )

    # Safely get the list of sessions for today
    sessions = (
        doc.get("logs", {})
        .get(today, {})
        .get(username, [])
        if doc else []
    )

    # If the list is empty or the last entry has a sign_out, they are NOT signed in.
    if not sessions or not isinstance(sessions, list):
        return False
    
    last_session = sessions[-1]
    return "sign_in" in last_session and "sign_out" not in last_session


def sign_in(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    new_entry = {"sign_in": datetime.now()}
    
    # Use $push to add a NEW pair to the list instead of overwriting
    weekly_col.update_one(
        {"week_start": week_start},
        {"$push": {f"logs.{today}.{username}": new_entry}},
        upsert=True
    )

def sign_out(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    
    # Updates the last session in the list that doesn't have a sign_out yet
    weekly_col.update_one(
        {"week_start": week_start},
        {"$set": {f"logs.{today}.{username}.$[last].sign_out": datetime.now()}},
        array_filters=[{"last.sign_out": {"$exists": False}}],
        upsert=True
    )

ensure_week_doc()

# -------------------- UI --------------------
st.title("Workplace Time Logger")

username = st.text_input("Username")

if st.button("Sign In"):
    if not username:
        st.warning("Enter a valid username.")
    elif not user_exists(username):           
        st.error("User not found in system.")
    elif already_signed_in(username):
        st.warning("You are already signed in!")
    else:
        sign_in(username)
        st.success("You are signed in.")


if st.button("Sign Out"):
    if not username:
        st.warning("Enter a valid username.")
    elif not user_exists(username):           
        st.error("User not found in system.")
    elif not already_signed_in(username):
        st.warning("You are not signed in or already signed out.")
    else:
        sign_out(username)
        st.success("You are signed out.")

st.caption(f"Device ID: {device_id}")

st.markdown("------")
st.markdown("If you have any trouble logging in or out, or would like to report any bugs. Reach out to the lead developer at: pranat32@gmail.com")
