# Heartbeat Tasks

This file is checked every 30 minutes by your nanobot agent.
Add tasks below that you want the agent to work on periodically.

If this file has no tasks (only headers and comments), the agent will skip the heartbeat.

## Active Tasks

- Check current Beijing time. If it is between 10:00 and 19:00 on a weekday, read memory/MEMORY.md to see if the user has any pending tasks. If yes, send a brief CBT-style micro-step nudge via the message tool (follow the cbt-coach skill rules — one step only, no lectures). If no pending tasks, send a casual check-in asking what they're working on. If it is outside 10:00-19:00 or on a weekend, do nothing and reply HEARTBEAT_OK.

## Completed

<!-- Move completed tasks here or delete them -->
