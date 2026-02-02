import os
from pymongo import MongoClient
import smtplib
from email.message import EmailMessage
from datetime import date

# --------- CONNECT TO MONGO ----------
MONGO_URI = os.environ.get("MONGO_URI")   # cron-job will provide this

client = MongoClient(MONGO_URI)
db = client["infoDB"]
col = db["Log_In"]

doc = col.find_one({})

if not doc:
    print("No weekly document found. Nothing to email.")
    exit()

# --------- BUILD EMAIL TEXT ----------
text = f"Weekly Attendance Report\n"
text += f"Week: {doc['week_start']} → {doc['week_end']}\n\n"

for day, users in doc.get("logs", {}).items():
    text += f"{day}\n"
    for user, t in users.items():
        text += f"  {user}: {t.get('sign_in','—')} → {t.get('sign_out','—')}\n"
    text += "\n"

# --------- SEND EMAIL VIA GMAIL SMTP ----------
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

msg = EmailMessage()
msg["Subject"] = "Weekly Attendance Report"
msg["From"] = GMAIL_USER
msg["To"] = "macari.agapito@brooklyn.cuny.edu, fiona.chan71@brooklyn.cuny.edu"
msg.set_content(text)

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    server.send_message(msg)

print("Email sent successfully!")

# --------- RESET WEEK ----------
col.delete_many({})
print("Old logs cleared.")
