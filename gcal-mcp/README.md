# Google Calendar MCP Server

A Google Calendar MCP server for use with Claude and other MCP-compatible agents.

## Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Calendar API for your project
3. Go to APIs & Services → Credentials → OAuth 2.0 Client IDs → Desktop app
4. Download credentials JSON → save as `credentials.json` (see template)
5. Run: `python auth.py`
   - A browser opens, you approve, and `token.json` is saved automatically

## Files

- `auth.py` — OAuth2 flow (run once to generate `token.json`)
- `server.py` — MCP server with Calendar tools
- `credentials.json` — **Fill in with your Google Cloud credentials** (never commit the real one)
- `token.json` — **Auto-generated after running `auth.py`** (never commit)
- `token.json.example` — Example token format for reference

## Notes

- `credentials.json` and `token.json` are in `.gitignore`
- You can reuse the same Google Cloud project/credentials as `gmail-mcp`
