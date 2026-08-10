"""
Chat Module - conversational AI with session management.

This module provides:
- ChatAgent: Legacy conversational agent with RAG/Web Search support
- AgenticChatPipeline: exploring agent loop + respond stage with autonomous tool use
- SessionManager: Chat session persistence and management

Usage:
    from deeptutor.agents.chat import ChatAgent, SessionManager

    agent = ChatAgent(language="en")
    response = await agent.process(
        message="What is machine learning?",
        history=[],
        kb_name="ai_textbook",
        enable_rag=True,
        enable_web_search=False
    )
"""

from .agentic_pipeline import AgenticChatPipeline
from .chat_agent import ChatAgent
from .session_manager import SessionManager
from .tool_protocol_filter import ToolProtocolFilter as _ChunkSafeToolProtocolFilter
from . import agent_loop as _agent_loop

# ``AgentLoop`` resolves ``ToolProtocolFilter`` from its module globals when an
# LLM call starts. Replace the legacy regex implementation after the module is
# loaded so every pipeline path gets the chunk-safe state machine without
# duplicating the large agent-loop implementation.
_agent_loop.ToolProtocolFilter = _ChunkSafeToolProtocolFilter

__all__ = ["AgenticChatPipeline", "ChatAgent", "SessionManager"]
