# 🏥 Medical Appointment Scheduling Agent :

This application is a **Streamlit-based medical appointment agent** designed to automate the scheduling process for clinics and healthcare providers. It guides patients (new or returning) through a conversational flow to book appointments, select doctors and locations, manage patient data, and send notifications via **email** and **SMS**.

---

## 🚀 Features :

- **Conversational Booking**: Patients interact step-by-step to provide information, choose dates and times, and confirm appointments.
- **Patient Management**: Handles both new and recurring patients, storing essential details in a CSV database.
- **Multiple Doctors & Locations**: Supports assignment of doctors and locations based on patient information.
- **Intelligent Slot Management**: Dynamically calculates available appointment slots based on patient type (new or recurring).
- **Email & SMS Notifications**: Sends appointment confirmations and reminders using Gmail SMTP and Twilio SMS.
- **Schedule Overview**: Displays today's appointments and available slots for admin and staff.
- **Insurance Capture**: Collects and stores insurance details as part of the final booking step.
- **Extensible Engine**: Uses a minimal LangGraph engine to manage conversational state and workflow.

---

## 🗂️ File Structure

- `patients.csv`: Stores registered patient details.
- `schedule.xlsx`: Manages daily appointment slots and bookings.
- `final.xlsx`: Records all finalized appointments and insurance info.

---

## ⚙️ Configuration

All sensitive credentials and options are loaded via environment variables using a `.env` file.

**Required Environment Variables:**

```env
EMAIL_ENABLED=true
EMAIL_USER=your_gmail_address@gmail.com
EMAIL_PASS=your_gmail_app_password
ENABLE_SMS=true
TWILIO_SID=your_twilio_account_sid
TWILIO_AUTH=your_twilio_auth_token
TWILIO_PHONE=your_twilio_phone_number
PATIENT_NOTIFY_PHONE=default_patient_phone_number
```

> **Note:** You must set up Gmail App Passwords and Twilio credentials for email and SMS notifications to work.

---

## 🛠️ Setup & Usage

1. **Clone the Repository**
    ```bash
    git clone https://github.com/your-org/your-repo.git
    cd your-repo
    ```

2. **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    # Or manually:
    pip install streamlit pandas openpyxl python-dotenv twilio
    ```

3. **Create and Configure `.env` File**
    - Copy `.env.example` to `.env` and fill in your credentials.

4. **Run the App**
    ```bash
    streamlit run <your_app_file>.py
    ```

5. **Access the App**
    - Open the local Streamlit URL (usually [http://localhost:8501](http://localhost:8501)).

---
## 💬 How It Works

### 1. **Greeting & Patient Info**
- The assistant welcomes the user and asks for either new or returning patient details (name, DOB, email, phone).

### 2. **Doctor & Location Assignment**
- Automatically assigns a doctor and clinic location based on patient info.

### 3. **Date & Slot Selection**
- Patient chooses a preferred date (today, tomorrow, etc.).
- App shows all available slots for that day, considering appointment duration.

### 4. **Booking & Insurance**
- Patient selects a time slot and provides insurance details.
- The system books the slot, saves all info, and sends confirmation notifications.

### 5. **Confirmation & Reminders**
- Patient receives a summary of their appointment.
- Email and SMS notifications are sent (if configured).
- Reminders are set for upcoming appointments.

### 6. **Admin Overview**
- The sidebar displays configuration status and today's schedule.
- Quick stats on appointments and available slots.

---

## 📋 Example Conversation

```
👋 Welcome to the Medical Appointment Scheduler!
Please provide your information:
- Name: Jane Doe, DOB: 1992-05-10, Email: jane@doe.com, Phone: +1234567890

✅ Welcome Jane Doe! (New Patient - 60 min appointment)
Doctor: Dr. Johnson
Location: Main Clinic
Duration: 60 minutes

Choose date: today / tomorrow / YYYY-MM-DD
...
Available slots: 10:00, 11:00, 14:30, 16:00
Pick a time: 14:30

✅ Appointment booked for 2025-09-08 at 14:30!
Please provide your insurance info:
Insurance: Blue Cross, Member ID: 123456, Group Number: ABC123
...
🎉 Appointment Confirmed!
📧 Email sent to jane@doe.com
📱 SMS sent to +1234567890
```

---

## 📝 Customization & Extensibility

- **Doctors and Locations**: Edit the `DOCTORS` and `LOCATIONS` lists in the code to fit your clinic.
- **Slot Times & Durations**: Change the `SLOT_START`, `SLOT_END`, `SLOT_STEP_MIN`, and patient duration variables as needed.
- **Insurance Fields**: Extend `parse_insurance_text` for more detailed insurance data.
- **LangGraph Engine**: Add more conversational steps, validation, or workflow nodes as required.

---

## 🔐 Security Notes

- Ensure your `.env` file with credentials is not committed or exposed publicly.
- Use secure app passwords for email, and restrict Twilio usage to trusted phone numbers.

---

## 📖 License

This project is distributed under the MIT License. Please consult `LICENSE` for details.

---

## 🙋‍♀️ Support & Contribution

- Issues and pull requests are welcome!
- For feature requests, bug reports, or assistance, please open an issue in the repository.

---

**Happy scheduling! 🩺**
