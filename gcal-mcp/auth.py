"""
OAuth2 authentication for Google Calendar.

First-time setup:
1. Copy credentials.json from gmail-mcp (same Google Cloud project), or
   download a new one from console.cloud.google.com:
   APIs & Services → Credentials → OAuth 2.0 Client IDs → Desktop app
2. Make sure Google Calendar API is enabled in your project.
3. Run: python auth.py
   A browser opens, you approve, token.json is saved.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")


def get_credentials() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_FILE}.\n"
                    "Download OAuth2 credentials from Google Cloud Console "
                    "(APIs & Services → Credentials → Create OAuth client ID → Desktop app).\n"
                    "Also ensure the Google Calendar API is enabled for your project."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


if __name__ == "__main__":
    creds = get_credentials()
    print("Authentication successful. token.json saved.")
    print(f"Valid: {creds.valid}, Scopes: {creds.scopes}")
