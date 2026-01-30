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
    password=st.secrets["COOKIE_PASSWORD"]  # YOU set this
)

if not cookies.ready():
    st.stop()

# -------------------- MongoDB --------------------
client = MongoClient(st.secrets["API_KEY"])
db = client["infoDB"]
weekly_col = db["Log_In"]
allowed_devices = db["allowed_devices"]

# -------------------- DEVICE AUTH --------------------
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
        {f"logs.{today}.{username}.sign_in": 1}
    )
    return bool(
        doc and doc.get("logs", {}).get(today, {}).get(username, {}).get("sign_in")
    )

def sign_in(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    weekly_col.update_one(
        {"week_start": week_start},
        {"$set": {f"logs.{today}.{username}.sign_in": datetime.now()}},
        upsert=True
    )

def sign_out(username):
    week_start, _ = get_weekbounds()
    today = str(date.today())
    weekly_col.update_one(
        {"week_start": week_start},
        {"$set": {f"logs.{today}.{username}.sign_out": datetime.now()}},
        upsert=True
    )

ensure_week_doc()

# -------------------- UI --------------------
st.title("Workplace Time Logger")

username = st.text_input("Username")

if st.button("Sign In"):
    if not username:
        st.warning("Enter a valid username.")
    elif already_signed_in(username):
        st.warning("You are already signed in!")
    else:
        sign_in(username)
        st.success("You are signed in.")

if st.button("Sign Out"):
    if not username:
        st.warning("Enter a valid username.")
    else:
        sign_out(username)
        st.success("You are signed out.")

st.caption(f"Device ID: {device_id}")
