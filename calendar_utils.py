from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from dateutil.parser import parse
import pytz
import streamlit as st
import json

from config import GOOGLE_CALENDAR_ID, GOOGLE_SERVICE_ACCOUNT_FILE

# 📌 Load credentials and calendar ID from Streamlit secrets
GOOGLE_CALENDAR_ID = st.secrets["GOOGLE_CALENDAR_ID"]
service_account_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])

# 📌 Authenticate with Google Calendar
def get_calendar_service():
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    service = build('calendar', 'v3', credentials=credentials)
    return service

# ✅ Check available 30-min slots on a date
def get_free_slots(date: str, timezone="Asia/Kolkata"):
    print(f"[DEBUG] get_free_slots called with date: {date}")
    try:
        service = get_calendar_service()
        tz = pytz.timezone(timezone)

        # 📅 Localize start and end of the day
        start_datetime = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        end_datetime = start_datetime + timedelta(days=1)

        # 📤 Fetch events for the date
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_datetime.isoformat(),
            timeMax=end_datetime.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"[DEBUG] Fetched {len(events)} events for {date}")

        # ⏳ Convert event times to timezone-aware datetime in local timezone
        busy_times = []
        for event in events:
            if 'dateTime' in event['start']:
                busy_start = parse(event['start']['dateTime']).astimezone(tz)
                busy_end = parse(event['end']['dateTime']).astimezone(tz)
                busy_times.append((busy_start, busy_end))

        # 🧮 Generate 30-min time slots from 9 AM to 5 PM
        slots = []
        current = start_datetime.replace(hour=9, minute=0, second=0, microsecond=0)
        work_end = start_datetime.replace(hour=17, minute=0, second=0, microsecond=0)

        while current < work_end:
            slot_start = current
            slot_end = current + timedelta(minutes=30)
            current = slot_end

            # ❌ Check if this slot overlaps with any busy time
            overlaps = any(slot_start < b_end and slot_end > b_start for b_start, b_end in busy_times)

            if not overlaps:
                slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat()
                })

        # ✅ Return fallback if no slots are available
        if not slots:
            print("[DEBUG] No free slots available. Returning fallback response.")
            return [{
                "start": None,
                "end": None,
                "note": "❌ No free slots available on this date."
            }]

        print(f"[DEBUG] Returning {len(slots)} free slots")
        return slots

    except Exception as e:
        print(f"❌ Error in get_free_slots: {e}")
        return [{
            "start": None,
            "end": None,
            "note": f"❌ Failed to fetch free slots due to error: {e}"
        }]

# ✅ Book an event
def book_slot(start: dict, end: dict, summary="Meeting", description="Booked via AI assistant"):
    try:
        print(f"[DEBUG] book_slot called with: start={start}, end={end}, summary={summary}")
        
        service = get_calendar_service()

        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start["dateTime"],
                'timeZone': start["timeZone"]
            },
            'end': {
                'dateTime': end["dateTime"],
                'timeZone': end["timeZone"]
            },
        }

        created_event = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()

        print(f"[DEBUG] Event created: {created_event['id']}")
        return {
            "id": created_event["id"],
            "summary": created_event["summary"],
            "start": created_event["start"]["dateTime"],
            "end": created_event["end"]["dateTime"]
        }

    except Exception as e:
        print(f"❌ Error in book_slot: {e}")
        raise e
    
# Change event date and time (Reschedule)
def update_event_time(title: str, date: str, new_start: datetime, new_end: datetime, timezone="Asia/Kolkata") -> str:
    """
    Update the time of an existing event matching the title on a given date.
    """
    try:
        print(f"[DEBUG] update_event_time: Looking for event '{title}' on {date} to reschedule")
        service = get_calendar_service()
        tz = pytz.timezone(timezone)

        # Define date window for the search
        start_of_day = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        end_of_day = start_of_day + timedelta(days=1)

        # Fetch events for the day
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"[DEBUG] Fetched {len(events)} events on {date}")

        # Try to find the event with the matching title
        for event in events:
            if event.get("summary", "").strip().lower() == title.strip().lower():
                print(f"[DEBUG] Found event to reschedule: {event['id']}")

                event['start'] = {
                    'dateTime': new_start.isoformat(),
                    'timeZone': timezone
                }
                event['end'] = {
                    'dateTime': new_end.isoformat(),
                    'timeZone': timezone
                }

                updated_event = service.events().update(
                    calendarId=GOOGLE_CALENDAR_ID,
                    eventId=event["id"],
                    body=event
                ).execute()

                print(f"[DEBUG] Event rescheduled: {updated_event['id']}")
                return f"✅ Rescheduled **{title}** to {new_start.strftime('%Y-%m-%d %I:%M %p')}"

        return f"❌ No event found with title **{title}** on {date}."

    except Exception as e:
        print(f"[ERROR:update_event_time] {str(e)}")
        return f"❌ Failed to reschedule meeting: {str(e)}"
    
# 🔍 Find events by title (across all future dates)
def find_events_by_title(title: str):
    try:
        service = get_calendar_service()
        now = datetime.utcnow().isoformat() + 'Z'

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=now,
            maxResults=10,
            singleEvents=True,
            orderBy='startTime',
            q=title
        ).execute()

        matched_events = [e for e in events_result.get('items', []) if e.get('summary', '').lower() == title.lower()]
        print(f"[DEBUG] Found {len(matched_events)} events matching '{title}'")
        return matched_events

    except Exception as e:
        print(f"[ERROR] find_events_by_title: {e}")
        return []
    

def get_today_events():
    try:
        tz = pytz.timezone("Asia/Kolkata")
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=today.isoformat(),
            timeMax=tomorrow.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return ["🟢 Nothing to do today."]

        formatted = []
        for event in events:
            start_str = "All Day"
            if 'dateTime' in event['start']:
                start = parse(event['start']['dateTime']).astimezone(tz)
                start_str = start.strftime("%I:%M %p")
            elif 'date' in event['start']:
                start = parse(event['start']['date'])
                # optional: skip if not today
                if start.date() != today.date():
                    continue

            summary = event.get("summary", "No Title")
            formatted.append(f"""
            <div style='margin-bottom:0.75rem; padding: 0.4rem 0.6rem; background-color: #2c2c2c; border-radius: 8px;'>
                <span style="color:#f44336; font-weight:bold;">⏰ {start_str}</span><br>
                <span style="color:#ddd;">{summary}</span>
            </div>
            """)
        return formatted or ["🟢 Nothing to do today."]

    except Exception as e:
        print(f"[ERROR:get_today_events] {e}")
        return ["⚠️ Could not load events. Try again later."]

# 🗑️ Delete event by ID
def delete_event_by_id(event_id: str):
    try:
        service = get_calendar_service()
        service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
        print(f"[DEBUG] Successfully deleted event ID: {event_id}")
    except Exception as e:
        print(f"[ERROR] delete_event_by_id: {e}")
    

def delete_event(title: str, date: str, timezone="Asia/Kolkata") -> str:
    """
    Deletes the first event matching the title on the given date.
    """
    try:
        print(f"[TOOL:delete_event] Attempting to delete event titled '{title}' on {date}")
        if not title.strip():
            return "❌ Please provide a valid event title to delete."

        service = get_calendar_service()
        tz = pytz.timezone(timezone)

        start_of_day = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        end_of_day = start_of_day + timedelta(days=1)

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        print(f"[DEBUG] Found {len(events)} events on {date}")

        for event in events:
            if event.get("summary", "").strip().lower() == title.strip().lower():
                event_id = event["id"]
                service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
                print(f"[DEBUG] Deleted event: {event_id}")
                return f"🗑️ Event deleted:\n\n**{title}** on {date}"

        return f"⚠️ No matching event found with title '**{title}**' on {date}."

    except Exception as e:
        print(f"❌ Error in delete_event: {e}")
        return f"❌ Failed to delete event '{title}' on {date}: {e}"
