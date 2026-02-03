import os
from pymongo import MongoClient
from datetime import datetime
from email.message import EmailMessage
import smtplib
from docx import Document

# ==========================
# CONFIGURATION
# ==========================
MONGO_URI = os.environ['MONGO_URI']
DB_NAME = os.environ.get('DB_NAME')
COLLECTION_NAME = os.environ.get("COLLECTION_NAME")

GMAIL_USER = os.environ['GMAIL_USER']
GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']
RECIPIENT_EMAILS = os.environ['RECIPIENT_EMAILS'].split(",")
LOG_FILE = "weekly_report.log"
DOCX_FILE = "weekly_report.docx"

# ==========================
# CONNECT TO MONGO
# ==========================
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db[COLLECTION_NAME]

# Get the latest weekly document
doc = col.find_one(sort=[("_id", -1)])

if not doc or not doc.get("logs"):
    print("No logs found. Exiting.")
    exit()

logs = doc["logs"]
week_start = doc.get("week_start", min(logs.keys()))
week_end = doc.get("week_end", max(logs.keys()))

# ==========================
# BUILD REPORT TEXT
# ==========================
lines = []
lines.append(f"Weekly Attendance Report")
lines.append(f"Week: {week_start} -> {week_end}\n")  # ASCII arrow

for day in sorted(logs.keys()):
    lines.append(f"{day}")
    users = logs[day]
    for user, t in users.items():
        lines.append(f"  {user}: {t.get('sign_in','-')} -> {t.get('sign_out','-')}")
    lines.append("")  # empty line

text = "\n".join(lines)

# ==========================
# WRITE DOCX
# ==========================
document = Document()
for line in lines:
    document.add_paragraph(line)
document.save(DOCX_FILE)
#print(f"DOCX created: {DOCX_FILE}")

# ==========================
# SEND EMAIL VIA GMAIL SMTP
# ==========================
msg = EmailMessage()
msg["Subject"] = "Weekly Attendance Report"
msg["From"] = GMAIL_USER
msg["To"] = ", ".join(RECIPIENT_EMAILS)
msg.set_content(text)

# Attach DOCX
with open(DOCX_FILE, "rb") as f:
    msg.add_attachment(f.read(), maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=DOCX_FILE)

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    #print("Email sent successfully with DOCX attachment!")
except Exception as e:
    #print("Failed to send email:", e)

# ==========================
# OPTIONAL LOGGING
# ==========================
try:
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: Weekly report sent for {week_start} -> {week_end}\n")
except Exception as e:
    #print("Failed to write log:", e)
