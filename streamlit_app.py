import streamlit as st
import requests
import time
import pytz
from datetime import datetime, timedelta
from dateutil.parser import parse
from calendar_utils import get_today_events

# 🌐 FastAPI backend URL
API_URL = "https://calendar-booking-assistant.onrender.com"

# 🛠️ Page config
st.set_page_config(page_title="🧠 Calendar Assistant", layout="wide")

# 🧠 Title & Description
st.title("📅 AI Calendar Assistant")
st.caption("Chat with your assistant to check availability, book slots, or manage meetings.")

# 🧭 Sidebar summary (Always fetch fresh)
with st.sidebar:
    st.header("📍 Today at a Glance")

    try:
        sidebar_events = get_today_events()
        for event_html in sidebar_events:
            st.markdown(event_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"⚠️ Failed to load today's events: {e}")

    st.markdown("---")
    if st.button("🔄 Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()
    
    st.markdown("### 💬 Ask something like:")

    # 📅 Availability Check
    st.markdown("- _Do I have any free slots today?_")
    st.markdown("- _Check my availability on Friday_")

    # 🆕 Booking an Event
    st.markdown("- _Book a call tomorrow at 2 PM_")
    st.markdown("- _Schedule a team sync for next Monday morning_")

    # 🔁 Rescheduling
    st.markdown("- _Reschedule my client meeting to Thursday at 4 PM_")
    st.markdown("- _Can you move the project discussion to 11 AM?_")

    # 🗑️ Deleting / Cancelling
    st.markdown("- _Cancel the marketing review meeting_")
    st.markdown("- _Delete the call with Sarah on Wednesday_")

# 🔁 Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.divider()

# 🧾 Display chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(f"**You:** {msg['content']}")
        else:
            st.markdown(f"**Assistant:**\n\n{msg['content']}", unsafe_allow_html=True)

# 💬 Input prompt
user_input = st.chat_input("Ask anything like 'Book at 4 PM tomorrow'...")

# 🚀 On user message
if user_input:
    st.chat_message("user").markdown(f"**You:** {user_input}")
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("🤔 Thinking..."):
            start_time = time.time()
            try:
                response = requests.post(f"{API_URL}/agent", json={"message": user_input}, timeout=60)
                response.raise_for_status()
                data = response.json()
                assistant_reply = data.get("response")

                if not assistant_reply:
                    assistant_reply = "❌ No response received from the assistant."
                    st.error("⚠️ Empty response from backend.")
            except requests.exceptions.RequestException as e:
                assistant_reply = f"❌ Request failed: {e}"
                st.error(assistant_reply)
            except Exception as e:
                assistant_reply = f"❌ Unexpected error: {e}"
                st.error(assistant_reply)

            response_time = round(time.time() - start_time, 2)
            st.markdown(f"**Assistant:**\n\n{assistant_reply}", unsafe_allow_html=True)
            st.caption(f"⏱️ Responded in {response_time}s")

            st.session_state.chat_history.append({
                "role": "assistant",
                "content": assistant_reply
            })

        # 🔁 Rerun sidebar if calendar modified
        trigger_keywords = ["Booking confirmed", "Rescheduled", "Event deleted"]
        if any(keyword in assistant_reply for keyword in trigger_keywords):
            time.sleep(1.5)  # allow Google Calendar to sync
            st.rerun()




# To Run Streamlit App: streamlit run streamlit_app.py
