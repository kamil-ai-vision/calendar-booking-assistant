from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")