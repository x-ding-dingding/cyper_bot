"""Base channel interface for chat platforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager

# Commands that trigger a conversation reset
RESET_COMMANDS = {"/reset", "/clear", "/new"}

class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.
    
    Each channel (Telegram, Discord, etc.) should implement this interface
    to integrate with the nanobot message bus.
    """
    
    name: str = "base"
    
    def __init__(self, config: Any, bus: MessageBus):
        """
        Initialize the channel.
        
        Args:
            config: Channel-specific configuration.
            bus: The message bus for communication.
        """
        self.config = config
        self.bus = bus
        self.session_manager: SessionManager | None = None
        self._running = False    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the channel and begin listening for messages.
        
        This should be a long-running async task that:
        1. Connects to the chat platform
        2. Listens for incoming messages
        3. Forwards messages to the bus via _handle_message()
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass
    
    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through this channel.
        
        Args:
            msg: The message to send.
        """
        pass
    
    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.
        
        Args:
            sender_id: The sender's identifier.
        
        Returns:
            True if allowed, False otherwise.
        """
        allow_list = getattr(self.config, "allow_from", [])
        
        # If no allow list, allow everyone
        if not allow_list:
            return True
        
        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        return False
    
    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Handle an incoming message from the chat platform.
        
        This method checks permissions, intercepts reset commands,
        and forwards normal messages to the bus.
        
        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/channel identifier.
            content: Message text content.
            media: Optional list of media URLs.
            metadata: Optional channel-specific metadata.
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for sender {sender_id} on channel {self.name}. "
                f"Add them to allowFrom list in config to grant access."
            )
            return
        
        # Intercept reset commands to clear conversation history
        stripped = content.strip().lower()
        if stripped in RESET_COMMANDS:
            await self._handle_reset(chat_id, metadata=metadata)
            return
        
        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {}
        )
        
        await self.bus.publish_inbound(msg)
    
    async def _handle_reset(self, chat_id: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Clear conversation history for the given chat and send a confirmation.
        
        Args:
            chat_id: The chat/channel identifier.
            metadata: Optional channel-specific metadata (needed for group message routing).
        """
        session_key = f"{self.name}:{chat_id}"
        
        if self.session_manager is None:
            logger.warning(f"/reset on {self.name} but session_manager is not available")
            await self.send(OutboundMessage(
                channel=self.name,
                chat_id=str(chat_id),
                content="⚠️ Session management is not available.",
                metadata=metadata or {},
            ))
            return
        
        session = self.session_manager.get_or_create(session_key)
        msg_count = len(session.messages)
        session.clear()
        self.session_manager.save(session)
        
        logger.info(f"Session reset for {session_key} (cleared {msg_count} messages)")
        await self.send(OutboundMessage(
            channel=self.name,
            chat_id=str(chat_id),
            content="🔄 Conversation history cleared. Let's start fresh!",
            metadata=metadata or {},
        ))
    
    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running
