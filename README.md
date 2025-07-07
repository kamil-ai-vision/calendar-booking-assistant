# 📅 AI Calendar Booking Assistant

An AI-powered conversational assistant that helps you schedule, reschedule, and manage meetings on your Google Calendar.

---

## 🚀 Features
- 📆 Book meetings by chatting naturally
- 🔁 Reschedule existing events
- ❌ Cancel meetings
- ✅ Check your availability
- 💡 Uses LangChain Agent + Google Calendar API

---

## 🛠️ Tech Stack
- Backend: **FastAPI**
- Frontend: **Streamlit**
- Agent: **LangChain**
- LLM: Gemini / OpenAI (via API)
- Calendar: Google Calendar API with **Service Account**

---

## 🧪 Demo Examples
- _“Book a call tomorrow at 3 PM”_
- _“Cancel my meeting on Friday”_
- _“Move my 10 AM event to 2 PM”_
- _“Am I free next Monday?”_

---

## ⚙️ Local Setup

1. Clone the repo:
```bash
git clone https://github.com/kamil-ai-vision/calendar-booking-assistant.git
cd calendar-booking-assistant
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Add your credentials:

- Create .env file (see .env.example)
- Add your service_account.json for Google Calendar access

4. Run backend:
```bash
uvicorn main:app --reload
```

5. Run frontend:
```bash
streamlit run streamlit_app.py
```

---

🌐 Deployment

You can deploy this project for free using:

- Backend: Render
- Frontend: Streamlit Community Cloud

---

🔐 Important

- Never commit .env or service_account.json to GitHub
- Use .gitignore to keep secrets safe

---

## 👤 Author

[Kamil Shaikh](https://github.com/kamil-ai-vision)
