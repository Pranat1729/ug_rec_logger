import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid
from streamlit_cookies_manager import EncryptedCookieManager

pd.set_option('future.no_silent_downcasting', True)

# -------------------- TIMEZONE --------------------
TZ = ZoneInfo("America/New_York")

def now():
    return datetime.now(TZ)

def today_date():
    return now().date()

def today_str():
    return str(today_date())

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

# -------------------- Auser --------------------
def user_exists(username):
    return bool(users_col.find_one({"username": username}))

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


def get_weekbounds():
    today = today_date()
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
    today = today_str()

    doc = weekly_col.find_one({"week_start": week_start})
    if not doc:
        return False

    user_logs = doc.get("logs", {}).get(today, {}).get(username, [])

    if isinstance(user_logs, list) and len(user_logs) > 0:
        last_session = user_logs[-1]
        return "sign_in" in last_session and "sign_out" not in last_session

    return False

def sign_in(username):
    week_start, _ = get_weekbounds()
    today = today_str()

    weekly_col.update_one(
        {"week_start": week_start},
        {"$push": {f"logs.{today}.{username}": {"sign_in": now()}}},
        upsert=True
    )

def sign_out(username):
    week_start, _ = get_weekbounds()
    today = today_str()

    weekly_col.update_one(
        {"week_start": week_start},
        {"$set": {f"logs.{today}.{username}.$[last].sign_out": now()}},
        array_filters=[{"last.sign_out": {"$exists": False}}]
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
        st.warning("You must sign in before you can sign out.")
    else:
        sign_out(username)
        st.success("You are signed out.")

st.caption(f"Device ID: {device_id}")
st.markdown("------")
st.markdown("If you have any trouble logging in or out, or would like to report any bugs. Reach out to the lead developer at: pranat32@gmail.com")
