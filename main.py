import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import ChatOllama
from langchain.agents import create_agent

import ollama_service

app = FastAPI(title="Pastel AI Local Chatbot")

# Enable CORS for local desktop webview and browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, compatible with PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Lazy-loaded LLM and agent
_llm = None
_agent = None

def get_agent():
    global _llm, _agent
    if _agent is None:
        _llm = ChatOllama(
            model=ollama_service.REQUIRED_MODEL,
            temperature=0,
        )
        _agent = create_agent(model=_llm)
    return _agent


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    html_path = get_resource_path("index.html")
    if not os.path.exists(html_path):
        # Fallback to local index.html if current working directory
        html_path = "index.html"
    return FileResponse(html_path)


@app.get("/status")
@app.get("/api/status")
def status():
    """Returns local system readiness (Ollama running & model availability)."""
    return ollama_service.check_system_readiness()


@app.post("/chat")
def chat(request: ChatRequest):
    # Verify local Ollama readiness first
    readiness = ollama_service.check_system_readiness()
    if not readiness["ready"]:
        raise HTTPException(
            status_code=503,
            detail=readiness["message"]
        )

    try:
        agent = get_agent()
        result = agent.invoke({
            "messages": [
                {"role": "user", "content": request.message}
            ]
        })

        return {
            "response": result["messages"][-1].content
        }

    except Exception as e:
        # Check if Ollama crashed during invocation
        err_msg = str(e)
        if "connection refused" in err_msg.lower() or "connect" in err_msg.lower():
            err_msg = (
                "Lost connection to local Ollama. Please ensure Ollama is running "
                "on http://127.0.0.1:11434."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Local model error: {err_msg}"
        )
