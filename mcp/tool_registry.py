import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from mcp.models import MCPToolDefinition, ActionClassification

logger = logging.getLogger("ghostmind.mcp.tool_registry")

class MCPToolRegistry:
    """
    Central repository for discovered MCP tools with dynamic relevance filtering
    to avoid blowing Qwen 2.5 3B token limits.
    """

    def __init__(self):
        # Map: server_name -> {tool_name: MCPToolDefinition}
        self._tools_by_server: Dict[str, Dict[str, MCPToolDefinition]] = {}

    def register_tools(self, server_name: str, tools: List[MCPToolDefinition]) -> None:
        """Stores discovered tool definitions for a connected server."""
        self._tools_by_server[server_name] = {t.name: t for t in tools}
        logger.info(f"Registered {len(tools)} tools in registry for '{server_name}'")

    def unregister_tools(self, server_name: str) -> None:
        """Removes tools for a disconnected server."""
        self._tools_by_server.pop(server_name, None)

    def get_all_tools(self) -> List[MCPToolDefinition]:
        """Returns all currently registered tools across all active servers."""
        all_tools = []
        for server_tools in self._tools_by_server.values():
            all_tools.extend(server_tools.values())
        return all_tools

    def get_tool(self, server_name: str, tool_name: str) -> Optional[MCPToolDefinition]:
        """Looks up a specific tool on a server."""
        return self._tools_by_server.get(server_name, {}).get(tool_name)

    def find_tool(self, tool_name: str, candidate_server: Optional[str] = None) -> Optional[MCPToolDefinition]:
        """Finds a tool by name, optionally preferring candidate_server."""
        if candidate_server and candidate_server in self._tools_by_server:
            tool = self._tools_by_server[candidate_server].get(tool_name)
            if tool:
                return tool

        for server_tools in self._tools_by_server.values():
            if tool_name in server_tools:
                return server_tools[tool_name]
        return None

    def filter_relevant_tools(self, prompt: str, max_tools: int = 5) -> List[MCPToolDefinition]:
        """
        Dynamically filters available tools according to user intent.
        Scores tools based on service name mentions, keywords, and action verbs.
        Never injects all tools at once.
        """
        all_tools = self.get_all_tools()
        if not all_tools:
            return []

        cleaned_prompt = prompt.lower()
        scored_tools: List[Tuple[float, MCPToolDefinition]] = []

        INTENT_SYNONYMS = {
            "send_email": ["mail", "email", "gmail", "send email", "mail to", "email to", "send mail", "write to", "draft mail"],
            "search_emails": ["inbox", "search email", "find email", "unread email", "check email", "check mail", "emails", "my email"],
            "get_email": ["read email", "email content", "message body"],
            "create_calendar_event": ["meeting", "schedule", "calendar event", "appointment", "schedule meeting", "invite", "interview"],
            "list_calendar_events": ["calendar", "agenda", "upcoming events", "my meetings", "schedule"],
            "list_drive_files": ["drive files", "google drive", "drive folder", "search drive", "drive storage", "drive"],
            "get_drive_file": ["drive file", "download file", "open file"],
            "create_issue": ["create issue", "open issue", "file bug", "bug report", "new issue", "issue"],
            "search_repositories": ["search repo", "github repo", "find repository", "repositories"],
            "post_message": ["slack message", "send to slack", "post in channel", "chat message"],
            "create_page": ["notion page", "new page", "create document", "notion document"]
        }

        has_email_addr = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', cleaned_prompt))

        for tool in all_tools:
            score = 0.0
            server_term = tool.server_name.lower().replace("-", " ")

            # Direct server name mention gives high confidence
            if server_term in cleaned_prompt or tool.server_name.lower() in cleaned_prompt:
                score += 10.0

            # Direct intent synonym matches
            for syn in INTENT_SYNONYMS.get(tool.name, []):
                if syn in cleaned_prompt:
                    score += 8.0

            # If prompt has an email address and tool is send_email
            if tool.name == "send_email" and has_email_addr:
                score += 15.0

            if tool.name == "send_email" and any(k in cleaned_prompt for k in ("mail to", "email to", "send email to", "send a mail to")):
                score += 20.0

            # Tool name keywords
            tool_terms = tool.name.lower().split("_")
            for term in tool_terms:
                if len(term) > 2 and (term in cleaned_prompt or (term == "email" and "mail" in cleaned_prompt)):
                    score += 4.0

            # Description keyword matches
            if tool.description:
                desc_words = set(tool.description.lower().split())
                prompt_words = set(cleaned_prompt.split())
                intersection = desc_words.intersection(prompt_words)
                score += len(intersection) * 0.5

            if score > 0:
                scored_tools.append((score, tool))

        # Sort by relevance score descending
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        return [tool for _, tool in scored_tools[:max_tools]]

    def format_tools_for_llm(self, tools: List[MCPToolDefinition]) -> str:
        """
        Builds a compact structured tools context block for Qwen 2.5 3B.
        Provides strict instructions for generating tool calls.
        """
        if not tools:
            return ""

        tool_lines = []
        for t in tools:
            clean_schema = {
                k: v for k, v in t.input_schema.items()
                if k in ("type", "properties", "required")
            }
            props = clean_schema.get("properties", {})
            compact_props = {
                p: {"type": details.get("type", "string"), "description": details.get("description", "")[:60]}
                for p, details in props.items()
            }
            clean_schema["properties"] = compact_props

            type_label = "READ-ONLY (Auto-executable)" if t.classification == ActionClassification.READ_ONLY else "WRITE / ACTION (Requires Confirmation)"
            tool_lines.append(
                f"- Server: `{t.server_name}` | Tool: `{t.name}` [{type_label}]\n"
                f"  Description: {t.description[:120]}\n"
                f"  Parameters: {json.dumps(clean_schema)}"
            )

        instructions = (
            "\n--- AVAILABLE CONNECTED APPLICATION TOOLS (MCP) ---\n"
            "You have direct access to these connected tools:\n"
            + "\n".join(tool_lines) + "\n\n"
            "CRITICAL INSTRUCTIONS FOR TOOL EXECUTION:\n"
            "1. When the user asks you to perform an action (e.g. send an email, schedule a meeting, search records, or create an issue), you MUST use the corresponding tool.\n"
            "2. DO NOT tell the user to perform the action themselves, and DO NOT refuse the request with 'I don't have knowledge of that' when a tool is provided.\n"
            "3. You must invoke the tool using ONLY this exact format:\n"
            '<<<TOOL_INVOCATION: {"server": "<server_name>", "tool": "<tool_name>", "arguments": {<args>}}>>>\n'
            "4. For 'send_email': extract recipient into 'to', provide a clear 'subject', and generate the full formatted email in 'body'.\n"
            "5. For 'get_email': if the user asks to read their last, latest, or recent email, set 'message_id' to 'latest'.\n"
            "6. The system will intercept write actions and request explicit user confirmation with a button before execution.\n"
            "----------------------------------------------------\n"
        )
        return instructions


tool_registry = MCPToolRegistry()

