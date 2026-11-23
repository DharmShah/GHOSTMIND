import sys
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, List, Optional

# Standard MCP tools definition for Figma
TOOLS_DEFINITIONS = [
    {
        "name": "get_file",
        "description": "Inspects a Figma design file. Returns metadata, document structure, pages, and top-level frames. Accepts a file key or full Figma URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key (e.g. 'AbCdEf123') or full Figma URL (e.g. 'https://www.figma.com/design/AbCdEf123/Project')"
                },
                "depth": {
                    "type": "integer",
                    "description": "Tree traversal depth (default 2 for page and frame summaries)",
                    "default": 2
                }
            },
            "required": ["file_key"]
        }
    },
    {
        "name": "get_file_nodes",
        "description": "Retrieves detailed node data (layout, dimensions, typography, styles, children) for specific Figma node IDs within a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                },
                "ids": {
                    "type": "string",
                    "description": "Comma-separated list of node IDs to inspect (e.g. '0:1,12:34')"
                }
            },
            "required": ["file_key", "ids"]
        }
    },
    {
        "name": "get_comments",
        "description": "Retrieves user review comments and feedback threads on a Figma design file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                }
            },
            "required": ["file_key"]
        }
    },
    {
        "name": "post_comment",
        "description": "Posts a new review comment or replies to an existing comment thread on a Figma design file (Requires user confirmation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                },
                "message": {
                    "type": "string",
                    "description": "Comment text to post"
                },
                "comment_id": {
                    "type": "string",
                    "description": "Optional parent comment ID if replying to an existing thread"
                }
            },
            "required": ["file_key", "message"]
        }
    },
    {
        "name": "delete_comment",
        "description": "Deletes a review comment from a Figma design file (Requires user confirmation).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                },
                "comment_id": {
                    "type": "string",
                    "description": "The ID of the comment to delete"
                }
            },
            "required": ["file_key", "comment_id"]
        }
    },
    {
        "name": "get_image",
        "description": "Renders and generates downloadable image URLs for specified Figma frame or component node IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                },
                "ids": {
                    "type": "string",
                    "description": "Comma-separated node IDs to render into image URLs (e.g. '1:2')"
                },
                "format": {
                    "type": "string",
                    "enum": ["png", "jpg", "svg", "pdf"],
                    "description": "Image export format (default 'png')",
                    "default": "png"
                },
                "scale": {
                    "type": "number",
                    "description": "Image scaling factor between 0.5 and 4 (default 2.0)",
                    "default": 2.0
                }
            },
            "required": ["file_key", "ids"]
        }
    },
    {
        "name": "get_components",
        "description": "Lists all reusable components, variants, and component sets published in a Figma file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                }
            },
            "required": ["file_key"]
        }
    },
    {
        "name": "get_styles",
        "description": "Lists design tokens and styles (colors, typography, elevation effects, grids) defined in a Figma file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_key": {
                    "type": "string",
                    "description": "Figma file key or full Figma URL"
                }
            },
            "required": ["file_key"]
        }
    },
    {
        "name": "get_current_user",
        "description": "Retrieves the authenticated Figma user profile (handle, email, avatar).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

def clean_file_key(file_key_or_url: str) -> str:
    """Extracts raw file key if a full Figma URL was provided."""
    s = str(file_key_or_url).strip()
    match = re.search(r'figma\.com/(?:file|design)/([a-zA-Z0-9_-]+)', s)
    if match:
        return match.group(1)
    return s

def get_auth_token() -> str:
    """Retrieves Figma Personal Access Token or OAuth Bearer token from environment."""
    return (
        os.environ.get("FIGMA_ACCESS_TOKEN")
        or os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN")
        or os.environ.get("ACCESS_TOKEN")
        or os.environ.get("BEARER_TOKEN")
        or ""
    ).strip()

def get_figma_headers() -> Dict[str, str]:
    token = get_auth_token()
    if not token:
        raise ValueError("No Figma access token found. Please enter your Figma Personal Access Token in GHOSTMIND.")

    headers = {
        "User-Agent": "GHOSTMIND-Figma-MCP/1.0",
        "Accept": "application/json"
    }
    # Figma supports 'X-Figma-Token: <token>' (for PAT) or 'Authorization: Bearer <token>' (for OAuth)
    if token.startswith("figd_") or not token.startswith("Bearer "):
        headers["X-Figma-Token"] = token
    else:
        headers["Authorization"] = token
    return headers

def figma_api_request(endpoint: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"https://api.figma.com/v1{endpoint}"
    headers = get_figma_headers()
    body_bytes = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_msg)
            msg = err_json.get("err") or err_json.get("message") or err_msg
        except Exception:
            msg = err_msg
        raise RuntimeError(f"Figma API error (HTTP {e.code}): {msg}")
    except Exception as e:
        raise RuntimeError(f"Figma request failed: {e}")

# Tool Handlers
def handle_get_file(arguments: Dict[str, Any]) -> str:
    raw_key = arguments.get("file_key", "")
    key = clean_file_key(raw_key)
    if not key:
        return "Error: file_key is required."

    depth = int(arguments.get("depth", 2))
    data = figma_api_request(f"/files/{key}?depth={depth}")

    file_name = data.get("name", "Untitled")
    last_modified = data.get("lastModified", "Unknown")
    version = data.get("version", "1")
    editor_type = data.get("editorType", "figma")

    # Summarize pages and frames
    document = data.get("document", {})
    pages = document.get("children", [])
    page_summaries = []

    for p in pages:
        p_name = p.get("name", "Page")
        frames = [c.get("name", "Frame") for c in p.get("children", []) if c.get("type") in ("FRAME", "SECTION", "COMPONENT")]
        frame_list = ", ".join(frames[:15]) if frames else "(No frames)"
        if len(frames) > 15:
            frame_list += f" and {len(frames) - 15} more..."
        page_summaries.append(f"- **Page '{p_name}'**: {len(frames)} top-level frames: {frame_list}")

    pages_text = "\n".join(page_summaries) if page_summaries else "No pages found."

    return (
        f"### Figma File: {file_name}\n"
        f"• **Key:** `{key}`\n"
        f"• **Type:** {editor_type.title()} | **Version:** {version}\n"
        f"• **Last Modified:** {last_modified}\n\n"
        f"**Structure & Pages:**\n{pages_text}"
    )

def handle_get_file_nodes(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    ids = str(arguments.get("ids", "")).strip()
    if not key or not ids:
        return "Error: file_key and ids are required."

    encoded_ids = urllib.parse.quote(ids)
    data = figma_api_request(f"/files/{key}/nodes?ids={encoded_ids}")

    nodes_dict = data.get("nodes", {})
    if not nodes_dict:
        return f"No nodes found for IDs '{ids}' in file `{key}`."

    lines = [f"### Node Details for File `{key}`:"]
    for nid, node_info in nodes_dict.items():
        doc = node_info.get("document", {})
        name = doc.get("name", nid)
        ntype = doc.get("type", "UNKNOWN")
        box = doc.get("absoluteBoundingBox", {})
        dimensions = f"{box.get('width', 0)}x{box.get('height', 0)}" if box else "N/A"
        characters = doc.get("characters")

        lines.append(f"\n• **Node `{nid}` ({name})**:")
        lines.append(f"  - Type: `{ntype}` | Size: `{dimensions}`")
        if characters:
            lines.append(f"  - Text Content: \"{characters[:200]}\"")

    return "\n".join(lines)

def handle_get_comments(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    if not key:
        return "Error: file_key is required."

    data = figma_api_request(f"/files/{key}/comments")
    comments = data.get("comments", [])
    if not comments:
        return f"No review comments found on Figma file `{key}`."

    lines = [f"### Comments on Figma File `{key}` ({len(comments)} total):"]
    for c in comments[:20]:
        author = c.get("user", {}).get("handle") or c.get("user", {}).get("name") or "User"
        created = c.get("created_at", "")[:16].replace("T", " ")
        msg = c.get("message", "")
        cid = c.get("id", "")
        resolved = "✓ Resolved" if c.get("resolved_at") else "Open"
        lines.append(f"\n• **{author}** ({created}) [{resolved}] (ID: `{cid}`):")
        lines.append(f"  > {msg}")

    return "\n".join(lines)

def handle_post_comment(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    message = arguments.get("message", "").strip()
    if not key or not message:
        return "Error: file_key and message are required."

    payload = {"message": message}
    if arguments.get("comment_id"):
        payload["comment_id"] = str(arguments["comment_id"])

    res = figma_api_request(f"/files/{key}/comments", method="POST", data=payload)
    cid = res.get("id", "created")
    return f"✓ Successfully posted comment (ID: `{cid}`) on Figma file `{key}`."

def handle_delete_comment(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    comment_id = str(arguments.get("comment_id", "")).strip()
    if not key or not comment_id:
        return "Error: file_key and comment_id are required."

    figma_api_request(f"/files/{key}/comments/{comment_id}", method="DELETE")
    return f"✓ Successfully deleted comment `{comment_id}` from Figma file `{key}`."

def handle_get_image(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    ids = str(arguments.get("ids", "")).strip()
    if not key or not ids:
        return "Error: file_key and ids are required."

    fmt = arguments.get("format", "png")
    scale = float(arguments.get("scale", 2.0))
    encoded_ids = urllib.parse.quote(ids)

    data = figma_api_request(f"/images/{key}?ids={encoded_ids}&format={fmt}&scale={scale}")
    images = data.get("images", {})
    if not images:
        return f"Could not generate image URLs for nodes '{ids}' in `{key}`."

    lines = [f"### Rendered Image Exports for File `{key}`:"]
    for nid, img_url in images.items():
        if img_url:
            lines.append(f"• **Node `{nid}`:** [View Rendered Image]({img_url})")
        else:
            lines.append(f"• **Node `{nid}`:** (Render failed or node empty)")

    return "\n".join(lines)

def handle_get_components(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    if not key:
        return "Error: file_key is required."

    data = figma_api_request(f"/files/{key}/components")
    components = data.get("meta", {}).get("components", [])
    if not components:
        return f"No published components found in Figma file `{key}`."

    lines = [f"### Components in Figma File `{key}` ({len(components)} total):"]
    for c in components[:25]:
        name = c.get("name", "Unnamed")
        desc = c.get("description", "")
        cid = c.get("key", "")
        lines.append(f"• **{name}** (Key: `{cid}`){f' — {desc}' if desc else ''}")

    return "\n".join(lines)

def handle_get_styles(arguments: Dict[str, Any]) -> str:
    key = clean_file_key(arguments.get("file_key", ""))
    if not key:
        return "Error: file_key is required."

    data = figma_api_request(f"/files/{key}/styles")
    styles = data.get("meta", {}).get("styles", [])
    if not styles:
        return f"No styles found in Figma file `{key}`."

    lines = [f"### Design Tokens & Styles in `{key}` ({len(styles)} total):"]
    for s in styles[:25]:
        name = s.get("name", "Unnamed")
        stype = s.get("style_type", "STYLE")
        desc = s.get("description", "")
        lines.append(f"• **{name}** (`{stype}`){f' — {desc}' if desc else ''}")

    return "\n".join(lines)

def handle_get_current_user(arguments: Dict[str, Any]) -> str:
    data = figma_api_request("/me")
    handle = data.get("handle", "Unknown")
    email = data.get("email", "Unknown")
    uid = data.get("id", "Unknown")
    return f"### Authenticated Figma Account\n• **Handle:** {handle}\n• **Email:** {email}\n• **User ID:** `{uid}`"

DISPATCHER = {
    "get_file": handle_get_file,
    "get_file_nodes": handle_get_file_nodes,
    "get_comments": handle_get_comments,
    "post_comment": handle_post_comment,
    "delete_comment": handle_delete_comment,
    "get_image": handle_get_image,
    "get_components": handle_get_components,
    "get_styles": handle_get_styles,
    "get_current_user": handle_get_current_user
}

def process_jsonrpc(line: str):
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
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
                    "name": "figma",
                    "version": "1.0.0"
                }
            }
        }
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    elif method == "notifications/initialized":
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

