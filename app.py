import os
import re
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time, timedelta, date
from openpyxl import Workbook
from dotenv import load_dotenv
import streamlit as st
from typing import Callable, Dict
from twilio.rest import Client

#source raga/Scripts/activate
PATIENT_FILE = "patients.csv"
SCHEDULE_FILE = "schedule.xlsx"
FINAL_FILE = "final.xlsx"

SLOT_START = time(10, 0)
SLOT_END = time(21, 0)
SLOT_STEP_MIN = 30


NEW_PATIENT_DURATION = 60  # minutes
RECURRING_PATIENT_DURATION = 30  # minutes

DOCTORS = ["Dr. Smith", "Dr. Johnson", "Dr. Lee"]
LOCATIONS = ["Main Clinic", "Downtown Office", "Uptown Branch"]

load_dotenv()


EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587


SMS_ENABLED = os.getenv("ENABLE_SMS", "true").lower() == "true"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE", "")
PATIENT_NOTIFY_PHONE = os.getenv("PATIENT_NOTIFY_PHONE", "")


def ensure_files():
    if not os.path.exists(PATIENT_FILE):
        pd.DataFrame(columns=["name", "dob", "email", "phone"]).to_csv(PATIENT_FILE, index=False)
    if not os.path.exists(SCHEDULE_FILE):
        wb = Workbook()
        ws = wb.active
        ws.title = "Schedule"
        ws.append(["date", "time", "patient", "duration", "patient_type"])
        wb.save(SCHEDULE_FILE)
    if not os.path.exists(FINAL_FILE):
        cols = [
            "name","dob","email","phone","date","time","duration","patient_type","doctor","location",
            "insurance_carrier","member_id","group_number","confirmed","notes"
        ]
        pd.DataFrame(columns=cols).to_excel(FINAL_FILE, index=False)

  
    try:
        df = pd.read_excel(SCHEDULE_FILE, dtype={"time": str, "date": str})
        if not df.empty:
            df["time"] = df["time"].astype(str).str.strip().str.extract(r"(\d{1,2}:\d{2})")[0]
            # Add missing columns if they don't exist
            if "duration" not in df.columns:
                df["duration"] = 30
            if "patient_type" not in df.columns:
                df["patient_type"] = "New"
            df.to_excel(SCHEDULE_FILE, index=False)
    except Exception:
        pass

def init_day_schedule(day: date):
    try:
        df = pd.read_excel(SCHEDULE_FILE)
    except Exception:
        df = pd.DataFrame(columns=["date", "time", "patient", "duration", "patient_type"])

    day_str = day.strftime("%Y-%m-%d")
    exists_for_day = (df["date"] == day_str).any() if not df.empty else False

    if not exists_for_day:
        rows = []
        cur = datetime.combine(day, SLOT_START)
        end_dt = datetime.combine(day, SLOT_END)
        while cur <= end_dt:
            rows.append([day_str, cur.strftime("%H:%M"), "", 30, ""])  # Default 30min slots
            cur += timedelta(minutes=SLOT_STEP_MIN)
        new_rows = pd.DataFrame(rows, columns=["date","time","patient","duration","patient_type"])
        df = pd.concat([df, new_rows], ignore_index=True)

    # Normalize time format
    if not df.empty:
        df["time"] = df["time"].astype(str).str.strip().str.extract(r"(\d{1,2}:\d{2})")[0]
        # Ensure all required columns exist
        if "duration" not in df.columns:
            df["duration"] = 30
        if "patient_type" not in df.columns:
            df["patient_type"] = ""
    df.to_excel(SCHEDULE_FILE, index=False)

def get_available_slots_for_patient(day: date, is_new_patient: bool):
    """Return available slots considering patient type and duration requirements."""
    try:
        df = pd.read_excel(SCHEDULE_FILE, dtype={"time": str, "date": str})
        if df.empty:
            return []
        
        df["time"] = df["time"].astype(str).str.strip().str.extract(r"(\d{1,2}:\d{2})")[0]
        day_str = day.strftime("%Y-%m-%d")
        df_day = df[df["date"] == day_str].copy()
        
        if df_day.empty:
            return []
        
        # Find free slots
        free_mask = (
            (df_day["patient"].isna()) |
            (df_day["patient"].astype(str).str.strip() == "") |
            (df_day["patient"].astype(str).str.lower() == "nan")
        )
        free_slots = df_day[free_mask].copy()
        
        if free_slots.empty:
            return []
        
        # Sort by time
        free_slots = free_slots.sort_values("time")
        available_slots = []
        
        required_duration = NEW_PATIENT_DURATION if is_new_patient else RECURRING_PATIENT_DURATION
        
        for idx, row in free_slots.iterrows():
            slot_time = row["time"]
            if can_book_duration(df_day, slot_time, required_duration):
                available_slots.append(slot_time)
        
        return available_slots
        
    except Exception as e:
        st.error(f"Error getting available slots: {e}")
        return []

def can_book_duration(df_day, start_time, duration_minutes):
    """Check if we can book consecutive slots for the required duration."""
    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
        slots_needed = duration_minutes // SLOT_STEP_MIN
        
        for i in range(slots_needed):
            check_time = (start_dt + timedelta(minutes=i * SLOT_STEP_MIN)).strftime("%H:%M")
            slot_row = df_day[df_day["time"] == check_time]
            
            if slot_row.empty:
                return False
            
            patient_val = str(slot_row.iloc[0]["patient"]).strip()
            if patient_val != "" and patient_val.lower() not in ("nan", "none"):
                return False
        
        return True
    except Exception:
        return False

def book_appointment_slot(day: date, start_time: str, patient_name: str, duration: int, patient_type: str):
    """Book consecutive slots for the appointment duration."""
    try:
        df = pd.read_excel(SCHEDULE_FILE, dtype={"time": str, "date": str})
        if df.empty:
            return False
        
        df["time"] = df["time"].astype(str).str.strip().str.extract(r"(\d{1,2}:\d{2})")[0]
        day_str = day.strftime("%Y-%m-%d")
        
        start_dt = datetime.strptime(start_time, "%H:%M")
        slots_needed = duration // SLOT_STEP_MIN
        
        # Book all required slots
        for i in range(slots_needed):
            slot_time = (start_dt + timedelta(minutes=i * SLOT_STEP_MIN)).strftime("%H:%M")
            mask = (df["date"] == day_str) & (df["time"] == slot_time)
            matching_rows = df[mask]
            
            if matching_rows.empty:
                return False
            
            idx = matching_rows.index[0]
            df.at[idx, "patient"] = patient_name
            df.at[idx, "duration"] = duration if i == 0 else 0  # Mark duration only on first slot
            df.at[idx, "patient_type"] = patient_type
        
        df.to_excel(SCHEDULE_FILE, index=False)
        return True
        
    except Exception as e:
        st.error(f"Error booking appointment: {e}")
        return False


def patient_lookup(name: str, dob: str):
    """Check if patient exists in database."""
    try:
        if not os.path.exists(PATIENT_FILE):
            return False
        df = pd.read_csv(PATIENT_FILE)
        if df.empty:
            return False
        match = df[(df["name"].str.strip().str.lower() == name.strip().lower())
                   & (df["dob"].str.strip() == dob.strip())]
        return not match.empty
    except Exception:
        return False

def get_patient_contact_info(name: str, dob: str):
    """Get patient's email and phone from database."""
    try:
        if not os.path.exists(PATIENT_FILE):
            return {"email": "", "phone": ""}
        df = pd.read_csv(PATIENT_FILE)
        if df.empty:
            return {"email": "", "phone": ""}
        match = df[(df["name"].str.strip().str.lower() == name.strip().lower())
                   & (df["dob"].str.strip() == dob.strip())]
        if not match.empty:
            row = match.iloc[0]
            return {
                "email": str(row.get("email", "")).strip(),
                "phone": str(row.get("phone", "")).strip()
            }
        return {"email": "", "phone": ""}
    except Exception:
        return {"email": "", "phone": ""}

def save_patient_if_new(patient: dict):
    """Save new patient to database."""
    try:
        if not os.path.exists(PATIENT_FILE):
            pd.DataFrame(columns=["name","dob","email","phone"]).to_csv(PATIENT_FILE, index=False)
        df = pd.read_csv(PATIENT_FILE)
        existing = ((df["name"].str.strip().str.lower() == patient["name"].strip().lower())
                    & (df["dob"].str.strip() == patient["dob"].strip())).any()
        if not existing:
            new_patient = pd.DataFrame([patient])
            df = pd.concat([df, new_patient], ignore_index=True)
            df.to_csv(PATIENT_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Error saving patient: {e}")
        return False

def save_final_details(patient, appt_date, appt_time, duration, patient_type, insurance, doctor, location):
    """Save final appointment details."""
    try:
        if not os.path.exists(FINAL_FILE):
            cols = [
                "name","dob","email","phone","date","time","duration","patient_type","doctor","location",
                "insurance_carrier","member_id","group_number","confirmed","notes"
            ]
            pd.DataFrame(columns=cols).to_excel(FINAL_FILE, index=False)
        
        df = pd.read_excel(FINAL_FILE)
        row = {
            "name": patient["name"],
            "dob": patient["dob"],
            "email": patient.get("email", ""),
            "phone": patient.get("phone", ""),
            "date": appt_date.strftime("%Y-%m-%d"),
            "time": appt_time,
            "duration": duration,
            "patient_type": patient_type,
            "doctor": doctor,
            "location": location,
            "insurance_carrier": insurance.get("insurance_carrier",""),
            "member_id": insurance.get("member_id",""),
            "group_number": insurance.get("group_number",""),
            "confirmed": "Yes",
            "notes": ""
        }
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_excel(FINAL_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Error saving final details: {e}")
        return False

# -----------------------
# Email Helper
# -----------------------
def send_email(to_email: str, subject: str, message: str):
    """Send email notification."""
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS:
        st.warning("Email not configured properly")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        text = msg.as_string()
        server.sendmail(EMAIL_USER, to_email, text)
        server.quit()
        return True
        
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

# -----------------------
# SMS Helper
# -----------------------
def send_sms(to_number: str, message: str):
    """Send SMS notification."""
    if not SMS_ENABLED or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        st.warning("SMS not configured properly")
        return False
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        return True
    except Exception as e:
        st.error(f"SMS error: {e}")
        return False


def parse_patient_text(text: str):
    """Parse patient information from text input."""
    name_match = re.search(r"name[:\-]?\s*([A-Za-z][A-Za-z\s.'-]+)", text, re.IGNORECASE)
    dob_match = re.search(r"(\d{4}-\d{2}-\d{2})|(\d{2}-\d{2}-\d{4})|(\d{1,2}[/-]\d{1,2}[/-]\d{4})", text)
    email_match = re.search(r"email[:\-]?\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text, re.IGNORECASE)
    phone_match = re.search(r"phone[:\-]?\s*([+]?[\d\-\(\)\s]{10,15})", text, re.IGNORECASE)
    
    name = name_match.group(1).strip() if name_match else ""
    dob = dob_match.group(0) if dob_match else ""
    email = email_match.group(1).strip() if email_match else ""
    phone = phone_match.group(1).strip() if phone_match else ""
    
    return {"name": name, "dob": dob, "email": email, "phone": phone}

def parse_insurance_text(text: str):
    """Parse insurance information from text input."""
    def grab(field):
        pattern = fr"{field}[:\-]?\s*([A-Za-z0-9\-\s]+)"
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else ""
    return {
        "insurance_carrier": grab("carrier|insurance"),
        "member_id": grab("member[_\s]?id"),
        "group_number": grab("group[_\s]?number"),
    }

# -----------------------
# Minimal LangGraph Engine
# -----------------------
class LGNode:
    def __init__(self, name: str, handler: Callable[[dict, str], dict]):
        self.name = name
        self.handler = handler

class LangGraph:
    def __init__(self):
        self.nodes: Dict[str, LGNode] = {}
        self.start_node: str = ""
    def add_node(self, node: LGNode):
        self.nodes[node.name] = node
    def set_start(self, name: str):
        self.start_node = name
    def step(self, current: str, state: dict, user_input: str) -> dict:
        if current not in self.nodes:
            return {"next": "error", "response": "Invalid node"}
        return self.nodes[current].handler(state, user_input)

# -----------------------
# State & Handlers
# -----------------------
def make_initial_state():
    return {
        "phase": "greet",
        "patient": {},
        "existing": False,
        "appointment_date": None,
        "appointment_time": "",
        "appointment_duration": 30,
        "patient_type": "New",
        "doctor": "",
        "location": "",
        "insurance": {},
        "messages": [
            "👋 Welcome to the Medical Appointment Scheduler!",
            "Please provide your information in the following format:",
            "**For New Patients:**",
            "• Name: [Full Name], DOB: [YYYY-MM-DD], Email: [email@example.com], Phone: [+1234567890]",
            "**For Returning Patients:**",
            "• Name: [Full Name], DOB: [YYYY-MM-DD]",
            "",
            "**Example:** Name: John Doe, DOB: 1990-01-15, Email: john@email.com, Phone: +1234567890"
        ],
        "completed": False,
        "reminders": [],
        "current_node": "greet"
    }

def node_greet_handler(state: dict, user_input: str) -> dict:
    if not user_input:
        return {"next": "greet", "response": "👋 Welcome! Please provide your information."}
    
    info = parse_patient_text(user_input)
    
    if info["name"] and info["dob"]:
        state["existing"] = patient_lookup(info["name"], info["dob"])
        
        if state["existing"]:
            # Get existing patient contact info
            contact_info = get_patient_contact_info(info["name"], info["dob"])
            info.update(contact_info)
            state["patient_type"] = "Recurring"
            state["appointment_duration"] = RECURRING_PATIENT_DURATION
            response = f"✅ Welcome back, {info['name']}! (Returning Patient - 30 min appointment)"
        else:
            # New patient - require email and phone
            if not info["email"] or not info["phone"]:
                return {
                    "next": "greet", 
                    "response": "❌ New patients must provide email and phone. Please include: Name, DOB, Email, and Phone."
                }
            state["patient_type"] = "New"
            state["appointment_duration"] = NEW_PATIENT_DURATION
            response = f"✅ Welcome {info['name']}! (New Patient - 60 min appointment)"
        
        state["patient"] = info
        return {"next": "doctor", "response": response + "\n\nChecking doctor and location assignment..."}
    
    return {"next": "greet", "response": "❌ Please provide at least your name and date of birth."}

def node_doctor_handler(state: dict, user_input: str) -> dict:
    # Simple assignment based on patient name/dob hash
    doctor = DOCTORS[len(state["patient"]["name"]) % len(DOCTORS)]
    location = LOCATIONS[len(state["patient"]["dob"]) % len(LOCATIONS)]
    state["doctor"] = doctor
    state["location"] = location
    
    duration_text = f"{state['appointment_duration']} minutes"
    return {
        "next": "date", 
        "response": f"👨‍⚕️ **Doctor:** {doctor}\n📍 **Location:** {location}\n⏱️ **Duration:** {duration_text}\n\n📅 **Choose date:** today / tomorrow / day after / YYYY-MM-DD"
    }

def node_date_handler(state: dict, user_input: str) -> dict:
    txt = (user_input or "").strip().lower()
    today = date.today()
    
    if txt in ("today", "t", "1"):
        state["appointment_date"] = today
    elif txt in ("tomorrow", "2"):
        state["appointment_date"] = today + timedelta(days=1)
    elif txt in ("day after", "3"):
        state["appointment_date"] = today + timedelta(days=2)
    else:
        try:
            state["appointment_date"] = datetime.strptime(txt, "%Y-%m-%d").date()
        except Exception:
            return {"next": "date", "response": "❌ Invalid date. Use today/tomorrow/day after or YYYY-MM-DD."}
    
    return {"next": "slots", "response": None}

def node_slots_handler(state: dict, user_input: str) -> dict:
    is_new_patient = not state["existing"]
    available_slots = get_available_slots_for_patient(state["appointment_date"], is_new_patient)
    
    if not available_slots:
        return {"next": "date", "response": f"❌ No available {state['appointment_duration']}-minute slots for this date. Pick another date."}
    
    slots_str = ", ".join(available_slots)
    duration_text = f"{state['appointment_duration']} minutes"
    return {
        "next": "book", 
        "response": f"🕒 **Available {duration_text} slots** for {state['appointment_date'].strftime('%Y-%m-%d')}:\n{slots_str}\n\nPick a time (e.g., 10:00)."
    }

def node_book_handler(state: dict, user_input: str) -> dict:
    time_slot = (user_input or "").strip()
    if ":" not in time_slot and time_slot.isdigit():
        time_slot = f"{time_slot}:00"
    time_slot = str(time_slot).strip()[:5]
    
    is_new_patient = not state["existing"]
    available_slots = get_available_slots_for_patient(state["appointment_date"], is_new_patient)
    
    if time_slot in available_slots:
        success = book_appointment_slot(
            state["appointment_date"], 
            time_slot, 
            state["patient"]["name"],
            state["appointment_duration"],
            state["patient_type"]
        )
        
        if success:
            state["appointment_time"] = time_slot
            return {
                "next": "insurance",
                "response": f"✅ **{state['appointment_duration']}-minute appointment** booked for {state['appointment_date'].strftime('%Y-%m-%d')} at {time_slot}!\n\n💳 Please provide your insurance information:\n**Example:** Insurance: Blue Cross, Member ID: 123456, Group Number: ABC123"
            }
        else:
            return {"next": "book", "response": "❌ Failed to book the slot. Please try another time."}
    else:
        return {"next": "book", "response": f"❌ That time slot is not available. Try one of: {', '.join(available_slots)}"}

def node_insurance_handler(state: dict, user_input: str) -> dict:
    info = parse_insurance_text(user_input or "")
    if info["insurance_carrier"] and info["member_id"] and info["group_number"]:
        state["insurance"] = info
        return {"next": "finalize", "response": None}
    return {
        "next": "insurance", 
        "response": "❌ Missing insurance info. Please provide:\n**Insurance:** [Carrier Name], **Member ID:** [ID], **Group Number:** [Number]"
    }

def node_finalize_handler(state: dict, user_input: str) -> dict:
    # Save patient if new
    if not state["existing"]:
        if not save_patient_if_new(state["patient"]):
            return {"next": "finalize", "response": "❌ Error saving patient information."}
    
    # Save final appointment details
    success = save_final_details(
        state["patient"],
        state["appointment_date"],
        state["appointment_time"],
        state["appointment_duration"],
        state["patient_type"],
        state["insurance"],
        state["doctor"],
        state["location"]
    )
    
    if not success:
        return {"next": "finalize", "response": "❌ Error finalizing appointment."}
    
    state["completed"] = True
    state["reminders"] = ["⏰ Reminder: 24h before", "⏰ Reminder: 3h before", "⏰ Reminder: 30min before"]
    
    # Create confirmation messages
    summary = f"""
🎉 **Appointment Confirmed!**

**Patient:** {state['patient']['name']} ({state['patient_type']})
**Date:** {state['appointment_date'].strftime('%Y-%m-%d')}
**Time:** {state['appointment_time']}
**Duration:** {state['appointment_duration']} minutes
**Doctor:** {state['doctor']}
**Location:** {state['location']}
**Insurance:** {state['insurance']['insurance_carrier']}
    """
    
    # Send notifications
    notification_msg = (
        f"Hi {state['patient']['name']}, your {state['appointment_duration']}-minute appointment is confirmed for "
        f"{state['appointment_date']} at {state['appointment_time']} with {state['doctor']} at {state['location']}. "
        f"Insurance: {state['insurance']['insurance_carrier']}."
    )
    
    notifications_sent = []
    
    # Send Email
    if state['patient'].get('email'):
        email_subject = f"Appointment Confirmation - {state['appointment_date']} at {state['appointment_time']}"
        if send_email(state['patient']['email'], email_subject, notification_msg):
            notifications_sent.append(f"📧 Email sent to {state['patient']['email']}")
        else:
            notifications_sent.append("❌ Email failed to send")
    
    # Send SMS
    phone_number = state['patient'].get('phone', PATIENT_NOTIFY_PHONE)
    if phone_number:
        if send_sms(phone_number, notification_msg):
            notifications_sent.append(f"📱 SMS sent to {phone_number}")
        else:
            notifications_sent.append("❌ SMS failed to send")
    
    # Add notification status to messages
    for notification in notifications_sent:
        state["messages"].append(notification)
    
    return {"next": "done", "response": summary.strip()}

def node_done_handler(state: dict, user_input: str) -> dict:
    return {"next": "done", "response": "✅ Appointment completed. Click 'Start New Appointment' to begin again."}

# -----------------------
# Build Graph
# -----------------------
def build_graph() -> LangGraph:
    g = LangGraph()
    g.add_node(LGNode("greet", node_greet_handler))
    g.add_node(LGNode("doctor", node_doctor_handler))
    g.add_node(LGNode("date", node_date_handler))
    g.add_node(LGNode("slots", node_slots_handler))
    g.add_node(LGNode("book", node_book_handler))
    g.add_node(LGNode("insurance", node_insurance_handler))
    g.add_node(LGNode("finalize", node_finalize_handler))
    g.add_node(LGNode("done", node_done_handler))
    g.set_start("greet")
    return g

# -----------------------
# Streamlit App
# -----------------------
st.set_page_config(page_title="Medical Appointment Agent", page_icon="🏥")
st.title("🏥 Medical Appointment Scheduling Agent")

# Display configuration status
with st.sidebar:
    st.subheader("📧 Email Configuration")
    st.write(f"Enabled: {'✅' if EMAIL_ENABLED else '❌'}")
    st.write(f"User: {EMAIL_USER[:10]}..." if EMAIL_USER else "Not Set")
    
    st.subheader("📱 SMS Configuration")
    st.write(f"Enabled: {'✅' if SMS_ENABLED else '❌'}")
    st.write(f"Twilio SID: {TWILIO_ACCOUNT_SID[:10]}..." if TWILIO_ACCOUNT_SID else "Not Set")
    
    st.subheader("⏱️ Appointment Durations")
    st.write(f"New Patients: {NEW_PATIENT_DURATION} minutes")
    st.write(f"Recurring Patients: {RECURRING_PATIENT_DURATION} minutes")
    
    st.subheader("🔧 Debug Info")
    if 'agent_state' in st.session_state:
        st.write(f"Node: {st.session_state.agent_state.get('current_node')}")
        if st.session_state.agent_state['patient']:
            st.write(f"Patient: {st.session_state.agent_state['patient']['name']}")
            st.write(f"Type: {st.session_state.agent_state.get('patient_type', 'Unknown')}")
        if st.session_state.agent_state['appointment_date']:
            st.write(f"Date: {st.session_state.agent_state['appointment_date']}")
            st.write(f"Duration: {st.session_state.agent_state.get('appointment_duration', 30)} min")

ensure_files()
today = date.today()
for i in range(7):
    init_day_schedule(today + timedelta(days=i))

if "lg_graph" not in st.session_state:
    st.session_state.lg_graph = build_graph()
if "agent_state" not in st.session_state:
    st.session_state.agent_state = make_initial_state()

# Initialize welcome message only once
if not st.session_state.agent_state.get("initialized", False):
    welcome_msg = """👋 Welcome to the Medical Appointment Scheduler!

Please provide your information in the following format:

**For New Patients:**
• Name: [Full Name], DOB: [YYYY-MM-DD], Email: [email@example.com], Phone: [+1234567890]

**For Returning Patients:**  
• Name: [Full Name], DOB: [YYYY-MM-DD]

**Example:** Name: John Doe, DOB: 1990-01-15, Email: john@email.com, Phone: +1234567890"""
    
    st.session_state.agent_state["conversation_history"] = [("Assistant", welcome_msg)]
    st.session_state.agent_state["initialized"] = True

st.subheader("💬 Conversation")

# Display conversation history
for speaker, message in st.session_state.agent_state["conversation_history"]:
    if speaker == "User":
        st.write(f"**You:** {message}")
    else:
        st.write(message)

# Display current message if any
if st.session_state.agent_state.get("current_message"):
    st.write(st.session_state.agent_state["current_message"])

if not st.session_state.agent_state.get("completed", False):
    user_input = st.chat_input("Type your response here...")
    if user_input is not None and user_input.strip():
        # Add user input to conversation history
        st.session_state.agent_state["conversation_history"].append(("User", user_input))
        
        current_node = st.session_state.agent_state.get("current_node", st.session_state.lg_graph.start_node)
        result = st.session_state.lg_graph.step(current_node, st.session_state.agent_state, user_input)
        next_node = result.get("next", current_node)
        resp = result.get("response", "")
        st.session_state.agent_state["current_node"] = next_node
        
        if resp:
            st.session_state.agent_state["conversation_history"].append(("Assistant", resp))
        
        # Handle automatic transitions for slots display
        if next_node in ("slots",) and result.get("response") is None:
            res2 = st.session_state.lg_graph.step(next_node, st.session_state.agent_state, "")
            st.session_state.agent_state["current_node"] = res2.get("next", next_node)
            if res2.get("response"):
                st.session_state.agent_state["conversation_history"].append(("Assistant", res2["response"]))
        
        # Handle automatic transitions for finalize
        if next_node in ("finalize",) and result.get("response") is None:
            res2 = st.session_state.lg_graph.step(next_node, st.session_state.agent_state, "")
            st.session_state.agent_state["current_node"] = res2.get("next", next_node)
            if res2.get("response"):
                st.session_state.agent_state["conversation_history"].append(("Assistant", res2["response"]))
        
        st.rerun()
else:
    st.success("🎉 Appointment booking completed!")
    
    # Display appointment summary
    if st.session_state.agent_state.get("completed"):
        patient = st.session_state.agent_state["patient"]
        appt_date = st.session_state.agent_state["appointment_date"]
        appt_time = st.session_state.agent_state["appointment_time"]
        duration = st.session_state.agent_state["appointment_duration"]
        patient_type = st.session_state.agent_state["patient_type"]
        doctor = st.session_state.agent_state["doctor"]
        location = st.session_state.agent_state["location"]
        
        st.info(f"""
        **Final Appointment Details:**
        - **Patient:** {patient['name']} ({patient_type})
        - **Date & Time:** {appt_date.strftime('%Y-%m-%d')} at {appt_time}
        - **Duration:** {duration} minutes
        - **Doctor:** {doctor}
        - **Location:** {location}
        - **Email:** {patient.get('email', 'N/A')}
        - **Phone:** {patient.get('phone', 'N/A')}
        """)
    
    if st.button("🔄 Start New Appointment"):
        st.session_state.agent_state = make_initial_state()
        st.rerun()

# Display current schedule for today (for testing purposes)
st.markdown("---")
st.markdown("## 📅 **Today's Schedule Overview**")
st.markdown(f"**Date: {date.today().strftime('%A, %B %d, %Y')}**")

try:
    df = pd.read_excel(SCHEDULE_FILE)
    today_str = date.today().strftime("%Y-%m-%d")
    today_schedule = df[df["date"] == today_str]
    
    if not today_schedule.empty:
        # Show only booked appointments
        booked = today_schedule[
            (today_schedule["patient"].notna()) & 
            (today_schedule["patient"].astype(str).str.strip() != "") &
            (today_schedule["patient"].astype(str).str.lower() != "nan")
        ]
        
        if not booked.empty:
            st.success(f"📋 **{len(booked)} Appointment(s) Scheduled Today**")
            
            # Create a more visually appealing display
            for _, appointment in booked.sort_values("time").iterrows():
                duration_text = f"{appointment['duration']} min" if appointment['duration'] > 0 else "Multi-slot"
                patient_type_icon = "🆕" if appointment['patient_type'] == "New" else "🔄"
                
                st.info(f"""
                **🕐 {appointment['time']}** | **{patient_type_icon} {appointment['patient']}** 
                ⏱️ Duration: {duration_text} | 📋 Type: {appointment['patient_type']} Patient
                """)
        else:
            st.info("📅 **No appointments scheduled for today**")
            st.write("All time slots are currently available.")
    else:
        st.warning("⚠️ **No schedule data available for today**")
        st.write("Schedule may need to be initialized.")
        
except Exception as e:
    st.error(f"❌ **Error loading today's schedule:** {e}")

# Add a clear separator before the conversation section by moving this to the TOP
# Move this section right after the title and before the conversation:

st.markdown("---")
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 💬 **Appointment Booking Conversation**")
    st.markdown("*Complete the steps below to schedule your appointment*")

with col2:
    # Quick stats
    try:
        df = pd.read_excel(SCHEDULE_FILE) if os.path.exists(SCHEDULE_FILE) else pd.DataFrame()
        today_str = date.today().strftime("%Y-%m-%d")
        today_booked = 0
        if not df.empty:
            today_schedule = df[df["date"] == today_str]
            today_booked = len(today_schedule[
                (today_schedule["patient"].notna()) & 
                (today_schedule["patient"].astype(str).str.strip() != "") &
                (today_schedule["patient"].astype(str).str.lower() != "nan")
            ])
        
        st.metric("📅 Today's Appointments", today_booked)
        st.metric("⏰ Available Slots", f"~{(11*60//30) - today_booked}")  # Rough estimate
    except:
        st.metric("📅 Today's Appointments", "N/A")

st.markdown("---")