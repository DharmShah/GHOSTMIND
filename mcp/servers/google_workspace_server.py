import sys
import os
import json
import base64
import asyncio
from typing import Dict, Any, List
import urllib.request
import urllib.parse
import urllib.error

# Standard MCP tools definition for Google Workspace
TOOLS_DEFINITIONS = [
    {
        "name": "search_emails",
        "description": "Searches Gmail messages matching a query (e.g. 'is:unread', 'from:colleague', 'project update').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query query string"},
                "max_results": {"type": "integer", "description": "Maximum number of messages to return (default 5)", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_email",
        "description": "Fetches a Gmail message. Pass the message_id, or pass 'latest' to read the most recent email.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The Gmail message ID, or 'latest' / 'last' for most recent email"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "send_email",
        "description": "Sends an email message via Gmail to a specified recipient (Requires user confirmation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Plaintext email message body"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "list_calendar_events",
        "description": "Lists upcoming events on the user's primary Google Calendar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Maximum number of events to list (default 10)", "default": 10},
                "time_min": {"type": "string", "description": "ISO 8601 minimum start time (default now)"}
            }
        }
    },
    {
        "name": "create_calendar_event",
        "description": "Schedules a new event on Google Calendar (Requires user confirmation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Title or summary of the event"},
                "start_time": {"type": "string", "description": "Start datetime in ISO format, e.g. 2026-11-12T10:00:00Z"},
                "end_time": {"type": "string", "description": "End datetime in ISO format, e.g. 2026-11-12T11:00:00Z"},
                "description": {"type": "string", "description": "Detailed description of the meeting or event"}
            },
            "required": ["summary", "start_time", "end_time"]
        }
    },
    {
        "name": "list_drive_files",
        "description": "Searches or lists files in the user's Google Drive storage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or file name keyword"},
                "page_size": {"type": "integer", "description": "Maximum number of files to return (default 10)", "default": 10}
            }
        }
    },
    {
        "name": "get_drive_file",
        "description": "Retrieves metadata and web link for a specific Google Drive file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "Google Drive file ID"}
            },
            "required": ["file_id"]
        }
    }
]

def get_auth_token() -> str:
    """Retrieves access token injected into process environment by integration service."""
    return (
        os.getenv("GOOGLE_WORKSPACE_ACCESS_TOKEN")
        or os.getenv("ACCESS_TOKEN")
        or os.getenv("BEARER_TOKEN")
        or ""
    ).strip()

def make_google_api_request(url: str, method: str = "GET", payload: Any = None) -> Any:
    """Executes an authenticated HTTP request to Google REST APIs."""
    token = get_auth_token()
    if not token:
        raise ValueError("No Google Workspace access token found. Please connect via OAuth in GHOSTMIND.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "GHOSTMIND-MCP/1.0"
    }

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Google API HTTP {e.code}: {err_body}")
    except Exception as e:
        raise RuntimeError(f"Google API network error: {e}")

# Tool Handlers
def handle_search_emails(args: Dict[str, Any]) -> str:
    raw_query = args.get("query", "")
    query = raw_query.strip() if isinstance(raw_query, str) else ""
    if query.lower() in ("last", "latest", "recent", "my emails", "all", "inbox", "last email", "last mail"):
        query = ""
    max_res = min(int(args.get("max_results", 5)), 20)
    q_param = f"&q={urllib.parse.quote(query)}" if query else ""
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_res}{q_param}"
    data = make_google_api_request(url)
    messages = data.get("messages", [])
    if not messages:
        return f"No emails found matching query: '{raw_query}'"

    summaries = []
    for msg in messages[:max_res]:
        msg_id = msg.get("id")
        try:
            detail = make_google_api_request(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata")
            snippet = detail.get("snippet", "")
            headers = {h["name"].lower(): h["value"] for h in detail.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(No subject)")
            sender = headers.get("from", "(Unknown sender)")
            date = headers.get("date", "")
            summaries.append(f"• ID: {msg_id}\n  From: {sender}\n  Subject: {subject}\n  Date: {date}\n  Snippet: {snippet}")
        except Exception:
            summaries.append(f"• ID: {msg_id}")
    return "\n\n".join(summaries)

def handle_get_email(args: Dict[str, Any]) -> str:
    raw_id = str(args.get("message_id", "")).strip().strip("'\"")
    msg_id = raw_id

    # If LLM passed "last", "latest", "LAST_EMAIL_ID", or a non-hex placeholder, auto-resolve to the latest message
    if not msg_id or msg_id.lower() in ("last", "latest", "recent", "last_email_id", "last_mail", "current") or not all(c in "0123456789abcdefABCDEF" for c in msg_id):
        list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=1"
        list_data = make_google_api_request(list_url)
        messages = list_data.get("messages", [])
        if not messages:
            return "No emails found in your Gmail mailbox."
        msg_id = messages[0]["id"]

    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
    detail = make_google_api_request(url)
    headers = {h["name"].lower(): h["value"] for h in detail.get("payload", {}).get("headers", [])}

    # Extract plain text content from payload
    body_text = ""
    payload = detail.get("payload", {})
    body_data = payload.get("body", {}).get("data")
    if body_data:
        try:
            body_text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        except Exception:
            pass

    if not body_text:
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                part_data = part.get("body", {}).get("data")
                if part_data:
                    try:
                        body_text = base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
                        break
                    except Exception:
                        pass

    content = body_text.strip() if body_text else detail.get("snippet", "")
    return (
        f"• **From:** {headers.get('from', 'Unknown')}\n"
        f"• **To:** {headers.get('to', '')}\n"
        f"• **Subject:** {headers.get('subject', '(No Subject)')}\n"
        f"• **Date:** {headers.get('date', '')}\n\n"
        f"**Content:**\n{content}"
    )

def handle_send_email(args: Dict[str, Any]) -> str:
    to = args.get("to")
    subject = args.get("subject")
    body = args.get("body")
    raw_msg = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}"
    raw_b64 = base64.urlsafe_b64encode(raw_msg.encode("utf-8")).decode("utf-8")

    res = make_google_api_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        method="POST",
        payload={"raw": raw_b64}
    )
    return f"Email sent successfully. Message ID: {res.get('id')}"

def handle_list_calendar_events(args: Dict[str, Any]) -> str:
    max_res = min(int(args.get("max_results", 10)), 50)
    time_min = args.get("time_min", "")
    params = {"maxResults": str(max_res), "singleEvents": "true", "orderBy": "startTime"}
    if time_min:
        params["timeMin"] = time_min
    url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{urllib.parse.urlencode(params)}"
    data = make_google_api_request(url)
    items = data.get("items", [])
    if not items:
        return "No upcoming events found on your Google Calendar."
    events = []
    for it in items:
        start = it.get("start", {}).get("dateTime") or it.get("start", {}).get("date")
        summary = it.get("summary", "(Untitled)")
        events.append(f"• {start} — {summary} (ID: {it.get('id')})")
    return "\n".join(events)

def handle_create_calendar_event(args: Dict[str, Any]) -> str:
    event_body = {
        "summary": args.get("summary"),
        "description": args.get("description", ""),
        "start": {"dateTime": args.get("start_time")},
        "end": {"dateTime": args.get("end_time")}
    }
    res = make_google_api_request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        method="POST",
        payload=event_body
    )
    return f"Calendar event created: '{res.get('summary')}' (ID: {res.get('id')})\nLink: {res.get('htmlLink')}"

def handle_list_drive_files(args: Dict[str, Any]) -> str:
    query = args.get("query", "")
    page_size = min(int(args.get("page_size", 10)), 30)
    params = {"pageSize": str(page_size), "fields": "files(id, name, mimeType, modifiedTime, webViewLink)"}
    if query:
        params["q"] = f"name contains '{query}' and trashed = false"
    url = f"https://www.googleapis.com/drive/v3/files?{urllib.parse.urlencode(params)}"
    data = make_google_api_request(url)
    files = data.get("files", [])
    if not files:
        return f"No Google Drive files found matching '{query}'."
    file_lines = []
    for f in files:
        file_lines.append(f"• {f.get('name')} (ID: {f.get('id')})\n  Type: {f.get('mimeType')}\n  Link: {f.get('webViewLink', '')}")
    return "\n\n".join(file_lines)

def handle_get_drive_file(args: Dict[str, Any]) -> str:
    file_id = args.get("file_id")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,mimeType,size,webViewLink,createdTime,modifiedTime"
    data = make_google_api_request(url)
    return json.dumps(data, indent=2)

DISPATCHER = {
    "search_emails": handle_search_emails,
    "get_email": handle_get_email,
    "send_email": handle_send_email,
    "list_calendar_events": handle_list_calendar_events,
    "create_calendar_event": handle_create_calendar_event,
    "list_drive_files": handle_list_drive_files,
    "get_drive_file": handle_get_drive_file
}

def process_jsonrpc(line: str) -> None:
    """Handles an incoming JSON-RPC 2.0 message and writes the response to stdout."""
    try:
        req = json.loads(line)
    except Exception:
        return

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        resp = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "google-workspace",
                    "version": "1.0.0"
                }
            }
        }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    elif method == "notifications/initialized":
        # Handshake complete notification, no response required
        pass

    elif method == "tools/list":
        resp = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_DEFINITIONS
            }
        }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        handler = DISPATCHER.get(tool_name)
        if not handler:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' not found."
                }
            }
        else:
            try:
                result_text = handler(arguments)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": str(result_text)}
                        ]
                    }
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Error executing {tool_name}: {e}"}
                        ],
                        "isError": True
                    }
                }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    elif req_id is not None:
        resp = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not implemented."
            }
        }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

def main():
    for line in sys.stdin:
        line = line.strip()
        if line:
            process_jsonrpc(line)

if __name__ == "__main__":
    main()
