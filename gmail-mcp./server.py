import base64
import email as email_lib
from datetime import datetime, timezone, timedelta
from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
from auth import get_credentials

mcp = FastMCP("gmail")


def _get_service():
    return build("gmail", "v1", credentials=get_credentials())


def _decode_body(payload: dict) -> str:
    """Recursively extract plain text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _decode_body(part)
            if text:
                return text
    return ""


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


@mcp.tool()
def search_emails(query: str, max_results: int = 10) -> str:
    """
    Search Gmail using any Gmail search query.
    Examples:
      - "from:boss@company.com is:unread"
      - "subject:invoice newer_than:7d"
      - "label:important"
    Returns a list of matching emails with sender, subject, date, and snippet.
    """
    service = _get_service()
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        return f"No emails found for query: {query}"

    lines = []
    for msg in messages:
        m = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = m.get("payload", {}).get("headers", [])
        lines.append(
            f"ID: {m['id']}\n"
            f"  From:    {_header(headers, 'From')}\n"
            f"  Subject: {_header(headers, 'Subject')}\n"
            f"  Date:    {_header(headers, 'Date')}\n"
            f"  Snippet: {m.get('snippet', '')}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def get_email(message_id: str) -> str:
    """
    Get the full content of an email by its ID (obtained from search_emails).
    Returns sender, subject, date, and full body text.
    """
    service = _get_service()
    m = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    headers = m.get("payload", {}).get("headers", [])
    body = _decode_body(m.get("payload", {}))

    return (
        f"From:    {_header(headers, 'From')}\n"
        f"To:      {_header(headers, 'To')}\n"
        f"Subject: {_header(headers, 'Subject')}\n"
        f"Date:    {_header(headers, 'Date')}\n"
        f"\n{body.strip()}"
    )


@mcp.tool()
def get_recent_emails(max_results: int = 20, unread_only: bool = False) -> str:
    """
    Get the most recent emails from your inbox.
    Set unread_only=True to only show unread messages.
    """
    query = "in:inbox is:unread" if unread_only else "in:inbox"
    return search_emails(query, max_results)


@mcp.tool()
def get_unread_count() -> str:
    """Get the count of unread emails in your inbox."""
    service = _get_service()
    result = service.users().labels().get(userId="me", id="INBOX").execute()
    unread = result.get("messagesUnread", 0)
    total = result.get("messagesTotal", 0)
    return f"Inbox: {unread} unread out of {total} total messages."


@mcp.tool()
def list_labels() -> str:
    """List all Gmail labels (folders) in your account."""
    service = _get_service()
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    user_labels = [l for l in labels if l["type"] == "user"]
    system_labels = [l for l in labels if l["type"] == "system"]

    lines = ["=== System Labels ==="]
    lines += [f"  {l['name']}" for l in system_labels]
    lines += ["", "=== Your Labels ==="]
    lines += [f"  {l['name']} (ID: {l['id']})" for l in user_labels]
    return "\n".join(lines)


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email.
    Args:
        to: recipient email address
        subject: email subject line
        body: plain text body of the email
    """
    service = _get_service()
    profile = service.users().getProfile(userId="me").execute()
    sender = profile["emailAddress"]

    message = email_lib.message.EmailMessage()
    message["To"] = to
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(body)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return f"Email sent successfully. Message ID: {result['id']}"


@mcp.tool()
def get_emails_from_sender(sender_email: str, max_results: int = 10) -> str:
    """Get recent emails from a specific sender."""
    return search_emails(f"from:{sender_email}", max_results)


@mcp.tool()
def get_emails_by_date_range(days_back: int = 7, max_results: int = 20) -> str:
    """
    Get emails received in the last N days.
    Args:
        days_back: how many days back to look (default 7)
        max_results: max number of emails to return
    """
    return search_emails(f"in:inbox newer_than:{days_back}d", max_results)


if __name__ == "__main__":
    mcp.run(transport="stdio")
