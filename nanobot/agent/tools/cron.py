"""Cron tool for scheduling reminders and tasks."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""
    
    def __init__(self, cron_service: CronService):
        self._cron = cron_service
        self._channel = ""
        self._chat_id = ""
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id
    
    @property
    def name(self) -> str:
        return "cron"
    
    @property
    def description(self) -> str:
        return "Schedule reminders and recurring tasks. Actions: add, list, remove."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "Action to perform"
                },
                "message": {
                    "type": "string",
                    "description": "Reminder message (for add)"
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for recurring tasks)"
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)"
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove)"
                },
                "active_hours": {
                    "type": "array",
                    "description": "Active time-of-day windows in Beijing time. Each element is [start, end] in 'HH:MM' format. E.g. [['10:00','12:00'],['14:00','19:00']] means only run during 10-12 and 14-19. Job is skipped (not executed) outside these windows.",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "active_weekdays": {
                    "type": "array",
                    "description": "Active weekdays as ISO numbers (1=Monday, 7=Sunday). E.g. [1,2,3,4,5] for weekdays only. Job is skipped on other days.",
                    "items": {"type": "integer"}
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        message: str = "",
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        job_id: str | None = None,
        active_hours: list[list[str]] | None = None,
        active_weekdays: list[int] | None = None,
        **kwargs: Any
    ) -> str:
        if action == "add":
            return self._add_job(message, every_seconds, cron_expr, active_hours, active_weekdays)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"
    
    def _add_job(
        self,
        message: str,
        every_seconds: int | None,
        cron_expr: str | None,
        active_hours: list[list[str]] | None = None,
        active_weekdays: list[int] | None = None,
    ) -> str:
        if not message:
            return "Error: message is required for add"
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"
        
        # Build schedule
        if every_seconds:
            schedule = CronSchedule(
                kind="every", every_ms=every_seconds * 1000,
                active_hours=active_hours, active_weekdays=active_weekdays,
            )
        elif cron_expr:
            schedule = CronSchedule(
                kind="cron", expr=cron_expr,
                active_hours=active_hours, active_weekdays=active_weekdays,
            )
        else:
            return "Error: either every_seconds or cron_expr is required"
        
        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
        )
        
        window_info = ""
        if active_hours:
            ranges = ", ".join(f"{w[0]}-{w[1]}" for w in active_hours if len(w) == 2)
            window_info += f", active hours: {ranges}"
        if active_weekdays:
            day_names = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
            days = ", ".join(day_names.get(d, str(d)) for d in active_weekdays)
            window_info += f", active days: {days}"
        
        return f"Created job '{job.name}' (id: {job.id}{window_info})"
    
    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
    
    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
