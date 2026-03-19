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
import re
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

pd.set_option('future.no_silent_downcasting', True)

# -------------------- PAGE CONFIG --------------------
st.set_page_config(
    page_title="Workplace Time Logger",
    page_icon="🕐",
    layout="centered"
)

# -------------------- TIMEZONE --------------------
TZ = ZoneInfo("America/New_York")

def now():
    return datetime.now(TZ)

def today_date():
    return now().date()

def today_str():
    return str(today_date())

# -------------------- REAL MAC DETECTION --------------------
def get_real_mac():
    """
    Get the real hardware MAC address cross-platform.
    Filters out virtual/Hyper-V/VMware/Bluetooth adapters on Windows.
    Falls back to uuid.getnode() only as a last resort.
    """
    try:
        if sys.platform == "win32":
            output = subprocess.check_output("ipconfig /all", shell=True).decode(errors="ignore")
            lines  = output.splitlines()
            real_macs = []
            for i, line in enumerate(lines):
                if "Physical Address" in line:
                    # Look back up to 10 lines for the adapter name
                    skip = False
                    for j in range(max(0, i - 10), i):
                        if any(kw in lines[j] for kw in (
                            "Hyper-V", "VirtualBox", "VMware",
                            "Loopback", "Bluetooth", "Tunnel"
                        )):
                            skip = True
                            break
                    if not skip:
                        mac = re.search(r"([0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}"
                                        r"[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2})", line)
                        if mac:
                            real_macs.append(mac.group().replace("-", ":").lower())
            if real_macs:
                return real_macs[0]

        elif sys.platform == "darwin":
            output = subprocess.check_output(["ifconfig", "en0"]).decode()
            mac = re.search(r"ether\s+([0-9a-f:]{17})", output)
            if mac:
                return mac.group(1)

        else:
            # Linux
            output = subprocess.check_output(["ip", "link", "show"]).decode()
            macs = re.findall(r"link/ether\s+([0-9a-f:]{17})", output)
            if macs:
                return macs[0]

    except Exception:
        pass

    # Last resort fallback
    return hex(uuid.getnode())


# -------------------- EMBEDDED MAC AGENT --------------------
AGENT_PORT = 9877

def start_mac_agent():
    MAC_ADDRESS = get_real_mac()

    class MACHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(MAC_ADDRESS.encode())

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", AGENT_PORT), MACHandler)
    server.serve_forever()

def ensure_agent_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        already_up = s.connect_ex(("localhost", AGENT_PORT)) == 0
    if not already_up:
        t = threading.Thread(target=start_mac_agent, daemon=True)
        t.start()

ensure_agent_running()

# -------------------- MAC AGENT CLIENT --------------------
def get_device_mac():
    """
    Calls the local MAC agent on localhost.
    Retries a few times to allow the thread to finish binding.
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

# -------------------- Device Helpers --------------------
def user_exists(username):
    return bool(users_col.find_one({"username": username}))

def is_device_allowed(mac: str) -> bool:
    return bool(allowed_devices.find_one({"device_id": mac, "active": True}))

def is_admin(username: str, password: str) -> bool:
    """Check admin credentials. User must have is_admin: True in the users collection."""
    user = users_col.find_one({"username": username, "is_admin": True})
    if not user:
        return False
    # Plain comparison — swap for bcrypt if you store hashed passwords
    return user.get("password") == password

def get_pending_devices():
    return list(allowed_devices.find({"active": False}))

def get_approved_devices():
    return list(allowed_devices.find({"active": True}))

def approve_device(mac: str, label: str = ""):
    allowed_devices.update_one(
        {"device_id": mac},
        {"$set": {"active": True, "approved_at": now(), "label": label}},
    )

def reject_device(mac: str):
    allowed_devices.delete_one({"device_id": mac})

def revoke_device(mac: str):
    allowed_devices.update_one(
        {"device_id": mac},
        {"$set": {"active": False, "revoked_at": now()}}
    )

def register_device_request(mac: str, pc_name: str):
    """Insert a pending registration if not already present."""
    existing = allowed_devices.find_one({"device_id": mac})
    if existing:
        return "already_exists"
    allowed_devices.insert_one({
        "device_id":    mac,
        "pc_name":      pc_name,
        "active":       False,
        "requested_at": now(),
        "label":        ""
    })
    return "requested"

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

# -------------------- GET THIS MACHINE'S MAC --------------------
device_mac = get_device_mac()

# -------------------- NAVIGATION --------------------
page = st.sidebar.selectbox(
    "Navigate",
    ["🕐 Time Logger", "📋 Register This PC", "🔐 Admin Panel"]
)

# ====================================================================
# PAGE 1 — TIME LOGGER
# ====================================================================
if page == "🕐 Time Logger":
    st.title("🕐 Workplace Time Logger")

    if device_mac is None:
        st.error("⚠️ Could not detect MAC address on this machine.")
        st.stop()

    if not is_device_allowed(device_mac):
        st.warning("🚫 This PC is not authorised yet.")
        st.info(
            "Go to **📋 Register This PC** in the sidebar to submit an access request. "
            "Once an admin approves it, you will be able to log in."
        )
        st.stop()

    username = st.text_input("Username")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ Sign In", use_container_width=True):
            if not username:
                st.warning("Enter a valid username.")
            elif not user_exists(username):
                st.error("User not found in system.")
            elif already_signed_in(username):
                st.warning("You are already signed in!")
            else:
                sign_in(username)
                st.success("You are signed in.")

    with col2:
        if st.button("🚪 Sign Out", use_container_width=True):
            if not username:
                st.warning("Enter a valid username.")
            elif not user_exists(username):
                st.error("User not found in system.")
            elif not already_signed_in(username):
                st.warning("You must sign in before signing out.")
            else:
                sign_out(username)
                st.success("You are signed out.")

    st.markdown("---")
    st.caption(f"Device MAC: {device_mac}")
    st.markdown(
        "Trouble logging in? Contact the lead developer at: pranat32@gmail.com"
    )

# ====================================================================
# PAGE 2 — REGISTER THIS PC
# ====================================================================
elif page == "📋 Register This PC":
    st.title("📋 Register This PC")

    if device_mac is None:
        st.error("⚠️ Could not detect the MAC address of this machine.")
        st.stop()

    existing = allowed_devices.find_one({"device_id": device_mac})

    if existing and existing.get("active"):
        st.success("✅ This PC is already approved and authorised.")
        st.caption(f"MAC: {device_mac}")
        st.stop()

    if existing and not existing.get("active"):
        st.info("⏳ A registration request for this PC is already pending admin approval.")
        st.caption(f"MAC: {device_mac}")
        st.markdown("Ask your administrator to check the **Admin Panel** and approve this device.")
        st.stop()

    st.markdown(
        "This PC is not yet registered. Fill in the details below to request access. "
        "An admin will approve or reject your request from the Admin Panel."
    )

    with st.form("register_form"):
        pc_name   = st.text_input(
            "PC / Workstation Name",
            placeholder="e.g. Reception Desk, John's Laptop"
        )
        submitted = st.form_submit_button("Submit Access Request", use_container_width=True)

    if submitted:
        if not pc_name.strip():
            st.warning("Please enter a name for this PC.")
        else:
            result = register_device_request(device_mac, pc_name.strip())
            if result == "requested":
                st.success(
                    "✅ Request submitted! An admin will review it shortly. "
                    "Come back to this page to check your approval status."
                )
            elif result == "already_exists":
                st.info("A request for this device already exists.")

    st.markdown("---")
    st.caption(f"Your MAC address: `{device_mac}`")

# ====================================================================
# PAGE 3 — ADMIN PANEL
# ====================================================================
elif page == "🔐 Admin Panel":
    st.title("🔐 Admin Panel")

    # ---- Login gate ----
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if not st.session_state.admin_logged_in:
        st.subheader("Admin Login")
        with st.form("admin_login"):
            admin_user = st.text_input("Admin Username")
            admin_pass = st.text_input("Admin Password", type="password")
            login_btn  = st.form_submit_button("Login", use_container_width=True)

        if login_btn:
            if is_admin(admin_user, admin_pass):
                st.session_state.admin_logged_in = True
                st.session_state.admin_username  = admin_user
                st.rerun()
            else:
                st.error("Invalid admin credentials.")
        st.stop()

    # ---- Admin is logged in ----
    st.success(f"Logged in as **{st.session_state.admin_username}**")

    if st.button("Logout"):
        st.session_state.admin_logged_in = False
        st.rerun()

    st.markdown("---")

    # ---- Pending Requests ----
    st.subheader("⏳ Pending Device Requests")
    pending = get_pending_devices()

    if not pending:
        st.info("No pending requests.")
    else:
        for device in pending:
            mac      = device.get("device_id", "N/A")
            pc_name  = device.get("pc_name", "Unknown")
            req_time = device.get("requested_at", "N/A")

            with st.container(border=True):
                col_info, col_label, col_btns = st.columns([2, 2, 1.5])

                with col_info:
                    st.markdown(f"**{pc_name}**")
                    st.caption(f"MAC: `{mac}`")
                    st.caption(f"Requested: {req_time}")

                with col_label:
                    label = st.text_input(
                        "Label (optional)",
                        placeholder="e.g. Front Desk",
                        key=f"label_{mac}"
                    )

                with col_btns:
                    st.write("")
                    if st.button("✅ Approve", key=f"approve_{mac}", use_container_width=True):
                        approve_device(mac, label)
                        st.success(f"Approved: {mac}")
                        st.rerun()
                    if st.button("❌ Reject", key=f"reject_{mac}", use_container_width=True):
                        reject_device(mac)
                        st.warning(f"Rejected & removed: {mac}")
                        st.rerun()

    st.markdown("---")

    # ---- Approved Devices ----
    st.subheader("✅ Approved Devices")
    approved = get_approved_devices()

    if not approved:
        st.info("No approved devices yet.")
    else:
        for device in approved:
            mac         = device.get("device_id", "N/A")
            label       = device.get("label") or device.get("pc_name", "Unlabelled")
            approved_at = device.get("approved_at", "N/A")

            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])

                with col_info:
                    st.markdown(f"**{label}**")
                    st.caption(f"MAC: `{mac}`")
                    st.caption(f"Approved: {approved_at}")

                with col_btn:
                    st.write("")
                    if st.button("🚫 Revoke", key=f"revoke_{mac}", use_container_width=True):
                        revoke_device(mac)
                        st.warning(f"Revoked: {mac}")
                        st.rerun()

    st.markdown("---")

    # ---- Add Device Manually ----
    st.subheader("➕ Add Device Manually")
    st.caption("Use this if a PC cannot run the app to self-register.")

    with st.form("manual_add"):
        manual_mac   = st.text_input("MAC Address", placeholder="e.g. aa:bb:cc:dd:ee:ff")
        manual_label = st.text_input("Label", placeholder="e.g. Server Room PC")
        add_btn      = st.form_submit_button("Add & Approve", use_container_width=True)

    if add_btn:
        if not manual_mac.strip():
            st.warning("Enter a MAC address.")
        else:
            existing = allowed_devices.find_one({"device_id": manual_mac.strip()})
            if existing:
                st.warning("This MAC is already in the system.")
            else:
                allowed_devices.insert_one({
                    "device_id":    manual_mac.strip(),
                    "pc_name":      manual_label.strip() or "Manual Entry",
                    "label":        manual_label.strip(),
                    "active":       True,
                    "approved_at":  now(),
                    "requested_at": now()
                })
                st.success(f"✅ Device `{manual_mac.strip()}` added and approved.")
                st.rerun()
