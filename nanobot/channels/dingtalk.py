"""DingTalk/DingDing channel implementation using Stream Mode."""

import asyncio
import json
import time
from typing import Any

from loguru import logger
import httpx

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import DingTalkConfig

try:
    from dingtalk_stream import (
        DingTalkStreamClient,
        Credential,
        CallbackHandler,
        CallbackMessage,
        AckMessage,
    )
    from dingtalk_stream.chatbot import ChatbotMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    # Fallback so class definitions don't crash at module level
    CallbackHandler = object  # type: ignore[assignment,misc]
    CallbackMessage = None  # type: ignore[assignment,misc]
    AckMessage = None  # type: ignore[assignment,misc]
    ChatbotMessage = None  # type: ignore[assignment,misc]


class NanobotDingTalkHandler(CallbackHandler):
    """
    Standard DingTalk Stream SDK Callback Handler.
    Parses incoming messages and forwards them to the Nanobot channel.
    """

    def __init__(self, channel: "DingTalkChannel"):
        super().__init__()
        self.channel = channel

    async def process(self, message: CallbackMessage):
        """Process incoming stream message."""
        try:
            # Parse using SDK's ChatbotMessage for robust handling
            chatbot_msg = ChatbotMessage.from_dict(message.data)

            # Extract text content based on message type
            content = ""
            msg_type = chatbot_msg.message_type or message.data.get("msgtype", "")

            if msg_type == "richText":
                # Rich text messages store content in content.richText array
                # Each element may have "text" (string) or "type":"picture" (image)
                rich_text_items = (
                    message.data.get("content", {}).get("richText", [])
                )
                text_parts = [
                    item["text"]
                    for item in rich_text_items
                    if "text" in item
                ]
                content = "".join(text_parts).strip()
            else:
                # Standard text message
                if chatbot_msg.text:
                    content = chatbot_msg.text.content.strip()
                if not content:
                    content = message.data.get("text", {}).get("content", "").strip()

            if not content:
                logger.warning(
                    f"Received empty or unsupported message type: {msg_type}"
                )
                return AckMessage.STATUS_OK, "OK"

            sender_id = chatbot_msg.sender_staff_id or chatbot_msg.sender_id
            sender_name = chatbot_msg.sender_nick or "Unknown"

            # Determine if this is a group message (conversationType "2" = group)
            is_group = str(chatbot_msg.conversation_type) == "2"
            conversation_id = chatbot_msg.conversation_id or ""
            session_webhook = chatbot_msg.session_webhook or ""

            logger.info(
                f"Received DingTalk message from {sender_name} ({sender_id}): {content}"
                f" [{'group' if is_group else 'private'}, conv={conversation_id}]"
            )

            # Forward to Nanobot via _on_message (non-blocking).
            # Store reference to prevent GC before task completes.
            task = asyncio.create_task(
                self.channel._on_message(
                    content, sender_id, sender_name,
                    is_group=is_group,
                    conversation_id=conversation_id,
                    session_webhook=session_webhook,
                )
            )
            self.channel._background_tasks.add(task)
            task.add_done_callback(self.channel._background_tasks.discard)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.error(f"Error processing DingTalk message: {e}")
            # Return OK to avoid retry loop from DingTalk server
            return AckMessage.STATUS_OK, "Error"


class DingTalkChannel(BaseChannel):
    """
    DingTalk channel using Stream Mode.

    Uses WebSocket to receive events via `dingtalk-stream` SDK.
    Uses direct HTTP API to send messages (SDK is mainly for receiving).

    Note: Currently only supports private (1:1) chat. Group messages are
    received but replies are sent back as private messages to the sender.
    """

    name = "dingtalk"

    def __init__(self, config: DingTalkConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DingTalkConfig = config
        self._client: Any = None
        self._http: httpx.AsyncClient | None = None

        # Access Token management for sending messages
        self._access_token: str | None = None
        self._token_expiry: float = 0

        # Hold references to background tasks to prevent GC
        self._background_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the DingTalk bot with Stream Mode."""
        try:
            if not DINGTALK_AVAILABLE:
                logger.error(
                    "DingTalk Stream SDK not installed. Run: pip install dingtalk-stream"
                )
                return

            if not self.config.client_id or not self.config.client_secret:
                logger.error("DingTalk client_id and client_secret not configured")
                return

            self._running = True
            self._http = httpx.AsyncClient()

            logger.info(
                f"Initializing DingTalk Stream Client with Client ID: {self.config.client_id}..."
            )
            credential = Credential(self.config.client_id, self.config.client_secret)
            self._client = DingTalkStreamClient(credential)

            # Register standard handler
            handler = NanobotDingTalkHandler(self)
            self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

            logger.info("DingTalk bot started with Stream Mode")

            # client.start() is an async infinite loop handling the websocket connection
            await self._client.start()

        except Exception as e:
            logger.exception(f"Failed to start DingTalk channel: {e}")

    async def stop(self) -> None:
        """Stop the DingTalk bot."""
        self._running = False
        # Close the shared HTTP client
        if self._http:
            await self._http.aclose()
            self._http = None
        # Cancel outstanding background tasks
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()

    async def _get_access_token(self) -> str | None:
        """Get or refresh Access Token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        data = {
            "appKey": self.config.client_id,
            "appSecret": self.config.client_secret,
        }

        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot refresh token")
            return None

        try:
            resp = await self._http.post(url, json=data)
            resp.raise_for_status()
            res_data = resp.json()
            self._access_token = res_data.get("accessToken")
            # Expire 60s early to be safe
            self._token_expiry = time.time() + int(res_data.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as e:
            logger.error(f"Failed to get DingTalk access token: {e}")
            return None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through DingTalk (private or group)."""
        if not self._http:
            logger.warning("DingTalk HTTP client not initialized, cannot send")
            return

        metadata = msg.metadata or {}
        is_group = metadata.get("is_group", False)

        if is_group:
            await self._send_group_message(msg)
        else:
            await self._send_private_message(msg)

    async def _send_private_message(self, msg: OutboundMessage) -> None:
        """Send a private (1:1) message via oToMessages/batchSend API."""
        token = await self._get_access_token()
        if not token:
            return

        metadata = msg.metadata or {}
        msg_type = metadata.get("msg_type", "text")

        url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": token}

        if msg_type == "image":
            photo_url = metadata.get("photo_url", "")
            msg_key = "sampleImageMsg"
            msg_param = json.dumps({"photoURL": photo_url})
        else:
            msg_key = "sampleMarkdown"
            msg_param = json.dumps({"text": msg.content, "title": "Nanobot Reply"})

        data = {
            "robotCode": self.config.client_id,
            "userIds": [msg.chat_id],
            "msgKey": msg_key,
            "msgParam": msg_param,
        }

        try:
            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"DingTalk private send failed: {resp.text}")
            else:
                logger.debug(f"DingTalk private message sent to {msg.chat_id} (type={msg_type})")
        except Exception as e:
            logger.error(f"Error sending DingTalk private message: {e}")

    async def _send_group_message(self, msg: OutboundMessage) -> None:
        """Send a group message via groupMessages/send API."""
        token = await self._get_access_token()
        if not token:
            return

        metadata = msg.metadata or {}
        conversation_id = metadata.get("conversation_id", "")

        if not conversation_id:
            logger.warning("DingTalk group send: missing conversation_id, falling back to private")
            await self._send_private_message(msg)
            return

        msg_type = metadata.get("msg_type", "text")

        url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
        headers = {"x-acs-dingtalk-access-token": token}

        if msg_type == "image":
            photo_url = metadata.get("photo_url", "")
            msg_key = "sampleImageMsg"
            msg_param = json.dumps({"photoURL": photo_url})
        else:
            msg_key = "sampleMarkdown"
            msg_param = json.dumps({"text": msg.content, "title": "Nanobot Reply"})

        data = {
            "robotCode": self.config.client_id,
            "openConversationId": conversation_id,
            "msgKey": msg_key,
            "msgParam": msg_param,
        }

        try:
            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"DingTalk group send failed: {resp.text}")
            else:
                logger.debug(f"DingTalk group message sent to conversation {conversation_id} (type={msg_type})")
        except Exception as e:
            logger.error(f"Error sending DingTalk group message: {e}")

    async def _on_message(
        self,
        content: str,
        sender_id: str,
        sender_name: str,
        is_group: bool = False,
        conversation_id: str = "",
        session_webhook: str = "",
    ) -> None:
        """Handle incoming message (called by NanobotDingTalkHandler).

        Delegates to BaseChannel._handle_message() which enforces allow_from
        permission checks before publishing to the bus.

        For group messages, chat_id is set to the conversation_id so that
        session history is tracked per-group rather than per-user.
        """
        try:
            # Use conversation_id as chat_id for group messages (per-group session),
            # sender_id for private messages (per-user session).
            chat_id = conversation_id if is_group else sender_id

            logger.info(
                f"DingTalk inbound: {content} from {sender_name}"
                f" [{'group' if is_group else 'private'}]"
            )
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=str(content),
                metadata={
                    "sender_name": sender_name,
                    "platform": "dingtalk",
                    "is_group": is_group,
                    "conversation_id": conversation_id,
                    "session_webhook": session_webhook,
                },
            )
        except Exception as e:
            logger.error(f"Error publishing DingTalk message: {e}")
