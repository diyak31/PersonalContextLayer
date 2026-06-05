# Gmail MCP Server

A Gmail MCP server for use with Claude and other MCP-compatible agents.

## Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials JSON → save as `credentials.json` (see `credentials.json` template)
5. Run: `python auth.py`
   - This opens a browser, you approve access, and `token.json` is saved automatically

## Files

- `auth.py` — OAuth2 flow (run once to generate `token.json`)
- `server.py` — MCP server with Gmail tools
- `credentials.json` — **Fill in with your Google Cloud credentials** (never commit the real one)
- `token.json` — **Auto-generated after running `auth.py`** (never commit)

## Notes

- `credentials.json` and `token.json` are in `.gitignore` — keep them out of version control
- See `token.json.example` for the expected token format
