<div align="center">
  <img src="nanobot_logo.png" alt="nanobot" width="400">
  <h1>Spark-nanobot — Personal AI Assistant</h1>
  <p><em>Built on <a href="">nanobot</a> · Ultra-lightweight · Skill-driven · Safe by default</em></p>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/based_on-nanobot-orange" alt="nanobot">
  </p>
</div>

<p align="center">
  <b>English</b> | <a href="#chinese-readme">中文文档</a>
</p>

---

Spark-nanobot is a personal AI assistant built on top of [nanobot]. It inherits nanobot's ultra-lightweight core (~4,000 lines) and extends it with a structured **work directory system**, **productivity-focused skills**, and **safe-by-default sandboxing**.

## Table of Contents

- [Install](#-install)
- [Quick Start](#-quick-start)
- [Skills](#-skills)
- [Work Directory](#-work-directory)
- [Security & Sandboxing](#-security--sandboxing)
- [Chat Channels](#-chat-channels)
- [Configuration](#️-configuration)
- [CLI Reference](#-cli-reference)

---

## 📦 Install

### One-step setup (recommended)

```bash
git clone <this-repo>
cd spark-nanobot
bash install.sh
```

`install.sh` will:
1. Check Python ≥ 3.11
2. Install nanobot
3. Copy `config.example.json` → `config.json`
4. Copy `workspace/*.md.example` → `workspace/*.md`
5. Optionally initialize a [work directory](#-work-directory)

Then open `config.json` and fill in your API key — done.

### Manual install

```bash
pip install -e .
cp config.example.json config.json   # then edit to add your API key
```

---

## 🚀 Quick Start

**1. Run setup**

```bash
bash install.sh
```

**2. Add your API key** (`config.json`)

```json
{
  "providers": {
    "dashscope": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "dashscope/qwen3.5-plus",
    }
  }
}
```

**3. Chat**

```bash
nanobot agent -m "Hello!"
nanobot agent          # interactive mode
nanobot gateway        # start all chat channels
```

---

## 🎯 Skills

Skills are modular knowledge packages that extend the agent's capabilities. They live in `workspace/skills/` and are automatically loaded into the system prompt.

### Built-in Skills

| Skill | What it does |
|-------|-------------|
| `github` | Interact with GitHub via `gh` CLI — check PRs, CI runs, issues |
| `weather` | Fetch current weather for any location |
| `cron` | Create and manage scheduled reminders and recurring tasks |
| `tmux` | Manage terminal sessions — run long tasks in the background |
| `summarize` | Summarize URLs, YouTube videos, PDFs, and local files |
| `skill-creator` | Guide for creating new skills |

### Productivity Skills (workspace/skills/)

| Skill | What it does |
|-------|-------------|
| `daily-dump` | **Always active.** Silently captures project notes, ideas, and progress into `{WORK_DIR}/00_inbox/daily_dump.md` during every conversation |
| `iflow-organizer` | End-of-day organizer — merges the daily dump and routes content into project logs, knowledge base, and archive |
| `todo-coach` | CBT-trained task coach — manages a global todo list, runs morning standups, keeps you focused without guilt |
| `cbt-coach` | Cognitive behavioral therapy coach — helps break through procrastination with micro-steps and gentle nudges |

### How Skills Work

Skills use a **progressive disclosure** model to stay token-efficient:

1. **Metadata** (name + description) — always in context, ~100 words each
2. **SKILL.md body** — loaded when the skill is triggered
3. **Bundled scripts/references** — loaded on demand by the agent

To add your own skill, create a folder in `workspace/skills/your-skill/` with a `SKILL.md` file.

---

## 📁 Work Directory

The work directory is a **personal knowledge base** separate from the nanobot project itself. It's where the agent stores your project notes, daily logs, and organized knowledge.

### Setup

```bash
# Prompted automatically during install.sh
# Or run standalone at any time:
bash init_workdir.sh ~/my-workdir

# The path is saved to config.json automatically:
# "tools": { "workDir": "/path/to/my-workdir" }
```

If no path is specified, the default is `<project_root>/workdir`.

### Directory Structure

```
workdir/                        ← configured via tools.workDir in config.json
├── 00_inbox/
│   ├── daily_dump.md           # daily capture inbox — appended automatically during conversations
│   └── TODO_INDEX.md           # global todo list managed by todo-coach skill
├── 10_projects/                # one subfolder per project (create as you go)
│   └── my-project/
│       └── work_log.md         # running log of progress, decisions, and notes
├── 20_knowledge/               # reusable knowledge and reference material
│   └── tech/
│       └── work_log.md         # general tech notes and learnings
├── 90_journal/                 # personal journal entries
└── 99_archive/                 # long-term archive
```

**Key points:**
- `10_projects/` subdirectories are **not pre-created** — the agent creates them during conversation as you discuss projects
- `00_inbox/daily_dump.md` is the single capture point; `iflow-organizer` routes content from here at end of day
- The work directory is **completely separate** from `workspace/` (which holds agent config and skills)

Skills reference it via `{WORK_DIR}`, which is injected into the system prompt automatically.

---

## 🔒 Security & Sandboxing

nanobot gives the agent real tools — file access, shell execution, web browsing. Here's how it prevents the agent from touching things it shouldn't.

### Layer 1 — Workspace Restriction (`restrictToWorkspace`)

The most important safety control. When enabled, **all tools** (file read/write/edit/list and shell exec) are restricted to an allowlist of directories. The agent physically cannot access anything outside these paths.

```json
{
  "tools": {
    "restrictToWorkspace": true,
    "allowedPaths": ["~/projects/my-app"]
  }
}
```

**Automatically included in the allowlist:**
- The nanobot project directory (always)
- `tools.workDir` (your work directory, if configured)
- Any paths listed in `tools.allowedPaths`

**Blocked:** everything else — `~/Documents`, `~/Desktop`, other projects, system files.

> [!TIP]
> Set `"restrictToWorkspace": true` for any production or shared deployment. It's `false` by default to make local development easier.

### Layer 2 — Protected Files

Even within the nanobot project, certain core files can never be written, edited, or deleted by the agent. This prevents the agent from modifying its own safety controls.

Default protected files:

```
nanobot/agent/tools/filesystem.py
nanobot/agent/tools/shell.py
nanobot/agent/tools/base.py
nanobot/agent/tools/registry.py
nanobot/agent/loop.py
nanobot/config/schema.py
nanobot/config/loader.py
nanobot/agent/subagent.py
```

Extend the list in `config.json` under `tools.protectedFiles`.

### Layer 3 — Dangerous Command Blocking

The shell tool blocks these patterns regardless of other settings:

| Blocked | Reason |
|---------|--------|
| `rm -rf` / `rm -r` | Recursive deletion |
| `format` / `mkfs` / `diskpart` | Disk formatting |
| `dd if=` | Raw disk write |
| `shutdown` / `reboot` / `poweroff` | System power control |
| `> /dev/sd*` | Write to block device |
| Fork bomb pattern | `: () { : \| : & }; :` |

Path traversal (`../`) is also blocked when `restrictToWorkspace` is enabled.

### Layer 4 — Channel Access Control

Each chat channel has an `allowFrom` list. Set it to restrict who can talk to your bot:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "...",
      "allowFrom": ["123456789"]
    }
  }
}
```

Empty `allowFrom` = allow everyone. Non-empty = only listed user IDs can interact.

### Layer 5 — Subagent Isolation

Background subagents have no `message` tool and no `spawn` tool — they can't send unsolicited messages or spawn recursively.

### Summary

| Threat | Defense |
|--------|---------|
| Agent reads/writes files outside project | `restrictToWorkspace: true` |
| Agent modifies its own safety code | `protectedFiles` list |
| Agent runs destructive shell commands | Hardcoded deny patterns |
| Unauthorized users access the bot | `allowFrom` per channel |
| Subagents spam users or spawn infinitely | Tool isolation on subagents |

---

## 💬 Chat Channels

Connect to your assistant through any of these channels:

| Channel | Setup difficulty |
|---------|-----------------|
| **Telegram** | Easy — just a bot token |
| **Discord** | Easy — bot token + intents |
| **Feishu (飞书)** | Medium — app credentials, WebSocket mode |
| **DingTalk (钉钉)** | Medium — app credentials, Stream mode |
| **Slack** | Medium — bot + app tokens, Socket mode |
| **WhatsApp** | Medium — scan QR (requires Node.js ≥18) |
| **Email** | Medium — IMAP/SMTP credentials |
| **QQ** | Easy — app credentials |

All channels use WebSocket or polling — **no public IP required**.

<details>
<summary><b>Telegram (Recommended)</b></summary>

**1. Create a bot**
- Search `@BotFather` on Telegram → `/newbot` → copy the token

**2. Configure**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Feishu (飞书)</b></summary>

**1. Create app** at [Feishu Open Platform](https://open.feishu.cn/app)
- Enable **Bot** capability
- Add permission: `im:message`
- Add event: `im.message.receive_v1` (Long Connection mode)
- Get **App ID** and **App Secret** → Publish

**2. Configure**

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "allowFrom": []
    }
  }
}
```

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>DingTalk (钉钉)</b></summary>

**1. Create app** at [DingTalk Open Platform](https://open-dev.dingtalk.com/)
- Add **Robot** capability → enable **Stream Mode**
- Get **AppKey** (Client ID) and **AppSecret** → Publish

**2. Configure**

```json
{
  "channels": {
    "dingtalk": {
      "enabled": true,
      "clientId": "YOUR_APP_KEY",
      "clientSecret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  }
}
```

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Discord</b></summary>

**1. Create bot** at [Discord Developer Portal](https://discord.com/developers/applications)
- Bot → Add Bot → copy token
- Enable **MESSAGE CONTENT INTENT**

**2. Configure**

```json
{
  "channels": {
    "discord": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

**3. Invite bot** via OAuth2 → URL Generator (scopes: `bot`, permissions: `Send Messages`, `Read Message History`)

**4. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Slack</b></summary>

**1. Create app** at [Slack API](https://api.slack.com/apps)
- Socket Mode: ON → generate App-Level Token (`xapp-...`)
- OAuth scopes: `chat:write`, `app_mentions:read`
- Events: `message.im`, `app_mention`
- Install to workspace → copy Bot Token (`xoxb-...`)

**2. Configure**

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "botToken": "xoxb-...",
      "appToken": "xapp-...",
      "groupPolicy": "mention"
    }
  }
}
```

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Email</b></summary>

**1. Get credentials** — create a dedicated Gmail account, enable 2FA, create an [App Password](https://myaccount.google.com/apppasswords)

**2. Configure**

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "consentGranted": true,
      "imapHost": "imap.gmail.com",
      "imapPort": 993,
      "imapUsername": "your-bot@gmail.com",
      "imapPassword": "your-app-password",
      "smtpHost": "smtp.gmail.com",
      "smtpPort": 587,
      "smtpUsername": "your-bot@gmail.com",
      "smtpPassword": "your-app-password",
      "fromAddress": "your-bot@gmail.com",
      "allowFrom": ["your-real-email@gmail.com"]
    }
  }
}
```

**3. Run**

```bash
nanobot gateway
```

</details>

---

## ⚙️ Configuration

Config file: `config.json` (project root). Copy from `config.example.json` to get started.

### LLM Providers

At least one provider API key is required. [OpenRouter](https://openrouter.ai) is recommended — it gives access to all major models with a single key.

| Provider | Models | Get Key |
|----------|--------|---------|
| `openrouter` | All models (recommended) | [openrouter.ai](https://openrouter.ai) |
| `anthropic` | Claude | [console.anthropic.com](https://console.anthropic.com) |
| `openai` | GPT | [platform.openai.com](https://platform.openai.com) |
| `deepseek` | DeepSeek | [platform.deepseek.com](https://platform.deepseek.com) |
| `groq` | Llama + Whisper transcription | [console.groq.com](https://console.groq.com) |
| `gemini` | Gemini | [aistudio.google.com](https://aistudio.google.com) |
| `dashscope` | Qwen | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com) |
| `moonshot` | Kimi | [platform.moonshot.cn](https://platform.moonshot.cn) |

### Work Directory

```json
{
  "tools": {
    "workDir": "~/my-workdir"
  }
}
```

Set this to the path initialized by `bash init_workdir.sh`. Skills like `daily-dump` and `todo-coach` use it automatically via `{WORK_DIR}`.

### Security Options

```json
{
  "tools": {
    "restrictToWorkspace": true,
    "allowedPaths": ["~/projects/my-app"],
    "protectedFiles": [
      "nanobot/agent/tools/filesystem.py",
      "nanobot/agent/tools/shell.py"
    ]
  }
}
```

### Agent Defaults

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "maxTokens": 8192,
      "temperature": 0.7,
      "contextWindow": 32768,
      "summarizeThreshold": 0.6
    }
  }
}
```

`summarizeThreshold`: when prompt tokens reach this fraction of `contextWindow`, older messages are summarized and trimmed automatically (non-blocking).

---

## 🖥️ CLI Reference

| Command | Description |
|---------|-------------|
| `nanobot agent -m "..."` | Single message |
| `nanobot agent` | Interactive chat mode |
| `nanobot agent --logs` | Show runtime logs |
| `nanobot gateway` | Start all enabled channels |
| `nanobot status` | Show provider and channel status |
| `nanobot cron list` | List scheduled tasks |
| `nanobot cron add ...` | Add a scheduled task |
| `nanobot cron remove <id>` | Remove a scheduled task |

Interactive mode exits: `exit`, `quit`, `/exit`, `/quit`, `:q`, or `Ctrl+D`.

---

## 📁 Project Structure

```
nanobot/                    # core engine (inherited from nanobot)
├── agent/                  # 🧠 agent loop, context builder, memory, tools
├── channels/               # 📱 Telegram, Discord, Feishu, DingTalk, Slack...
├── providers/              # 🤖 LLM provider abstraction (litellm)
├── session/                # 💬 conversation persistence
├── cron/                   # ⏰ scheduled tasks
├── heartbeat/              # 💓 proactive wake-up
└── config/                 # ⚙️ schema + loader

workspace/                  # your personal config (gitignored)
├── SOUL.md                 # assistant personality
├── USER.md                 # your profile
├── AGENTS.md               # behavioral guidelines
├── HEARTBEAT.md            # periodic background tasks
└── skills/                 # productivity skills
    ├── daily-dump/
    ├── iflow-organizer/
    ├── todo-coach/
    └── cbt-coach/

workdir/                    # your work directory (configured separately)
├── 00_inbox/
├── 10_projects/
├── 20_knowledge/
├── 90_journal/
└── 99_archive/

config.json                 # your config (gitignored, copy from config.example.json)
config.example.json         # template — safe to commit
install.sh                  # one-step setup
init_workdir.sh             # initialize work directory
```

---

<p align="center">
  <sub>Spark-nanobot is built on <a href="https://github.com/x-ding-dingding/cyper_bot">nanobot</a> — for personal use, research, and technical exploration.</sub>
</p>

---

## <a id="chinese-readme"></a>Spark-nanobot — 个人 AI 助手

<div align="center">
  <p><em>基于 <a href="https://github.com/x-ding-dingding/cyper_bot">nanobot</a> · 超轻量 · 技能驱动 · 默认安全</em></p>
</div>

Spark-nanobot 是一个基于 [nanobot](https://github.com/x-ding-dingding/cyper_bot) 构建的个人 AI 助手。它继承了 nanobot 超轻量的核心代码（约 4,000 行），并在此基础上扩展了**结构化工作目录系统**、**生产力技能包**和**默认安全沙箱**。

## 目录

- [安装](#-安装)
- [快速开始](#-快速开始)
- [技能 Skills](#-技能-skills)
- [工作目录](#-工作目录)
- [安全沙箱](#-安全沙箱)
- [聊天渠道](#-聊天渠道)
- [配置参考](#️-配置参考)
- [命令行参考](#️-命令行参考)

---

## 📦 安装

### 一键安装（推荐）

```bash
git clone <this-repo>
cd spark-nanobot
bash install.sh
```

`install.sh` 会自动完成：
1. 检查 Python ≥ 3.11
2. 安装 nanobot
3. 复制 `config.example.json` → `config.json`
4. 复制 `workspace/*.md.example` → `workspace/*.md`
5. 可选：初始化[工作目录](#-工作目录)

完成后打开 `config.json`，填入你的 API Key 即可。

### 手动安装

```bash
pip install -e .
cp config.example.json config.json   # 然后编辑填入 API Key
```

---

## 🚀 快速开始

**1. 运行安装脚本**

```bash
bash install.sh
```

**2. 填入 API Key**（`config.json`）

以通义千问为例：

```json
{
  "providers": {
    "dashscope": {
      "apiKey": "sk-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "dashscope/qwen-plus"
    }
  }
}
```

**3. 开始对话**

```bash
nanobot agent -m "你好！"
nanobot agent          # 交互模式
nanobot gateway        # 启动所有聊天渠道
```

---

## 🎯 技能 Skills

技能是模块化的知识包，用于扩展 Agent 的能力。技能文件存放在 `workspace/skills/` 目录下，启动时自动加载到 system prompt。

### 内置技能

| 技能 | 功能 |
|------|------|
| `github` | 通过 `gh` CLI 操作 GitHub — 查看 PR、CI 运行状态、Issues |
| `weather` | 查询任意地点的实时天气 |
| `cron` | 创建和管理定时提醒与周期任务 |
| `tmux` | 管理终端会话，在后台运行长时间任务 |
| `summarize` | 总结 URL、YouTube 视频、PDF 和本地文件 |
| `skill-creator` | 创建新技能的引导工具 |

### 生产力技能（workspace/skills/）

| 技能 | 功能 |
|------|------|
| `daily-dump` | **始终激活。** 在每次对话中静默地将项目笔记、想法和进展追加到 `{WORK_DIR}/00_inbox/daily_dump.md` |
| `iflow-organizer` | 每日收工整理器 — 合并 daily dump，将内容归档到对应项目日志、知识库和存档目录 |
| `todo-coach` | 受 CBT 训练的任务教练 — 管理全局待办列表，主持晨会发牌，帮你专注而不产生内疚感 |
| `cbt-coach` | 认知行为疗法教练 — 通过微步骤和温和的推动帮你突破拖延 |

### 技能加载机制

技能采用**渐进式披露**模型，节省 token：

1. **元数据**（名称 + 描述）— 始终在上下文中，每个约 100 词
2. **SKILL.md 正文** — 技能被触发后才加载
3. **附带脚本/参考文件** — 由 Agent 按需加载

要添加自己的技能，在 `workspace/skills/your-skill/` 下创建包含 `SKILL.md` 的文件夹即可。

---

## 📁 工作目录

工作目录是独立于 nanobot 项目之外的**个人知识库**，用于存储项目笔记、每日日志和整理后的知识。

### 初始化

```bash
# install.sh 安装时会自动提示初始化
# 也可以随时单独运行：
bash init_workdir.sh ~/my-workdir

# 路径会自动写入 config.json：
# "tools": { "workDir": "/path/to/my-workdir" }
```

不指定路径时，默认在项目根目录下创建 `workdir/`。

### 目录结构

```
workdir/                        ← 通过 config.json 的 tools.workDir 配置
├── 00_inbox/
│   ├── daily_dump.md           # 每日碎片收集箱 — 对话中自动追加
│   └── TODO_INDEX.md           # 全局待办列表，由 todo-coach 管理
├── 10_projects/                # 项目目录（按需创建子文件夹）
│   └── my-project/
│       └── work_log.md         # 项目进展、决策和笔记的流水日志
├── 20_knowledge/               # 可复用的知识和参考资料
│   └── tech/
│       └── work_log.md         # 通用技术笔记
├── 90_journal/                 # 个人日记
└── 99_archive/                 # 长期归档
```

**设计要点：**
- `10_projects/` 的子目录**不预先创建** — 在对话中讨论项目时由 Agent 按需创建
- `00_inbox/daily_dump.md` 是唯一的捕获入口；`iflow-organizer` 在每日收工时将内容路由到对应位置
- 工作目录与 `workspace/`（存放 Agent 配置和技能）**完全分离**

技能通过 `{WORK_DIR}` 引用工作目录，该变量会自动注入到 system prompt 中。

---

## 🔒 安全沙箱

nanobot 赋予 Agent 真实的工具能力 — 文件访问、Shell 执行、网页浏览。以下是防止 Agent 操作不该碰的内容的五层机制。

### 第一层 — 工作区限制（`restrictToWorkspace`）

最重要的安全控制。开启后，**所有工具**（文件读写/编辑/列目录和 Shell 执行）都被限制在一个路径白名单内。Agent 在物理上无法访问白名单之外的任何路径。

```json
{
  "tools": {
    "restrictToWorkspace": true,
    "allowedPaths": ["~/projects/my-app"]
  }
}
```

**自动加入白名单的路径：**
- nanobot 项目目录（始终包含）
- `tools.workDir`（工作目录，如已配置）
- `tools.allowedPaths` 中列出的路径

**被拦截的路径：** 其他所有内容 — `~/Documents`、`~/Desktop`、其他项目、系统文件。

> [!TIP]
> 生产环境或共享部署时，建议设置 `"restrictToWorkspace": true`。默认为 `false` 是为了方便本地开发。

### 第二层 — 受保护文件

即使在 nanobot 项目目录内，某些核心文件也永远不能被 Agent 写入、编辑或删除（读取仍然允许）。这防止 Agent 修改自身的安全控制代码。

默认受保护文件：

```
nanobot/agent/tools/filesystem.py
nanobot/agent/tools/shell.py
nanobot/agent/tools/base.py
nanobot/agent/tools/registry.py
nanobot/agent/loop.py
nanobot/config/schema.py
nanobot/config/loader.py
nanobot/agent/subagent.py
```

可在 `config.json` 的 `tools.protectedFiles` 中扩展此列表。

### 第三层 — 危险命令拦截

Shell 工具会无条件拦截以下命令模式：

| 被拦截的命令 | 原因 |
|------------|------|
| `rm -rf` / `rm -r` | 递归删除 |
| `format` / `mkfs` / `diskpart` | 磁盘格式化 |
| `dd if=` | 原始磁盘写入 |
| `shutdown` / `reboot` / `poweroff` | 系统电源控制 |
| `> /dev/sd*` | 写入块设备 |
| Fork bomb 模式 | `: () { : \| : & }; :` |

开启 `restrictToWorkspace` 时，路径穿越（`../`）也会被拦截。

### 第四层 — 渠道访问控制

每个聊天渠道都有 `allowFrom` 白名单，用于限制谁可以和你的 Bot 对话：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "...",
      "allowFrom": ["123456789"]
    }
  }
}
```

`allowFrom` 为空 = 允许所有人。非空 = 只有列出的用户 ID 才能交互。

### 第五层 — 子代理隔离

后台子代理没有 `message` 工具和 `spawn` 工具 — 它们无法主动给用户发消息，也无法递归 spawn 新的子代理。

### 安全机制总览

| 威胁 | 防御措施 |
|------|---------|
| Agent 读写项目外的文件 | `restrictToWorkspace: true` |
| Agent 修改自身安全代码 | `protectedFiles` 列表 |
| Agent 执行破坏性 Shell 命令 | 硬编码拦截规则 |
| 未授权用户访问 Bot | 每个渠道的 `allowFrom` |
| 子代理无限 spawn 或骚扰用户 | 子代理工具隔离 |

---

## 💬 聊天渠道

通过以下任意渠道连接你的助手：

| 渠道 | 接入难度 |
|------|---------|
| **Telegram** | 简单 — 只需 Bot Token |
| **飞书** | 中等 — 应用凭证，WebSocket 模式 |
| **钉钉** | 中等 — 应用凭证，Stream 模式 |
| **Discord** | 简单 — Bot Token + Intents |
| **Slack** | 中等 — Bot Token + App Token，Socket 模式 |
| **WhatsApp** | 中等 — 扫码绑定（需要 Node.js ≥18） |
| **Email** | 中等 — IMAP/SMTP 凭证 |
| **QQ** | 简单 — 应用凭证 |

所有渠道均使用 WebSocket 或轮询 — **无需公网 IP**。

<details>
<summary><b>飞书（推荐国内用户）</b></summary>

**1. 创建应用**，访问[飞书开放平台](https://open.feishu.cn/app)
- 启用**机器人**能力
- 添加权限：`im:message`
- 添加事件：`im.message.receive_v1`（选择长连接模式）
- 获取 **App ID** 和 **App Secret** → 发布应用

**2. 配置**

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "allowFrom": []
    }
  }
}
```

**3. 启动**

```bash
nanobot gateway
```

> 飞书使用 WebSocket 长连接接收消息，无需 Webhook 和公网 IP！

</details>

<details>
<summary><b>钉钉</b></summary>

**1. 创建应用**，访问[钉钉开放平台](https://open-dev.dingtalk.com/)
- 添加**机器人**能力 → 开启 **Stream 模式**
- 获取 **AppKey**（Client ID）和 **AppSecret** → 发布

**2. 配置**

```json
{
  "channels": {
    "dingtalk": {
      "enabled": true,
      "clientId": "YOUR_APP_KEY",
      "clientSecret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  }
}
```

**3. 启动**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>Telegram</b></summary>

**1. 创建 Bot**
- 在 Telegram 搜索 `@BotFather` → `/newbot` → 复制 Token

**2. 配置**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

**3. 启动**

```bash
nanobot gateway
```

</details>

---

## ⚙️ 配置参考

配置文件：项目根目录下的 `config.json`。从 `config.example.json` 复制后编辑。

### LLM 提供商

至少需要配置一个提供商的 API Key。

| 提供商 | 模型 | 获取 Key |
|--------|------|---------|
| `openrouter` | 所有主流模型（推荐） | [openrouter.ai](https://openrouter.ai) |
| `dashscope` | 通义千问 | [dashscope.console.aliyun.com](https://dashscope.console.aliyun.com) |
| `anthropic` | Claude | [console.anthropic.com](https://console.anthropic.com) |
| `deepseek` | DeepSeek | [platform.deepseek.com](https://platform.deepseek.com) |
| `moonshot` | Kimi | [platform.moonshot.cn](https://platform.moonshot.cn) |
| `openai` | GPT | [platform.openai.com](https://platform.openai.com) |
| `gemini` | Gemini | [aistudio.google.com](https://aistudio.google.com) |
| `groq` | Llama + Whisper 语音转文字 | [console.groq.com](https://console.groq.com) |

### 工作目录

```json
{
  "tools": {
    "workDir": "~/my-workdir"
  }
}
```

设置为 `bash init_workdir.sh` 初始化的路径。`daily-dump`、`todo-coach` 等技能会通过 `{WORK_DIR}` 自动使用该路径。

### 安全配置

```json
{
  "tools": {
    "restrictToWorkspace": true,
    "allowedPaths": ["~/projects/my-app"],
    "protectedFiles": [
      "nanobot/agent/tools/filesystem.py",
      "nanobot/agent/tools/shell.py"
    ]
  }
}
```

### Agent 默认参数

```json
{
  "agents": {
    "defaults": {
      "model": "dashscope/qwen-plus",
      "maxTokens": 8192,
      "temperature": 0.7,
      "contextWindow": 32768,
      "summarizeThreshold": 0.6
    }
  }
}
```

`summarizeThreshold`：当 prompt token 数达到 `contextWindow` 的该比例时，自动在后台对历史对话进行摘要压缩（不阻塞当前对话）。

---

## 🖥️ 命令行参考

| 命令 | 说明 |
|------|------|
| `nanobot agent -m "..."` | 单条消息对话 |
| `nanobot agent` | 交互式对话模式 |
| `nanobot agent --logs` | 显示运行日志 |
| `nanobot gateway` | 启动所有已启用的渠道 |
| `nanobot status` | 查看提供商和渠道状态 |
| `nanobot cron list` | 列出定时任务 |
| `nanobot cron add ...` | 添加定时任务 |
| `nanobot cron remove <id>` | 删除定时任务 |

交互模式退出：输入 `exit`、`quit`、`/exit`、`/quit`、`:q` 或按 `Ctrl+D`。

---

<p align="center">
  <sub>Spark-nanobot 基于 <a href="https://github.com/x-ding-dingding/cyper_bot">nanobot</a> 构建，供个人使用、学习研究和技术探索。</sub>
</p>
