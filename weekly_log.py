import os
from pymongo import MongoClient
from datetime import datetime
from email.message import EmailMessage
import smtplib
from docx import Document
from io import BytesIO
import sys

# ==========================
# CONFIGURATION (ENV VARIABLES)
# ==========================
try:
MONGO_URI = os.environ["MONGO_URI"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAILS = [e.strip() for e in os.environ["RECIPIENT_EMAILS"].split(",")]
except KeyError as e:
print(f"Missing required environment variable: {e}")
sys.exit(1)

DB_NAME = os.environ.get("DB_NAME", "infoDB")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "Log_In")

# ==========================
# CONNECT TO MONGO
# ==========================
print("Connecting to MongoDB...")

try:
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db[COLLECTION_NAME]
except Exception as e:
print("MongoDB connection failed:", e)
sys.exit(1)

# ==========================
# FETCH LATEST LOG DOCUMENT
# ==========================
doc = col.find_one(sort=[("_id", -1)])

if not doc or not doc.get("logs"):
print("No logs found. Exiting.")
sys.exit(0)

logs = doc["logs"]
week_start = doc.get("week_start", min(logs.keys()))
week_end = doc.get("week_end", max(logs.keys()))

print(f"Generating report for {week_start} -> {week_end}")

# ==========================
# BUILD REPORT TEXT
# ==========================
lines = []
lines.append("Weekly Attendance Report")
lines.append(f"Week: {week_start} -> {week_end}")
lines.append("")

for day in sorted(logs.keys()):
lines.append(f"{day}")
users = logs[day]

for user, t in users.items():
sign_in = t.get("sign_in", "-")
sign_out = t.get("sign_out", "-")
lines.append(f" {user}: {sign_in} -> {sign_out}")

lines.append("")

text = "\n".join(lines)

# ==========================
# BUILD DOCX IN MEMORY
# ==========================
doc_buffer = BytesIO()

document = Document()
for line in lines:
document.add_paragraph(line)

document.save(doc_buffer)
doc_buffer.seek(0)

print("DOCX generated in memory")

# ==========================
# SEND EMAIL
# ==========================
msg = EmailMessage()
msg["Subject"] = "Weekly Attendance Report"
msg["From"] = GMAIL_USER
msg["To"] = ", ".join(RECIPIENT_EMAILS)

msg.set_content(text)

msg.add_attachment(
doc_buffer.read(),
maintype="application",
subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
filename=f"weekly_report_{week_start}_to_{week_end}.docx"
)

#print("Sending email...")

try:
with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
server.send_message(msg)

#print("Email sent successfully!")

except Exception as e:
print("Failed to send email:", e)
sys.exit(1)

# ==========================
# DONE
# ==========================
#print(f"{datetime.now()}: Weekly report completed.")
