"""Agent loop: the core processing engine."""

import asyncio
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.sticker import StickerTool
from nanobot.agent.subagent import SubagentManager
from nanobot.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        allowed_paths: list[str] | None = None,
        protected_paths: list[str] | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.allowed_paths = [Path(p).expanduser().resolve() for p in (allowed_paths or [])]
        self.protected_paths = [Path(p).expanduser().resolve() for p in (protected_paths or [])]
        
        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        self._running = False
        self._register_default_tools()
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        protected = self.protected_paths or None

        # File tools — read/list have no restrictions; write/edit check protected_paths
        self.tools.register(ReadFileTool())
        self.tools.register(WriteFileTool(protected_paths=protected))
        self.tools.register(EditFileTool(protected_paths=protected))
        self.tools.register(ListDirTool())
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            protected_paths=protected,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
        
        # Sticker tool (for sending image stickers)
        sticker_tool = StickerTool(
            workspace=self.workspace,
            send_callback=self.bus.publish_outbound,
        )
        if sticker_tool._stickers:
            self.tools.register(sticker_tool)
        
        # Custom tools from workspace/tools/*.py (hot-loaded)
        self._load_custom_tools()
    
    # Patterns forbidden in custom tool source code to prevent sandbox escape
    _FORBIDDEN_TOOL_PATTERNS: list[str] = [
        r"\bsubprocess\b",
        r"\bos\.system\s*\(",
        r"\bos\.popen\s*\(",
        r"\bos\.exec\w*\s*\(",
        r"\bos\.spawn\w*\s*\(",
        r"\bos\.remove\s*\(",
        r"\bos\.unlink\s*\(",
        r"\bos\.rmdir\s*\(",
        r"\bshutil\.rmtree\s*\(",
        r"\b__import__\s*\(",
        r"\bimportlib\b",
        r"\bopen\s*\(",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bcompile\s*\(",
        r"\bctypes\b",
        r"\bsocket\b",
        r"\bpathlib\.Path\s*\(",
    ]

    def _scan_for_forbidden_patterns(self, source: str) -> list[str]:
        """Scan Python source for forbidden patterns.

        Returns a list of human-readable violation descriptions.  An empty
        list means the source passed the safety check.
        """
        violations: list[str] = []
        for pattern in self._FORBIDDEN_TOOL_PATTERNS:
            match = re.search(pattern, source)
            if match:
                violations.append(f"forbidden pattern: {match.group()}")
        return violations

    def _load_custom_tools(self) -> None:
        """Hot-load custom tools from ``{workspace}/tools/*.py``.

        Each Python file must define exactly one class that inherits from
        :class:`Tool`.  The file is scanned for dangerous patterns before
        being imported — any file that contains forbidden calls (e.g.
        ``subprocess``, ``open()``, ``eval()``) is rejected.

        Custom tools **cannot** override built-in tools.  If a name
        collision is detected the file is skipped with a warning.

        Files whose names start with ``_`` are ignored.
        """
        custom_tools_dir = self.workspace / "tools"
        if not custom_tools_dir.is_dir():
            return

        from nanobot.agent.tools.base import Tool as BaseTool

        protected = self.protected_paths or None

        for py_file in sorted(custom_tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            # Skip files that are already loaded (hot-reload guard)
            module_name = f"nanobot_custom_tool_{py_file.stem}"

            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception as exc:
                logger.error(f"Cannot read custom tool {py_file.name}: {exc}")
                continue

            # Static safety scan
            violations = self._scan_for_forbidden_patterns(source)
            if violations:
                logger.warning(
                    f"Custom tool {py_file.name} blocked — "
                    f"safety violations: {', '.join(violations)}"
                )
                continue

            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseTool)
                        and attr is not BaseTool
                    ):
                        # Pass protected_paths when the constructor accepts it
                        try:
                            tool_instance = attr(protected_paths=protected)
                        except TypeError:
                            tool_instance = attr()

                        if self.tools.has(tool_instance.name):
                            logger.warning(
                                f"Custom tool '{tool_instance.name}' from "
                                f"{py_file.name} conflicts with existing tool, skipped"
                            )
                            continue

                        self.tools.register(tool_instance)
                        logger.info(
                            f"Loaded custom tool '{tool_instance.name}' "
                            f"from {py_file.name}"
                        )
                        break  # one tool per file

            except Exception as exc:
                logger.error(f"Failed to load custom tool from {py_file.name}: {exc}")

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        # Hot-reload custom tools so newly created tools take effect immediately
        self._load_custom_tools()
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")
        
        # Intercept reset commands (/reset, /clear, /new)
        stripped_content = msg.content.strip().lower()
        if stripped_content in {"/reset", "/clear", "/new"}:
            return await self._handle_reset_command(msg)
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)
        
        sticker_tool = self.tools.get("sticker")
        if isinstance(sticker_tool, StickerTool):
            sticker_tool.set_context(msg.channel, msg.chat_id, metadata=msg.metadata)
        
        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        
        # Agent loop
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Call LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            # Handle tool calls
            if response.has_tool_calls:
                # Add assistant message with tool calls
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)  # Must be JSON string
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                # Execute tools
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # No tool calls, we're done
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},  # Pass through for channel-specific needs (e.g. Slack thread_ts)
        )
    
    async def _handle_reset_command(self, msg: InboundMessage) -> OutboundMessage:
        """Handle /reset, /clear, /new commands by clearing session history."""
        session_key = msg.session_key
        session = self.sessions.get_or_create(session_key)
        msg_count = len(session.messages)
        session.clear()
        self.sessions.save(session)
        
        logger.info(f"Session reset for {session_key} (cleared {msg_count} messages)")
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="🔄 Conversation history cleared. Let's start fresh!",
            metadata=msg.metadata or {},
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            if response.has_tool_calls:
                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )
                
                for tool_call in response.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info(f"Tool call: {tool_call.name}({args_str[:200]})")
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
