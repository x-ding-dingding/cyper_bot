"""Background conversation summarizer for context window management."""

import asyncio
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider

SUMMARY_SYSTEM_PROMPT = """The following messages are being evicted from the conversation window.
Write a concise summary that captures what happened in these messages.

This summary will be provided as background context for future conversations. Include:

1. **What happened**: The conversations, tasks, and exchanges that took place.
2. **Important details**: Specific names, data, or facts that were discussed.
3. **Ongoing context**: Any unfinished tasks, pending questions, or commitments made.

If there is a previous summary provided, incorporate it to maintain continuity
and avoid losing track of long-term context.

Keep your summary under 200 words. Only output the summary."""


class Summarizer:
    """
    Background summarization service.

    When the conversation context approaches the token limit, this service
    generates a summary of older messages asynchronously (fire-and-forget)
    so the main agent loop is never blocked.
    """

    def __init__(self, provider: LLMProvider, model: str):
        self.provider = provider
        self.model = model

    def fire_and_forget(
        self,
        session: "Session",
        session_manager: "SessionManager",
        messages_snapshot: list[dict[str, Any]],
        previous_summary: str,
        min_keep: int,
    ) -> None:
        """Launch a background task to summarize evicted messages.

        Args:
            session: The live Session object (will be mutated on completion).
            session_manager: Used to persist the session after summarization.
            messages_snapshot: A *copy* of session.messages at trigger time.
            previous_summary: The existing summary to incorporate.
            min_keep: Number of recent messages to retain after summarization.
        """
        task = asyncio.create_task(
            self._do_summarize(
                session, session_manager, messages_snapshot, previous_summary, min_keep
            )
        )
        task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Log any unhandled exception from the background task."""
        if task.cancelled():
            return
        exception = task.exception()
        if exception:
            logger.warning(f"Background summarization failed: {exception}")

    async def _do_summarize(
        self,
        session: "Session",
        session_manager: "SessionManager",
        messages_snapshot: list[dict[str, Any]],
        previous_summary: str,
        min_keep: int,
    ) -> None:
        """Generate a summary and update the session."""
        try:
            logger.info(
                f"[Summarizer] Starting summarization for {session.key}: "
                f"{len(messages_snapshot)} messages → keeping {min_keep} recent"
            )
            
            transcript = self._format_transcript(messages_snapshot, previous_summary)

            llm_messages: list[dict[str, Any]] = [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ]

            logger.info(f"[Summarizer] Calling LLM for summary (model: {self.model})...")
            response = await self.provider.chat(
                messages=llm_messages,
                tools=None,
                model=self.model,
                max_tokens=1024,
                temperature=0.3,
            )

            summary_text = (response.content or "").strip()
            if not summary_text or response.finish_reason == "error":
                logger.warning("Summarizer returned empty or error response, skipping update")
                return

            # Update session atomically (single-threaded asyncio, safe at await boundaries)
            messages_before = len(session.messages)
            session.summary = summary_text
            session.messages = session.messages[-min_keep:]
            messages_after = len(session.messages)
            session.summary_in_progress = False
            session_manager.save(session)

            preview = summary_text[:120] + "..." if len(summary_text) > 120 else summary_text
            logger.info(
                f"[Summarizer] ✓ Summary completed for {session.key}\n"
                f"  Messages: {messages_before} → {messages_after} (trimmed {messages_before - messages_after})\n"
                f"  Summary preview: {preview}"
            )

        except Exception as exc:
            logger.warning(f"Summarization error for {session.key}: {exc}")
        finally:
            session.summary_in_progress = False

    @staticmethod
    def _format_transcript(
        messages: list[dict[str, Any]], previous_summary: str
    ) -> str:
        """Format messages into a plain-text transcript for the summarizer LLM."""
        parts: list[str] = []

        if previous_summary:
            parts.append("--- Previous Summary ---")
            parts.append(previous_summary)
            parts.append("--- End Previous Summary ---\n")

        parts.append("--- Conversation Transcript ---")
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Multi-modal content: extract text parts only
                text_parts = [
                    item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
                ]
                content = " ".join(text_parts)
            parts.append(f"{role}: {content}")
        parts.append("--- End Transcript ---")

        return "\n".join(parts)
