"""
OAuth2 authentication for Gmail.

First-time setup:
1. Go to https://console.cloud.google.com/
2. Create a project → Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials JSON → save as credentials.json next to this file
5. Run: python auth.py
   This opens a browser, you approve access, and token.json is saved.
   After that, server.py uses token.json automatically (auto-refreshes).
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
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
                    "(APIs & Services → Credentials → Create OAuth client ID → Desktop app)."
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
