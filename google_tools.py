"""
Google API helpers for JARVIS — Gmail and Calendar
"""

import os
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_token.json")
CREDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_credentials.json")
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly'
]

def get_creds():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds

def get_unread_emails(max_results=5) -> str:
    """Returns a summary of unread emails."""
    try:
        creds = get_creds()
        gmail = build('gmail', 'v1', credentials=creds)
        results = gmail.users().messages().list(
            userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results
        ).execute()

        messages = results.get('messages', [])
        total = results.get('resultSizeEstimate', 0)

        if not messages:
            return "No unread emails."

        lines = [f"{total} unread emails. Most recent:"]
        for msg in messages[:max_results]:
            detail = gmail.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['Subject', 'From']
            ).execute()
            headers = {h['name']: h['value'] for h in detail['payload']['headers']}
            subject = headers.get('Subject', '(no subject)')[:60]
            sender = headers.get('From', '').split('<')[0].strip()[:30]
            lines.append(f"- {subject} from {sender}")

        return "\n".join(lines)
    except Exception as e:
        return f"Gmail error: {e}"

def get_calendar_events(days=1) -> str:
    """Returns upcoming calendar events for the next N days."""
    try:
        creds = get_creds()
        cal = build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.now(datetime.timezone.utc)
        end = now + datetime.timedelta(days=days)

        events_result = cal.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        if not events:
            return f"No events in the next {days} day(s)."

        lines = []
        for e in events:
            start = e['start'].get('dateTime', e['start'].get('date'))
            # Parse and format nicely
            if 'T' in start:
                dt = datetime.datetime.fromisoformat(start)
                time_str = dt.strftime("%A %I:%M %p").lstrip("0")
            else:
                time_str = start
            lines.append(f"- {e['summary']} on {time_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Calendar error: {e}"
