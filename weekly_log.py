import smtplib
from email.message import EmailMessage
from pymongo import MongoClient
from datetime import date


# -------------------- CONFIG --------------------
MONGO_URI = st.secrets["API_KEY"]
GMAIL_USER = st.secrets["EMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = st.secrets["EMAIL_PASSWORD"]

RECIPIENTS = [
    "macari.agapito@brooklyn.cuny.edu",
    "fiona.chan71@brooklyn.cuny.edu",
    "pranat32@gmail.com"
]

# -------------------- FETCH DATA --------------------
client = MongoClient(MONGO_URI)
db = client["infoDB"]
col = db["Log_In"]

doc = col.find_one({})
if not doc:
    print("No weekly document found.")
    exit()

# -------------------- FORMAT EMAIL --------------------
text = f"Weekly Attendance Report\n"
text += f"Week: {doc['week_start']} → {doc['week_end']}\n\n"

for day, users in doc["logs"].items():
    text += f"{day}\n"
    for user, t in users.items():
        text += f"  {user}: {t.get('sign_in','—')} → {t.get('sign_out','—')}\n"
    text += "\n"

# -------------------- SEND EMAIL --------------------
msg = EmailMessage()
msg["Subject"] = "Weekly Attendance Report"
msg["From"] = GMAIL_USER
msg["To"] = ", ".join(RECIPIENTS)
msg.set_content(text)

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
    smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    smtp.send_message(msg)

print("Weekly email sent successfully.")

# -------------------- RESET WEEK --------------------
col.delete_many({})
print("Weekly logs cleared.")

