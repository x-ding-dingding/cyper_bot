# nanobot 项目架构说明（AI 开发者预读文档）

> **用途**：本文档面向需要对 nanobot 进行开发的 AI 助手。先读此文档建立全局认知，再制定计划，最后按需阅读具体代码文件进行修正。
>
> **项目定位**：nanobot 是一个超轻量级（~3,500 行核心代码）的个人 AI 助手框架，支持多 LLM 提供商、多聊天渠道、工具调用、定时任务、记忆系统和子代理。

---

## 一、技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python ≥ 3.11 |
| 包管理 | hatchling (pyproject.toml) |
| CLI | typer + rich |
| LLM 调用 | litellm（统一多提供商接口） |
| 数据模型 | pydantic v2 + pydantic-settings |
| 异步 | asyncio（全异步架构） |
| 日志 | loguru |
| 渠道 SDK | python-telegram-bot, lark-oapi, dingtalk-stream, slack-sdk, qq-botpy, discord 原生 WebSocket 等 |

---

## 二、目录结构与模块职责

```
nanobot/
├── __init__.py              # 版本号 (__version__)
├── __main__.py              # python -m nanobot 入口 → cli.commands:app
│
├── cli/
│   └── commands.py          # CLI 命令定义（onboard / agent / gateway / cron / status）
│                            # 入口函数 app = typer.Typer()
│
├── config/
│   ├── schema.py            # 所有配置的 Pydantic 模型（Config 为根模型）
│   └── loader.py            # 从 ~/.nanobot/config.json 加载/保存配置
│                            # camelCase ↔ snake_case 自动转换
│
├── bus/
│   ├── events.py            # InboundMessage / OutboundMessage 数据类
│   └── queue.py             # MessageBus：asyncio.Queue 实现的异步消息总线
│
├── agent/
│   ├── loop.py              # ★ AgentLoop：核心处理引擎（收消息→构建上下文→调LLM→执行工具→回消息）
│   ├── context.py           # ContextBuilder：组装 system prompt（bootstrap 文件 + 记忆 + 技能）
│   ├── memory.py            # MemoryStore：日记（YYYY-MM-DD.md）+ 长期记忆（MEMORY.md）
│   ├── skills.py            # SkillsLoader：技能发现与加载（workspace/skills/ + 内置 skills/）
│   ├── subagent.py          # SubagentManager：后台子代理（独立工具集，无 message/spawn 工具）
│   ├── summarizer.py        # Summarizer：后台异步对话摘要（context window 管理）
│   └── tools/
│       ├── base.py          # Tool 抽象基类（name/description/parameters/execute + 参数校验）
│       ├── registry.py      # ToolRegistry：工具注册/查找/执行
│       ├── filesystem.py    # ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
│       ├── shell.py         # ExecTool（带危险命令拦截 + 超时 + 路径限制）
│       ├── web.py           # WebSearchTool（Brave API）, WebFetchTool（readability 提取）
│       ├── message.py       # MessageTool（向用户发消息）
│       ├── spawn.py         # SpawnTool（启动子代理）
│       ├── cron.py          # CronTool（创建/管理定时任务）
│       └── sticker.py       # StickerTool（发送表情包图片）
│
├── providers/
│   ├── base.py              # LLMProvider 抽象基类 + LLMResponse / ToolCallRequest 数据类
│   ├── litellm_provider.py  # LiteLLMProvider：通过 litellm 统一调用所有 LLM
│   ├── registry.py          # ProviderSpec + PROVIDERS 元组：提供商元数据注册表
│   └── transcription.py     # 语音转文字（Groq Whisper）
│
├── channels/
│   ├── base.py              # BaseChannel 抽象基类（start/stop/send + 权限检查 + /reset 拦截）
│   ├── manager.py           # ChannelManager：初始化已启用渠道 + 路由出站消息
│   ├── telegram.py          # Telegram 渠道实现
│   ├── discord.py           # Discord 渠道实现（原生 WebSocket）
│   ├── whatsapp.py          # WhatsApp 渠道实现（通过 Node.js bridge）
│   ├── feishu.py            # 飞书渠道实现
│   ├── dingtalk.py          # 钉钉渠道实现
│   ├── slack.py             # Slack 渠道实现
│   ├── email.py             # Email 渠道实现（IMAP/SMTP）
│   ├── qq.py                # QQ 渠道实现
│   └── mochat.py            # Mochat 渠道实现（Socket.IO）
│
├── session/
│   └── manager.py           # SessionManager + Session：会话持久化（JSONL 格式存储在 ~/.nanobot/sessions/）
│
├── cron/
│   ├── types.py             # CronJob / CronSchedule / CronPayload 等数据类
│   └── service.py           # CronService：定时任务调度引擎（at/every/cron 三种模式）
│
├── heartbeat/
│   └── service.py           # HeartbeatService：每 30 分钟读取 HEARTBEAT.md 并执行任务
│
├── utils/
│   └── helpers.py           # 工具函数（路径、日期、文件名安全化等）
│
└── skills/                  # 内置技能目录（每个技能一个子目录，含 SKILL.md）

workspace/                   # 运行时工作区（默认 ~/.nanobot/workspace/）
├── AGENTS.md                # Agent 行为指令（注入 system prompt）
├── SOUL.md                  # 人格/身份定义（注入 system prompt）
├── USER.md                  # 用户画像（注入 system prompt）
├── TOOLS.md                 # 工具使用说明（注入 system prompt）
├── HEARTBEAT.md             # 心跳任务列表
├── IDENTITY.md              # 可选的身份补充
└── memory/
    ├── MEMORY.md            # 长期记忆
    └── YYYY-MM-DD.md        # 每日笔记

bridge/                      # WhatsApp Node.js 桥接服务（TypeScript）
```

---

## 三、核心数据流

```
用户消息
    │
    ▼
[Channel] ──publish_inbound──▶ [MessageBus.inbound Queue]
                                       │
                                       ▼
                               [AgentLoop._process_message]
                                       │
                    ┌──────────────────┤
                    ▼                  ▼
            ContextBuilder        SessionManager
            (system prompt         (历史消息)
             + bootstrap
             + memory
             + skills)
                    │                  │
                    └────────┬─────────┘
                             ▼
                    组装 messages[]
                             │
                    ┌────────┴────────┐
                    ▼                 │
              LLMProvider.chat()      │
                    │                 │
              ┌─────┴─────┐          │
              ▼           ▼          │
         有 tool_calls  无 tool_calls │
              │           │          │
              ▼           ▼          │
        ToolRegistry   final_content │
        .execute()        │          │
              │           │          │
              ▼           │          │
        追加结果到         │          │
        messages[]        │          │
              │           │          │
              └───循环────┘          │
                             │       │
                             ▼       │
                    保存到 Session ◄──┘
                             │
                             ▼
                    检查是否需要 Summarize
                             │
                             ▼
                    OutboundMessage
                             │
                             ▼
              [MessageBus.outbound Queue]
                             │
                             ▼
              [ChannelManager._dispatch_outbound]
                             │
                             ▼
                    [Channel.send()]
                             │
                             ▼
                        用户收到回复
```

---

## 四、关键设计模式与约定

### 4.1 消息总线解耦

- **MessageBus** 是 Channel 和 AgentLoop 之间的唯一桥梁
- Channel 只负责协议适配（收发消息），不直接调用 Agent
- 所有消息通过 `InboundMessage` / `OutboundMessage` 数据类传递
- Session key 格式：`"{channel}:{chat_id}"`（如 `telegram:123456`）

### 4.2 System Prompt 组装（ContextBuilder）

system prompt 由以下部分按顺序拼接（用 `---` 分隔）：

1. **System Context**：运行时信息（时间、OS、workspace 路径、工具说明）
2. **Bootstrap 文件**：`AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `IDENTITY.md`（按此顺序，存在则加载）
3. **Memory**：长期记忆 + 当日笔记
4. **Always Skills**：标记为 `always=true` 的技能全文
5. **Skills Summary**：所有技能的 XML 摘要（agent 按需用 `read_file` 加载完整内容）
6. **Current Session**：当前 channel + chat_id
7. **Conversation Summary**：如果有之前被驱逐的对话摘要

### 4.3 工具系统

- 所有工具继承 `Tool` 基类，实现 `name`, `description`, `parameters`, `execute`
- 工具在 `AgentLoop._register_default_tools()` 中注册到 `ToolRegistry`
- 工具定义通过 `to_schema()` 转为 OpenAI function calling 格式
- 工具执行前自动做参数校验（`validate_params`）
- **添加新工具的步骤**：
  1. 在 `nanobot/agent/tools/` 下创建新文件，继承 `Tool`
  2. 在 `AgentLoop._register_default_tools()` 中 import 并注册

### 4.4 LLM Provider 体系

- 唯一实现类 `LiteLLMProvider`，通过 litellm 库统一调用所有提供商
- `providers/registry.py` 中的 `PROVIDERS` 元组是提供商元数据的单一数据源
- **添加新提供商的步骤**：
  1. 在 `PROVIDERS` 元组中添加一个 `ProviderSpec`
  2. 在 `config/schema.py` 的 `ProvidersConfig` 中添加对应字段
- Provider 分两类：
  - **Gateway**（如 OpenRouter, AiHubMix）：可路由任意模型，通过 api_key 前缀或 api_base 关键词检测
  - **Standard**（如 Anthropic, DeepSeek）：通过模型名关键词匹配

### 4.5 Channel 体系

- 所有渠道继承 `BaseChannel`，实现 `start()`, `stop()`, `send()`
- `ChannelManager` 根据配置中 `enabled: true` 的渠道动态初始化
- 权限控制：每个渠道配置 `allow_from` 列表，空列表 = 允许所有人
- 内置 `/reset`, `/clear`, `/new` 命令清除会话历史

### 4.6 会话管理

- `Session` 存储消息列表 + 元数据 + 对话摘要
- 持久化为 JSONL 文件（`~/.nanobot/sessions/{channel}_{chat_id}.jsonl`）
- 第一行是 metadata（含 summary），后续每行一条消息
- `get_history(max_messages=50)` 返回最近 50 条消息给 LLM

### 4.7 Context Window 管理（Summarizer）

- 当 LLM 返回的 `prompt_tokens` 达到 `context_window * summarize_threshold`（默认 60%）时触发
- 异步后台执行，不阻塞主 agent loop
- 生成摘要后：`session.summary = 摘要文本`，`session.messages` 只保留最近 `message_buffer_min` 条
- 下次构建 prompt 时，摘要作为 "Conversation Summary" 段落注入 system prompt

### 4.8 定时任务（Cron + Heartbeat）

- **CronService**：支持三种调度模式 — `at`（一次性）、`every`（间隔）、`cron`（cron 表达式）
- **HeartbeatService**：每 30 分钟检查 `HEARTBEAT.md`，有任务则唤醒 agent 执行
- 两者独立运行，Cron 通过 CronTool 暴露给 agent，Heartbeat 自动触发

### 4.9 子代理（Subagent）

- 通过 `SpawnTool` 触发，在后台 asyncio.Task 中运行
- 拥有独立的 ToolRegistry（无 message/spawn 工具，防止递归）
- 完成后通过 MessageBus 注入 `channel="system"` 的消息，主 agent 收到后自然语言总结给用户

---

## 五、配置体系

- 配置文件：`~/.nanobot/config.json`（camelCase JSON）
- 代码中使用 snake_case（Pydantic 模型），loader 自动转换
- 根模型 `Config` 包含：
  - `providers: ProvidersConfig` — 各 LLM 提供商的 API key / base
  - `agents: AgentsConfig` — 默认模型、温度、max_tokens、context_window 等
  - `channels: ChannelsConfig` — 各聊天渠道的启用状态和凭证
  - `tools: ToolsConfig` — 工具配置（web search key、exec timeout、路径限制）
  - `gateway: GatewayConfig` — 网关服务端口

---

## 六、CLI 命令

| 命令 | 功能 |
|------|------|
| `nanobot onboard` | 初始化配置和工作区 |
| `nanobot agent -m "..."` | 单次对话（CLI 模式） |
| `nanobot agent` | 交互式对话（REPL） |
| `nanobot gateway` | 启动网关（所有渠道 + agent loop + cron + heartbeat） |
| `nanobot cron add/list/remove` | 管理定时任务 |
| `nanobot status` | 查看系统状态 |

---

## 七、开发常见任务速查

### 添加新的聊天渠道

1. 在 `nanobot/channels/` 下创建 `{name}.py`，继承 `BaseChannel`
2. 在 `config/schema.py` 中添加 `{Name}Config` 模型，并加入 `ChannelsConfig`
3. 在 `channels/manager.py` 的 `_init_channels()` 中添加初始化逻辑

### 添加新的 LLM 提供商

1. 在 `providers/registry.py` 的 `PROVIDERS` 元组中添加 `ProviderSpec`
2. 在 `config/schema.py` 的 `ProvidersConfig` 中添加字段

### 添加新的工具

1. 在 `nanobot/agent/tools/` 下创建文件，继承 `Tool` 基类
2. 在 `agent/loop.py` 的 `_register_default_tools()` 中 import 并注册

### 修改 Agent 行为/人格

- 编辑 `workspace/SOUL.md`（人格）或 `workspace/AGENTS.md`（行为指令）
- 这些文件在每次对话时作为 system prompt 的一部分注入

### 修改 System Prompt 结构

- 修改 `agent/context.py` 的 `build_system_prompt()` 和 `_get_identity()`

---

## 八、关键文件快速索引

> 按"改动频率"排序，最常需要修改的在前面。

| 场景 | 需要看的文件 |
|------|-------------|
| 理解核心循环 | `agent/loop.py` |
| 理解 prompt 组装 | `agent/context.py` |
| 添加/修改工具 | `agent/tools/base.py` + `agent/tools/registry.py` + `agent/loop.py` |
| 添加 LLM 提供商 | `providers/registry.py` + `config/schema.py` |
| 添加聊天渠道 | `channels/base.py` + `channels/manager.py` + `config/schema.py` |
| 修改配置结构 | `config/schema.py` + `config/loader.py` |
| 会话/历史管理 | `session/manager.py` |
| 记忆系统 | `agent/memory.py` |
| 技能系统 | `agent/skills.py` |
| 定时任务 | `cron/service.py` + `cron/types.py` |
| 心跳任务 | `heartbeat/service.py` |
| 子代理 | `agent/subagent.py` |
| 对话摘要 | `agent/summarizer.py` |
| CLI 命令 | `cli/commands.py` |

---

## 九、注意事项

1. **全异步架构**：所有 I/O 操作都是 async/await，工具的 `execute` 方法也是 async
2. **受保护文件**：`config/schema.py` 中的 `protected_files` 列表定义了 agent 自身不可修改的核心文件
3. **路径安全**：`restrict_to_workspace` 开启时，文件和 shell 工具只能访问 workspace + allowed_paths
4. **配置格式**：JSON 文件用 camelCase，Python 代码用 snake_case，`loader.py` 自动转换
5. **会话隔离**：不同 channel:chat_id 有独立的 Session，互不干扰
6. **子代理隔离**：子代理没有 message/spawn 工具，不能直接给用户发消息或递归 spawn
7. **Summarizer 是异步的**：摘要在后台生成，不阻塞当前对话，通过 `summary_in_progress` 标志防止重复触发
