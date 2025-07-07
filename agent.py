import os
import pytz
from dateutil.parser import parse
from dateparser import parse as parse_date
from dateparser.search import search_dates
from datetime import datetime, timedelta

from langchain.agents import initialize_agent, Tool
from langchain.agents.agent_types import AgentType
from langchain.memory import ConversationBufferMemory

from llm_setup import get_llm
from config import GOOGLE_CALENDAR_ID
from calendar_utils import get_free_slots, book_slot, get_calendar_service, delete_event

# ------------------------------
# 🧠 ChatContext to track memory
# ------------------------------
class ChatContext:
    def __init__(self):
        self.pending_booking = None
        self.last_date = None
        self.pending_delete = False
        self.pending_delete_title = None
        self.pending_reschedule = False
        self.pending_reschedule_title = None

    def update_date(self, date_str):
        self.last_date = date_str

    def get_last_date(self):
        return self.last_date

chat_context = ChatContext()

# 🛠️ Tool: Check availability
def check_availability(date: str) -> str:
    try:
        print(f"[TOOL:check_availability] Checking slots for date: {date}")
        chat_context.update_date(date)
        tz = pytz.timezone("Asia/Kolkata")
        start_datetime = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        end_datetime = start_datetime + timedelta(days=1)

        # 🔄 Fetch events
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_datetime.isoformat(),
            timeMax=end_datetime.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"[DEBUG] Fetched {len(events)} events for {date}")

        # 📌 Build busy intervals
        busy_intervals = []
        for event in events:
            if 'dateTime' in event['start']:
                busy_start = parse(event['start']['dateTime']).astimezone(tz)
                busy_end = parse(event['end']['dateTime']).astimezone(tz)
                busy_intervals.append((busy_start, busy_end))

        # 📅 Build 30-min slots
        slots = []
        current = start_datetime.replace(hour=9, minute=0, second=0, microsecond=0)
        work_end = start_datetime.replace(hour=17, minute=0, second=0, microsecond=0)

        while current < work_end:
            slot_start = current
            slot_end = current + timedelta(minutes=30)
            current = slot_end

            is_busy = any(slot_start < b_end and slot_end > b_start for b_start, b_end in busy_intervals)
            time_range = f"{slot_start.strftime('%I:%M %p')} to {slot_end.strftime('%I:%M %p')}"
            label = "🔴 Booked" if is_busy else "🟢 Free"
            slots.append(f"{label} - {time_range}")

        # 🧾 Format 2-column string
        slot_lines = []
        for i in range(0, len(slots), 2):
            left = slots[i]
            right = slots[i+1] if i+1 < len(slots) else ""
            slot_lines.append(f"{left:<30} {right}")

        # ✅ Final message (title and CTA outside code block)
        title = f"📅 **Availability on {date}:**"
        code_block = "```\n" + "\n".join(slot_lines) + "\n```"
        cta = "💬 _Would you like me to book one of these?_"

        return f"{title}\n\n{code_block}\n\n{cta}"

    except Exception as e:
        print(f"[ERROR:check_availability] {str(e)}")
        return f"❌ Failed to check availability for {date}: {e}"

# 🛠️ Tool: Book a meeting
def book_meeting(
    time: str,
    date: str = None,
    summary: str = "Meeting",
    description: str = "Booked via Assistant"
) -> str:
    try:
        print(f"[TOOL:book_meeting] Booking meeting with time='{time}', date='{date}'")
        if not date:
            date = chat_context.get_last_date()
            if not date:
                return "❌ Please provide a date to book the meeting."

        dt = parse_date(f"{date} {time}", settings={"PREFER_DATES_FROM": "future"})
        if not dt:
            return f"❌ Could not understand the time '{time}' for date '{date}'."

        # ✅ Ensure timezone-aware datetime in IST
        tz = pytz.timezone("Asia/Kolkata")
        if dt.tzinfo is None:
            start_time = tz.localize(dt)
        else:
            start_time = dt.astimezone(tz)

        end_time = start_time + timedelta(minutes=30)

        # 🗓 Book the meeting
        book_slot(
            start={
                "dateTime": start_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            end={
                "dateTime": end_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            summary=summary,
            description=description,
        )

        confirmation = f"✅ Booking confirmed: **{summary}** from {start_time.strftime('%Y-%m-%d %I:%M %p')} to {end_time.strftime('%I:%M %p')}"
        return confirmation if confirmation.strip() else "✅ Meeting booked successfully."

    except Exception as e:
        print(f"[ERROR:book_meeting] {str(e)}")
        return f"❌ Failed to book meeting: {str(e)}"

# Reschedule meeting
from calendar_utils import find_events_by_title, delete_event_by_id, book_slot
import pytz
from datetime import datetime, timedelta
from dateparser import parse as parse_date

def reschedule_meeting(title: str, new_date: str, new_time: str) -> str:
    try:
        print(f"[TOOL:reschedule_meeting] Rescheduling '{title}' to {new_date} at {new_time}")

        # 1. 🗑️ Find matching event
        matching_events = find_events_by_title(title)
        if not matching_events:
            print(f"[DEBUG] No matching event found with title '{title}' to delete.")
        else:
            # 🔍 Pick the one with nearest start time
            event_to_delete = sorted(matching_events, key=lambda e: e['start']['dateTime'])[0]
            event_id = event_to_delete['id']
            print(f"[DEBUG] Deleting event ID={event_id}, start={event_to_delete['start']['dateTime']}")
            delete_event_by_id(event_id)

        # 2. 🕒 Parse new datetime
        dt = parse_date(f"{new_date} {new_time}", settings={"PREFER_DATES_FROM": "future"})
        if not dt:
            return f"❌ Could not parse new date/time for '{title}'"

        tz = pytz.timezone("Asia/Kolkata")
        start_time = tz.localize(dt)
        end_time = start_time + timedelta(minutes=30)

        # 3. 📅 Book the rescheduled event
        book_slot(
            start={
                "dateTime": start_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            end={
                "dateTime": end_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            summary=title,
            description=f"Rescheduled via Assistant on {datetime.now().strftime('%Y-%m-%d')}"
        )

        result = f"✅ Rescheduled **{title}** to {start_time.strftime('%Y-%m-%d %I:%M %p')} – {end_time.strftime('%I:%M %p')}"
        return result if result.strip() else "✅ Meeting rescheduled."

    except Exception as e:
        print(f"[ERROR:reschedule_meeting] {e}")
        return f"❌ Failed to reschedule meeting: {e}"

# Reschedule meeting
from calendar_utils import find_events_by_title, delete_event_by_id, book_slot
import pytz
from datetime import datetime, timedelta
from dateparser import parse as parse_date

def reschedule_meeting(title: str, new_date: str, new_time: str) -> str:
    try:
        print(f"[TOOL:reschedule_meeting] Rescheduling '{title}' to {new_date} at {new_time}")

        if not title.strip():
            return "❌ Please provide a valid title for the meeting to reschedule."

        # 1. 🗑️ Find matching event
        matching_events = find_events_by_title(title)
        if not matching_events:
            return f"❌ No meeting found with title '{title}' to reschedule."

        # 🔍 Pick the one with nearest start time
        event_to_delete = sorted(matching_events, key=lambda e: e['start']['dateTime'])[0]
        event_id = event_to_delete['id']
        print(f"[DEBUG] Deleting event ID={event_id}, start={event_to_delete['start']['dateTime']}")
        delete_event_by_id(event_id)

        # 2. 🕒 Parse new datetime
        dt = parse_date(f"{new_date} {new_time}", settings={"PREFER_DATES_FROM": "future"})
        if not dt:
            return f"❌ Could not understand the new date/time: '{new_date} {new_time}'"

        tz = pytz.timezone("Asia/Kolkata")
        start_time = tz.localize(dt)
        end_time = start_time + timedelta(minutes=30)

        # 3. 📅 Book the rescheduled event
        book_slot(
            start={
                "dateTime": start_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            end={
                "dateTime": end_time.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            summary=title,
            description=f"Rescheduled via Assistant on {datetime.now().strftime('%Y-%m-%d')}"
        )

        result = (
            f"🔁 Meeting rescheduled:\n\n"
            f"**{title}**\n"
            f"🗓️ New Date: {start_time.strftime('%Y-%m-%d')}\n"
            f"⏰ Time: {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')}"
        )
        return result.strip() or "✅ Meeting rescheduled successfully."

    except Exception as e:
        print(f"[ERROR:reschedule_meeting] {e}")
        return f"❌ Failed to reschedule meeting: {e}"
    
tools = [
    Tool.from_function(
        func=check_availability,
        name="CheckAvailability",
        description="Use this tool to check available 30-minute meeting slots for a given date (format: YYYY-MM-DD)."
    ),
    Tool.from_function(
        func=book_meeting,
        name="BookMeeting",
        description="Use this tool to book a 30-minute meeting. You must provide: time (e.g., '2 PM'), date (YYYY-MM-DD), and title (e.g., 'Project Update')."
    ),
    Tool.from_function(
        func=reschedule_meeting,
        name="RescheduleMeeting",
        description="Use this to reschedule an existing meeting. Provide the meeting title, new date (YYYY-MM-DD), and new time (e.g., '3 PM')."
    ),
    Tool.from_function(
        func=delete_event,
        name="DeleteMeeting",
        description="Use this to delete a meeting. Provide both the title and date (YYYY-MM-DD) of the meeting."
    )
]

llm = get_llm()

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    memory=ConversationBufferMemory(
        memory_key="chat_history",
        input_key="input",
        output_key="output",
        return_messages=True
    ),
    handle_parsing_errors=True,
    return_intermediate_steps=True,  # Keep if you want tool output logs
    verbose=True
)


def run_with_agent(user_input: str) -> str:
    result = agent_executor.invoke({"input": user_input})

    tool_output = None
    if "intermediate_steps" in result and result["intermediate_steps"]:
        tool_output = result["intermediate_steps"][-1][1]
        print(f"[DEBUG] Tool output: {tool_output}")

    final_output = result.get("output", None)

    if final_output and final_output.strip():
        if tool_output and str(tool_output).strip() != final_output.strip():
            return f"{final_output}\n\n{tool_output}"
        return final_output.strip()
    elif tool_output and str(tool_output).strip():
        return str(tool_output).strip()
    else:
        return "⚠️ Assistant could not generate a valid response."

# ✅ Exportable getter for FastAPI global agent
def get_agent_executor():
    return agent_executor

from dateparser import parse as parse_date
from dateparser.search import search_dates
import re

# 🔁 Main routing logic (manual agent)
def run_agent(user_input: str) -> str:
    print(f"📥 Received message: {user_input}")
    settings = {"PREFER_DATES_FROM": "future"}
    user_input_lower = user_input.lower()

    # 🔁 Step 1: Awaiting reschedule title
    if getattr(chat_context, "pending_reschedule", False) and not getattr(chat_context, "pending_reschedule_title", None):
        chat_context.pending_reschedule_title = user_input.strip()
        return "📅 What new date and time should I reschedule it to?"

    # 🔁 Step 2: Awaiting reschedule date/time
    if getattr(chat_context, "pending_reschedule", False) and getattr(chat_context, "pending_reschedule_title", None):
        try:
            parsed = parse_date(user_input, settings=settings)
            if not parsed:
                return "❌ Please provide a valid date and time like 'tomorrow at 3 PM'."

            title = chat_context.pending_reschedule_title
            chat_context.pending_reschedule = False
            chat_context.pending_reschedule_title = None

            return reschedule_meeting(
                title,
                parsed.strftime("%Y-%m-%d"),
                parsed.strftime("%I:%M %p")
            )
        except Exception as e:
            print(f"[ERROR] Parsing failed during reschedule flow: {e}")
            return "❌ Couldn't parse the new time. Try something like 'next Friday at 11 AM'."

    # 🔁 Reschedule (multi-turn)
    if any(kw in user_input_lower for kw in [
        "reschedule", "change", "postpone", "move",
        "shift", "delay", "update", "edit", "modify",
        "adjust", "rearrange", "push back", "bring forward",
        "change the time", "resched"
    ]):
        title_match = re.search(r"['\"](.+?)['\"]", user_input) or re.search(r"(?:reschedule|change)\s+(.*?)\s+to", user_input_lower)
        if title_match:
            title = title_match.group(1).strip()
            to_match = re.search(r"\bto\s+(.+)", user_input_lower)
            new_dt = parse_date(to_match.group(1), settings=settings) if to_match else None

            if not new_dt:
                # Partial input — enter multi-turn mode
                chat_context.pending_reschedule = True
                chat_context.pending_reschedule_title = title
                return "📅 What new date and time should I reschedule it to?"

            return reschedule_meeting(
                title,
                new_dt.strftime("%Y-%m-%d"),
                new_dt.strftime("%I:%M %p")
            )
        else:
            # Start multi-turn flow
            chat_context.pending_reschedule = True
            chat_context.pending_reschedule_title = None
            return "📝 Please specify the event name you'd like to reschedule."
        
    # 🗑 Step 1: Awaiting delete title
    if getattr(chat_context, "pending_delete", False) and not getattr(chat_context, "pending_delete_title", None):
        chat_context.pending_delete_title = user_input.strip()
        return "📅 Please specify the date of the event you want to delete (e.g., 'tomorrow' or '9 July')."

    # 🗑 Step 2: Awaiting delete date
    if getattr(chat_context, "pending_delete", False) and getattr(chat_context, "pending_delete_title", None):
        try:
            parsed = parse_date(user_input, settings=settings)
            if not parsed:
                return "❌ I couldn't understand the date. Try something like 'tomorrow' or 'July 10'."

            title = chat_context.pending_delete_title
            chat_context.pending_delete = False
            chat_context.pending_delete_title = None

            from calendar_utils import delete_event
            return delete_event(title, parsed.strftime("%Y-%m-%d"))
        except Exception as e:
            print(f"[ERROR] Parsing failed during delete flow: {e}")
            return "❌ Couldn't parse the date. Try something like 'July 10'."

    # 🗓 Step 1: Awaiting time
    if chat_context.pending_booking and chat_context.pending_booking.get("awaiting_time"):
        time_input = user_input.strip()
        date_str = chat_context.pending_booking["date"]
        combined_dt = parse_date(f"{date_str} {time_input}", settings=settings)
        if combined_dt:
            chat_context.pending_booking = {
                "time": combined_dt.strftime("%I:%M %p"),
                "date": date_str
            }
            print(f"[DEBUG] Time parsed for pending booking: {combined_dt}")
            return "📝 What should I title the event?"
        else:
            return "❌ I couldn't understand that time."

    # 📝 Step 2: Awaiting title
    if chat_context.pending_booking and chat_context.pending_booking.get("time"):
        pending = chat_context.pending_booking
        chat_context.pending_booking = None
        chat_context.last_date = None
        print(f"[DEBUG] Booking final with title: {user_input.strip()}, date={pending['date']}, time={pending['time']}")
        return book_meeting(
            time=pending["time"],
            date=pending["date"],
            summary=user_input.strip()
        )

    # 🧠 Step 3: Date/time parsing
    parsed_dates = []

    # Manual: "8 July"
    manual_match = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        user_input_lower
    )
    if manual_match:
        day = manual_match.group(1)
        month = manual_match.group(2)
        try:
            forced_date = datetime.strptime(f"{day} {month} {datetime.now().year}", "%d %B %Y")
            parsed_dates = [(f"{day} {month}", forced_date)]
            print(f"[DEBUG] Manually forced date parsing: {forced_date}")

            # ✅ Enhancement: allow search_dates to extract more complete datetime like "8 July at 2 PM"
            try:
                parsed_dates_raw = search_dates(user_input, settings=settings)
                if parsed_dates_raw:
                    for txt, dt in parsed_dates_raw:
                        if dt.date() == forced_date.date() and (dt.hour != 0 or dt.minute != 0):
                            parsed_dates = [(txt, dt)]
                            print(f"[DEBUG] Overriding with datetime from search_dates: {dt}")
            except Exception as e:
                print(f"[ERROR] Fallback search_dates failed: {e}")

        except Exception as e:
            print(f"[DEBUG] Manual date parsing failed: {e}")

    # General parsing
    if not parsed_dates:
        try:
            parsed_dates_raw = search_dates(user_input, settings=settings)
            parsed_dates = list(parsed_dates_raw) if parsed_dates_raw else []
        except Exception as e:
            print(f"[ERROR] search_dates() failed: {e}")

        parsed_dates = [
            (text, dt)
            for (text, dt) in parsed_dates
            if re.match(r"\d{1,2}", text) or re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|july|august|am|pm)\b",
                text.lower()
            )
        ]

    # ISO + time
    iso_date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", user_input)
    time_match = re.search(r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b", user_input_lower)
    if iso_date_match:
        iso_date = iso_date_match.group(1)
        if time_match:
            dt = parse_date(f"{iso_date} {time_match.group(1)}", settings=settings)
            if dt:
                parsed_dates = [(f"{iso_date} {time_match.group(1)}", dt)]
        else:
            dt = parse_date(iso_date, settings=settings)
            if dt:
                parsed_dates = [(iso_date, dt)]

    # Weekday fallback
    if not parsed_dates or all(dt.hour == 0 and dt.minute == 0 for _, dt in parsed_dates):
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        today = datetime.now()
        for i, day in enumerate(weekdays):
            if f"this {day}" in user_input_lower:
                offset = (i - today.weekday()) % 7 or 7
                parsed_dates = [(f"this {day}", today + timedelta(days=offset))]
                break
            elif f"next {day}" in user_input_lower:
                offset = ((i - today.weekday()) % 7) + 7
                parsed_dates = [(f"next {day}", today + timedelta(days=offset))]
                break
            elif day in user_input_lower:
                offset = (i - today.weekday()) % 7
                parsed_dates = [(day, today + timedelta(days=offset))]
                break

        if parsed_dates and time_match:
            combined_dt = parse_date(f"{parsed_dates[0][1].strftime('%Y-%m-%d')} {time_match.group(1)}", settings=settings)
            if combined_dt:
                parsed_dates = [(f"{parsed_dates[0][0]} {time_match.group(1)}", combined_dt)]

    # Vague time
    vague_time_block = None
    if "morning" in user_input_lower: vague_time_block = (9, 12)
    elif "afternoon" in user_input_lower: vague_time_block = (12, 17)
    elif "evening" in user_input_lower: vague_time_block = (17, 20)
    elif "night" in user_input_lower: vague_time_block = (20, 22)

    print("🔍 All matched date tokens:")
    for text, dt in parsed_dates:
        print(f" - '{text}' -> {dt}")

    # ⏳ Awaiting date → user now sent it
    if chat_context.pending_booking and chat_context.pending_booking.get("awaiting_date") and parsed_dates:
        date_obj = parsed_dates[0][1]
        date_str = date_obj.strftime("%Y-%m-%d")
        chat_context.pending_booking = {"date": date_str, "awaiting_time": True}
        chat_context.update_date(date_str)
        return "⏰ What time should I schedule it?"

    # ⏳ Awaiting time from date input
    if chat_context.pending_booking and chat_context.pending_booking.get("awaiting_time") and parsed_dates:
        date_obj = parsed_dates[0][1]
        date_str = date_obj.strftime("%Y-%m-%d")
        chat_context.pending_booking["date"] = date_str

        if date_obj.hour or date_obj.minute:
            chat_context.pending_booking["time"] = date_obj.strftime("%I:%M %p")
            del chat_context.pending_booking["awaiting_time"]
            return "📝 What should I title the event?"
        return "⏰ What time should I schedule it?"

    # 🔁 Reschedule intent without full info
    if not parsed_dates and any(kw in user_input_lower for kw in ["reschedule", "change", "postpone", "move"]):
        chat_context.pending_reschedule = True
        return "📝 Please specify the event name you'd like to reschedule."

    # 🗑 Delete intent without full info
    if not parsed_dates and any(kw in user_input_lower for kw in ["delete", "remove", "cancel"]):
        chat_context.pending_delete = True
        return "📝 Please specify the event name you'd like to delete."

    # 🗓 Booking intent without date
    if not parsed_dates and any(kw in user_input_lower for kw in ["book", "schedule", "meeting", "set up", "add", "lock", "event"]):
        chat_context.pending_booking = {"awaiting_date": True}
        return "📅 What date should I schedule the meeting?"

    # ❌ No date parsed and no clear intent
    if not parsed_dates:
        if any(kw in user_input_lower for kw in ["hi", "hello", "hey"]):
            return "👋 Hi there! I can help you manage your calendar — try saying something like 'Book meeting on Friday' or 'Check availability on July 10'."

        if any(kw in user_input_lower for kw in ["what can you do", "help", "who are you", "abilities", "features"]):
            return (
                "🧠 I'm your Calendar Assistant! Here's what I can do:\n"
                "- 📅 Book a meeting (e.g., 'Schedule a call on Friday at 4 PM')\n"
                "- 🔁 Reschedule an event (e.g., 'Reschedule 'Team Sync' to Monday at 11 AM')\n"
                "- 🗑️ Delete an event (e.g., 'Delete 'Project Review' from tomorrow')\n"
                "- 🔍 Check your availability (e.g., 'Check availability on July 15')\n\n"
                "💬 Just tell me what you'd like to do!"
            )

        return "Sorry, I didn't catch that. Try asking me to book, reschedule, or delete a meeting."

    # 🧠 Final date to use
    date_obj = parsed_dates[0][1]
    date_str = date_obj.strftime("%Y-%m-%d")
    chat_context.update_date(date_str)

    # ✅ Check Availability
    if any(kw in user_input_lower for kw in [
        "availability", "available", "free", "slots",
        "check my calendar", "check availability",
        "what's open", "open times", "free times",
        "calendar openings", "any slot", "do i have time",
        "can i book", "am i free", "is my calendar free"
    ]):
        return check_availability(date_str)

    # 🔁 Reschedule
    if any(kw in user_input_lower for kw in [
        "reschedule", "change", "postpone", "move",
        "shift", "delay", "update", "edit", "modify",
        "adjust", "rearrange", "push back", "bring forward",
        "change the time", "resched"
    ]):
        title_match = (
            re.search(r"['\"](.+?)['\"]", user_input) or
            re.search(r"reschedule (.*?) to", user_input_lower)
        )

        # Support memory fallback
        title = chat_context.pending_reschedule_title if hasattr(chat_context, "pending_reschedule_title") else None
        if title_match:
            title = title_match.group(1).strip()

        if not title:
            return "❌ Please specify which meeting to reschedule using quotes or like `reschedule Team Sync to 3 PM`"

        title = title_match.group(1).strip()
        to_match = re.search(r"\bto\s+(.+)", user_input_lower)
        new_dt = parse_date(to_match.group(1), settings=settings) if to_match else parsed_dates[-1][1]

        if not new_dt:
            return "❌ Please specify the new date and time clearly."
        
        chat_context.pending_reschedule_title = None

        return reschedule_meeting(title, new_dt.strftime("%Y-%m-%d"), new_dt.strftime("%I:%M %p"))

    # 🗑 Delete
    if any(kw in user_input_lower for kw in [
        "delete", "remove", "cancel", "clear", "discard",
        "drop", "terminate", "cancel meeting", "erase",
        "get rid of", "trash", "kill", "stop", "unschedule"
    ]):
        title_match = (
            re.search(r"['\"](.+?)['\"]", user_input) or
            re.search(r"(?:delete|remove|cancel)\s+(.*?)($|from|on)", user_input_lower)
        )

        # Use fallback if title isn't in this message
        title = chat_context.pending_delete_title if hasattr(chat_context, "pending_delete_title") else None
        if title_match:
            title = title_match.group(1).strip()

        if not title:
            # Start multi-turn flow
            chat_context.pending_delete = True
            chat_context.pending_delete_title = None
            return "📝 Please specify the event name you'd like to delete."

        # Try to find date from message
        date_match = re.search(r"(?:from|on)\s+(.+)", user_input_lower)
        parsed = parse_date(date_match.group(1), settings=settings) if date_match else None

        if not parsed:
            chat_context.pending_delete = True
            chat_context.pending_delete_title = title
            return "📅 Please specify the date of the event you want to delete (e.g., 'tomorrow')."

        # ✅ Reset pending values
        chat_context.pending_delete = False
        chat_context.pending_delete_title = None

        from calendar_utils import delete_event
        return delete_event(title, parsed.strftime("%Y-%m-%d"))

    # 📅 Booking intent
    if any(kw in user_input_lower for kw in [
        "book", "schedule", "meeting", "set up", "add",
        "lock", "event", "create", "plan", "make appointment",
        "put on calendar", "register", "arrange", "organize",
        "invite", "fix", "log", "block time", "set meeting",
        "new meeting"
    ]):
        if not parsed_dates:
            chat_context.pending_booking = {"awaiting_date": True}
            return "📅 What date should I schedule the meeting?"

        if not (date_obj.hour or date_obj.minute):
            chat_context.pending_booking = {"date": date_str, "awaiting_time": True}
            return "⏰ What time should I schedule it?"

        chat_context.pending_booking = {
            "date": date_str,
            "time": date_obj.strftime("%I:%M %p")
        }
        return "📝 What should I title the event?"

    # 🧩 Fallback
    return "Sorry, I didn't understand what you're asking. Try 'Book meeting on Friday' or 'Reschedule 'Team Sync' to 3 PM'."