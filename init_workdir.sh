#!/usr/bin/env bash
# init_workdir.sh — Initialize a nanobot work directory
#
# Usage:
#   ./init_workdir.sh [path]
#
# If [path] is not provided, the script will prompt for one.
# The default is a "workdir" folder inside the nanobot project directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Determine target directory ────────────────────────────────────────────────

if [[ $# -ge 1 ]]; then
    WORK_DIR="$1"
else
    DEFAULT_DIR="$SCRIPT_DIR/workdir"
    echo ""
    echo "Where would you like to create your work directory?"
    echo "Press Enter to use the default: $DEFAULT_DIR"
    echo ""
    read -r -p "Path (or Enter for default): " USER_INPUT
    if [[ -z "$USER_INPUT" ]]; then
        WORK_DIR="$DEFAULT_DIR"
    else
        # Expand ~ manually since read doesn't expand it
        WORK_DIR="${USER_INPUT/#\~/$HOME}"
    fi
fi

# Resolve to absolute path
WORK_DIR="$(python3 -c "import os; print(os.path.abspath(os.path.expanduser('$WORK_DIR')))")"

# ── Create directory structure ────────────────────────────────────────────────

echo ""
echo "Creating work directory at: $WORK_DIR"
echo ""

mkdir -p "$WORK_DIR/00_inbox"
mkdir -p "$WORK_DIR/10_projects"
mkdir -p "$WORK_DIR/20_knowledge/tech"
mkdir -p "$WORK_DIR/90_journal"
mkdir -p "$WORK_DIR/99_archive"

# ── Seed essential files ──────────────────────────────────────────────────────

# 00_inbox/daily_dump.md — daily capture inbox (appended to by daily-dump skill)
if [[ ! -f "$WORK_DIR/00_inbox/daily_dump.md" ]]; then
    cat > "$WORK_DIR/00_inbox/daily_dump.md" << 'EOF'
# Daily Dump

This file is your capture inbox. The daily-dump skill automatically appends
project notes, ideas, and progress here during conversations.

The iflow-organizer skill processes this file at end-of-day and archives
the content into the appropriate project or knowledge folders.

---
EOF
    echo "  ✓ Created 00_inbox/daily_dump.md"
fi

# 00_inbox/TODO_INDEX.md — global todo list (managed by todo-coach skill)
if [[ ! -f "$WORK_DIR/00_inbox/TODO_INDEX.md" ]]; then
    cat > "$WORK_DIR/00_inbox/TODO_INDEX.md" << 'EOF'
# 待办池

## 🎯 今日聚焦 (Today)


## 🚨 明确期限 (DDL)


## ☕ 弹性蓄水池 (随时做)


## ✅ 归档 (Done)

EOF
    echo "  ✓ Created 00_inbox/TODO_INDEX.md"
fi

# 10_projects/README.md — guide for the projects folder
if [[ ! -f "$WORK_DIR/10_projects/README.md" ]]; then
    cat > "$WORK_DIR/10_projects/README.md" << 'EOF'
# Projects

Each project lives in its own subdirectory here.

## Structure

Create a folder per project as you go — no need to set them all up in advance.
The agent will help you create and organize project folders during conversations.

## Suggested layout per project

```
10_projects/
└── my-project/
    ├── work_log.md     # Running log of progress, decisions, and notes
    └── ...             # Any other files relevant to the project
```

The iflow-organizer skill will automatically route daily notes to the
correct project's work_log.md based on context.
EOF
    echo "  ✓ Created 10_projects/README.md"
fi

# 20_knowledge/tech/work_log.md — general tech notes
if [[ ! -f "$WORK_DIR/20_knowledge/tech/work_log.md" ]]; then
    cat > "$WORK_DIR/20_knowledge/tech/work_log.md" << 'EOF'
# Tech Knowledge Log

General technical notes, learnings, and reference material.

---
EOF
    echo "  ✓ Created 20_knowledge/tech/work_log.md"
fi

# ── Update config.json ────────────────────────────────────────────────────────

CONFIG_FILE="$SCRIPT_DIR/config.json"

if [[ -f "$CONFIG_FILE" ]]; then
    echo ""
    echo "Found config.json. Updating tools.workDir..."
    python3 - "$CONFIG_FILE" "$WORK_DIR" << 'PYEOF'
import json, sys

config_path = sys.argv[1]
work_dir = sys.argv[2]

with open(config_path) as f:
    config = json.load(f)

config.setdefault("tools", {})["workDir"] = work_dir

with open(config_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print(f"  ✓ Set tools.workDir = {work_dir}")
PYEOF
else
    echo ""
    echo "  ℹ  No config.json found. Remember to set tools.workDir manually:"
    echo "     \"workDir\": \"$WORK_DIR\""
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "✅ Work directory initialized at:"
echo "   $WORK_DIR"
echo ""
echo "Directory structure:"
echo "   00_inbox/       — daily capture inbox & global todo list"
echo "   10_projects/    — one subfolder per project (create as needed)"
echo "   20_knowledge/   — reusable knowledge & tech notes"
echo "   90_journal/     — personal journal entries"
echo "   99_archive/     — long-term archive"
echo ""
