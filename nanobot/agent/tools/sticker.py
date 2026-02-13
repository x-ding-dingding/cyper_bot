"""Sticker tool for sending image stickers to chat channels."""

import json
from pathlib import Path
from typing import Any, Callable, Awaitable

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage


class StickerTool(Tool):
    """Tool to send image stickers from a local sticker library.

    Stickers are sent immediately when the tool is called, following the
    normal tool-calling flow: LLM calls the tool first, then composes its
    text reply based on the tool result.
    """

    def __init__(
        self,
        workspace: Path,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._workspace = workspace
        self._send_callback = send_callback
        self._default_channel = ""
        self._default_chat_id = ""
        self._default_metadata: dict[str, Any] = {}
        self._stickers: dict[str, str] = {}
        self._load_stickers()

    def _load_stickers(self) -> None:
        """Load sticker index from workspace/stickers/index.json."""
        index_path = self._workspace / "stickers" / "index.json"
        if not index_path.exists():
            logger.debug("No sticker index found, sticker tool will be inactive")
            return

        try:
            raw = index_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._stickers = {k: v for k, v in data.items() if isinstance(v, str)}
                logger.info(f"Loaded {len(self._stickers)} stickers from index")
        except Exception as error:
            logger.warning(f"Failed to load sticker index: {error}")

    def reload(self) -> None:
        """Reload the sticker index from disk."""
        self._stickers.clear()
        self._load_stickers()

    def set_context(
        self, channel: str, chat_id: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Set the current message context for routing sticker messages."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_metadata = metadata or {}

    @property
    def name(self) -> str:
        return "sticker"

    @property
    def description(self) -> str:
        available = ", ".join(self._stickers.keys()) if self._stickers else "none"
        return (
            "Send an image sticker to express emotion. "
            f"Available stickers: [{available}]. "
            "The sticker will be sent immediately. Then give your text reply after calling this tool. "
            "The sticker is a supplement to your words, never a replacement. "
            "Do not overuse; pick one only when the emotion is strong or playful."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        sticker_names = list(self._stickers.keys())
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The sticker name to send",
                    "enum": sticker_names if sticker_names else ["none"],
                },
            },
            "required": ["name"],
        }

    async def execute(self, name: str = "", **kwargs: Any) -> str:
        if not self._stickers:
            return "Sticker library is empty. Ask the user to add stickers to workspace/stickers/index.json."

        photo_url = self._stickers.get(name)
        if not photo_url:
            available = ", ".join(self._stickers.keys())
            return f"Sticker '{name}' not found. Available: [{available}]"

        channel = self._default_channel
        chat_id = self._default_chat_id
        if not channel or not chat_id:
            return "Error: No target channel/chat specified for sticker"

        if not self._send_callback:
            return "Error: Message sending not configured"

        sticker_metadata = {
            **self._default_metadata,
            "msg_type": "image",
            "photo_url": photo_url,
        }

        sticker_message = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content="",
            metadata=sticker_metadata,
        )

        try:
            await self._send_callback(sticker_message)
            logger.info(f"Sticker '{name}' sent to {channel}:{chat_id}")
            return f"Sticker '{name}' sent successfully."
        except Exception as error:
            logger.error(f"Failed to send sticker '{name}': {error}")
            return f"Error: Failed to send sticker '{name}': {error}"