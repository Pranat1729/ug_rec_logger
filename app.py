import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
import uuid
import threading
import socket
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

pd.set_option('future.no_silent_downcasting', True)

# -------------------- TIMEZONE --------------------
TZ = ZoneInfo("America/New_York")

def now():
    return datetime.now(TZ)

def today_date():
    return now().date()

def today_str():
    return str(today_date())

# -------------------- EMBEDDED MAC AGENT --------------------
AGENT_PORT = 9877

def start_mac_agent():
    MAC_ADDRESS = hex(uuid.getnode())

    class MACHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(MAC_ADDRESS.encode())

        def log_message(self, format, *args):
            pass  # silence server logs

    server = HTTPServer(("localhost", AGENT_PORT), MACHandler)
    server.serve_forever()

def ensure_agent_running():
    """Launch the MAC agent in a background daemon thread if not already running."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        already_up = s.connect_ex(("localhost", AGENT_PORT)) == 0

    if not already_up:
        t = threading.Thread(target=start_mac_agent, daemon=True)
        t.start()

# Start agent before anything else
ensure_agent_running()

# -------------------- MAC AGENT CLIENT --------------------
def get_device_mac():
    """
    Calls the local MAC agent running on localhost.
    Retries a few times to allow the thread to finish binding.
    Returns the MAC address string, or None if unreachable.
    """
    for _ in range(5):
        try:
            r = requests.get(f"http://localhost:{AGENT_PORT}", timeout=1)
            if r.status_code == 200:
                return r.text.strip()
        except Exception:
            time.sleep(0.2)
    return None

# -------------------- MongoDB --------------------
client = MongoClient(st.secrets["API_KEY"])
db = client["infoDB"]

users_col       = db["users"]
weekly_col      = db["Log_In"]
allowed_devices = db["allowed_devices"]

# -------------------- Helpers --------------------
def user_exists(username):
    return bool(users_col.find_one({"username": username}))

def is_device_allowed(mac: str) -> bool:
    return bool(
        allowed_devices.find_one({
            "device_id": mac,
            "active": True
        })
    )

# -------------------- Device Gate --------------------
device_mac = get_device_mac()

if device_mac is None:
    st.error("⚠️ MAC agent could not be started on this machine.")
    st.info("Try restarting the app. If the issue persists, contact your administrator.")
    st.stop()

if not is_device_allowed(device_mac):
    st.error("🚫 This computer is not authorised to access this system.")
    st.info("Provide the following MAC address to your administrator so they can whitelist this PC:")
    st.code(device_mac)
    st.stop()

# -------------------- Week Helpers --------------------
def get_weekbounds():
    today = today_date()
    start = today - timedelta(days=today.weekday())
    end   = start + timedelta(days=6)
    return str(start), str(end)

def ensure_week_doc():
    week_start, week_end = get_weekbounds()
    if not weekly_col.find_one({"week_start": week_start}):
        weekly_col.insert_one({
            "week_start": week_start,
            "week_end":   week_end,
            "logs":       {}
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
        st.success("✅ You are signed in.")

if st.button("Sign Out"):
    if not username:
        st.warning("Enter a valid username.")
    elif not user_exists(username):
        st.error("User not found in system.")
    elif not already_signed_in(username):
        st.warning("You must sign in before you can sign out.")
    else:
        sign_out(username)
        st.success("✅ You are signed out.")

st.caption(f"Device MAC: {device_mac}")
st.markdown("------")
st.markdown(
    "If you have any trouble logging in or out, or would like to report any bugs, "
    "reach out to the lead developer at: pranat32@gmail.com"
)
