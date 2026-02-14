# Nanobot 架构与配置参考文档

## 一、目录结构总览

```
~/.nanobot/                          # 数据根目录 (get_data_path)
├── config.json                      # 主配置文件
├── sessions/                        # 会话历史存储
│   └── {channel}_{chat_id}.jsonl    # 每个会话一个 JSONL 文件
└── workspace/                       # 工作区 (默认路径，可在 config 中修改)
    ├── AGENTS.md                    # Agent 行为指令 (Bootstrap)
    ├── SOUL.md                      # 人格/身份设定 (Bootstrap)
    ├── USER.md                      # 用户画像 (Bootstrap)
    ├── TOOLS.md                     # 工具使用说明 (Bootstrap)
    ├── IDENTITY.md                  # 身份补充 (Bootstrap, 可选)
    ├── HEARTBEAT.md                 # 心跳任务清单 (每30分钟检查)
    ├── memory/
    │   ├── MEMORY.md                # 长期记忆
    │   └── YYYY-MM-DD.md           # 每日记忆笔记
    ├── skills/
    │   └── {skill-name}/
    │       └── SKILL.md             # 自定义技能
    └── stickers/
        └── index.json               # 表情包索引
```

---

## 二、记忆系统 (Memory)

> 代码位置：`nanobot/agent/memory.py` → `MemoryStore` 类

### 2.1 长期记忆 — `MEMORY.md`

- **路径**：`{workspace}/memory/MEMORY.md`
- **用途**：存储跨会话的持久信息，如用户偏好、项目上下文、重要笔记
- **更新方式**：**完全由 Agent 自主决定**。Agent 在对话中认为某些信息值得记住时，会通过 `write_file` 工具写入此文件
- **读取时机**：每次构建 system prompt 时，`MemoryStore.get_memory_context()` 会读取此文件内容，作为 `## Long-term Memory` 注入到 system prompt 中
- **没有自动压缩/摘要机制**，内容会持续增长

### 2.2 每日记忆 — `YYYY-MM-DD.md`

- **路径**：`{workspace}/memory/YYYY-MM-DD.md`（如 `2026-02-13.md`）
- **用途**：记录当天的笔记、事件、临时信息
- **更新方式**：**同样由 Agent 自主决定**。Agent 通过 `write_file` / `edit_file` 工具写入
- **读取时机**：每次构建 system prompt 时，`MemoryStore.get_memory_context()` 只读取**当天**的文件，作为 `## Today's Notes` 注入
- **历史日记**：`get_recent_memories(days=7)` 方法可以读取最近 N 天的记忆，但**目前没有被任何地方调用**，仅作为 API 保留
- **没有自动创建**：如果 Agent 当天没有主动写入，就不会有当天的文件

### 2.3 关键结论：没有"每周记录"

项目中**不存在每周记录/周报机制**。记忆系统只有两层：
1. 长期记忆（`MEMORY.md`，一个文件，持续累积）
2. 每日记忆（`YYYY-MM-DD.md`，按天分文件）

两者都不会自动生成，完全依赖 Agent 在对话中主动调用文件工具写入。

---

## 三、上下文管理 (Context)

> 代码位置：`nanobot/agent/context.py` → `ContextBuilder` 类

### 3.1 System Prompt 构成

每次 LLM 调用时，system prompt 按以下顺序拼接：

| 顺序 | 内容 | 来源 |
|------|------|------|
| 1 | 核心身份 + 运行时信息 | `ContextBuilder._get_identity()` 硬编码 |
| 2 | Bootstrap 文件 | `AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`、`IDENTITY.md` |
| 3 | 长期记忆 + 当日笔记 | `memory/MEMORY.md` + `memory/YYYY-MM-DD.md` |
| 4 | Always-on 技能 | 标记了 `always=true` 的 SKILL.md 全文 |
| 5 | 技能摘要 | 所有技能的名称/描述/路径（XML 格式） |
| 6 | 当前会话信息 | `Channel: xxx` / `Chat ID: xxx` |

各部分之间用 `\n\n---\n\n` 分隔。

### 3.2 消息列表结构

```
[system_prompt] → 1 条 system 消息
[history]       → 最近 50 条历史消息 (user/assistant 交替)
[current_msg]   → 1 条当前用户消息 (可能带图片 base64)
```

### 3.3 上下文截断策略

**没有基于 token 的截断，只有基于消息条数的硬性截断：**

- `Session.get_history(max_messages=50)` — 取最近 50 条消息
- 超过 50 条时，直接丢弃最早的消息，**不做摘要**
- 不计算 token 数量，不感知模型的 context window 大小
- 如果 system prompt 本身很大（SOUL.md + MEMORY.md 内容多），可能导致总 token 超出模型限制

### 3.4 当前轮次的 Tool Calls

在单次消息处理的 agent loop 中（最多 20 轮迭代）：
- assistant 消息（带 `tool_calls`）和 tool result 会不断追加到 `messages` 列表
- 这些**中间过程不会被保存到 session**
- Session 只保存最终的 `user` 和 `assistant` 纯文本消息

---

## 四、会话管理 (Session)

> 代码位置：`nanobot/session/manager.py` → `SessionManager` 类

### 4.1 存储

- **路径**：`~/.nanobot/sessions/{channel}_{chat_id}.jsonl`
- **格式**：JSONL（每行一个 JSON 对象）
  - 第一行：metadata（创建时间、更新时间）
  - 后续行：消息记录 `{role, content, timestamp}`
- **缓存**：内存中有 `_cache` 字典，避免重复读盘

### 4.2 Session Key

- 格式：`{channel}:{chat_id}`
- 私聊：`dingtalk:030950616458756705`（chat_id = sender_id）
- 群聊：`dingtalk:{conversation_id}`（chat_id = conversation_id，按群维度隔离）

### 4.3 清空

用户发送 `/reset`、`/clear`、`/new` 可以清空当前会话历史。

---

## 五、定时任务系统

### 5.1 Heartbeat（心跳服务）

> 代码位置：`nanobot/heartbeat/service.py` → `HeartbeatService` 类

- **检查间隔**：默认 30 分钟（`DEFAULT_HEARTBEAT_INTERVAL_S = 1800`）
- **工作方式**：
  1. 每 30 分钟读取 `{workspace}/HEARTBEAT.md`
  2. 如果文件为空或只有标题/注释，跳过
  3. 如果有内容，发送固定 prompt 给 Agent：`"Read HEARTBEAT.md in your workspace..."`
  4. Agent 读取文件并执行任务
  5. 如果 Agent 回复包含 `HEARTBEAT_OK`，表示无需操作
- **任务管理**：Agent 通过 `edit_file` / `write_file` 工具编辑 `HEARTBEAT.md` 来增删任务

### 5.2 Cron（定时调度）

> 代码位置：`nanobot/cron/service.py` → `CronService` 类

- **存储路径**：通过 `store_path` 参数指定（JSON 文件）
- **三种调度方式**：
  - `at`：一次性定时（指定时间戳）
  - `every`：固定间隔（毫秒）
  - `cron`：cron 表达式（依赖 `croniter` 库）
- **任务载荷**：
  - `agent_turn`：触发一次 Agent 对话
  - 可选 `deliver: true` 将结果发送到指定 channel/chat
- **管理方式**：通过 CLI 命令 `nanobot cron add/list/remove` 或 Agent 调用 `exec` 工具

---

## 六、配置文件详解

### 6.1 主配置文件

- **路径**：`~/.nanobot/config.json`
- **格式**：JSON，使用 camelCase 键名（加载时自动转 snake_case）
- **加载逻辑**：`nanobot/config/loader.py` → `load_config()`

### 6.2 配置结构

```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.nanobot/workspace",  // 工作区路径
      "model": "anthropic/claude-opus-4-5",   // 默认模型
      "maxTokens": 8192,                     // 最大输出 token
      "temperature": 0.7,                    // 采样温度
      "maxToolIterations": 20               // Agent loop 最大迭代次数
    }
  },
  "providers": {
    "anthropic": { "apiKey": "", "apiBase": null },
    "openai": { "apiKey": "", "apiBase": null },
    "openrouter": { "apiKey": "", "apiBase": null },
    "deepseek": { "apiKey": "", "apiBase": null },
    "groq": { "apiKey": "", "apiBase": null },
    "zhipu": { "apiKey": "", "apiBase": null },
    "dashscope": { "apiKey": "", "apiBase": null },
    "vllm": { "apiKey": "", "apiBase": null },
    "gemini": { "apiKey": "", "apiBase": null },
    "moonshot": { "apiKey": "", "apiBase": null },
    "minimax": { "apiKey": "", "apiBase": null },
    "aihubmix": { "apiKey": "", "apiBase": null, "extraHeaders": {} }
  },
  "channels": {
    "dingtalk": { "enabled": false, "clientId": "", "clientSecret": "", "allowFrom": [] },
    "telegram": { "enabled": false, "token": "", "allowFrom": [], "proxy": null },
    "feishu": { "enabled": false, "appId": "", "appSecret": "", "allowFrom": [] },
    "discord": { "enabled": false, "token": "", "allowFrom": [] },
    "whatsapp": { "enabled": false, "bridgeUrl": "ws://localhost:3001", "allowFrom": [] },
    "slack": { "enabled": false, "botToken": "", "appToken": "", "mode": "socket" },
    "email": { "enabled": false, "imapHost": "", "smtpHost": "", "allowFrom": [] },
    "qq": { "enabled": false, "appId": "", "secret": "", "allowFrom": [] },
    "mochat": { "enabled": false, "baseUrl": "https://mochat.io", "clawToken": "" }
  },
  "tools": {
    "web": { "search": { "apiKey": "" } },
    "exec": { "timeout": 60 },
    "restrictToWorkspace": false
  },
  "gateway": { "host": "0.0.0.0", "port": 18790 }
}
```

### 6.3 Bootstrap 文件（工作区）

这些文件在每次 LLM 调用时被读取并注入 system prompt：

| 文件 | 路径 | 用途 |
|------|------|------|
| `AGENTS.md` | `{workspace}/AGENTS.md` | Agent 行为指令、工具使用指南、任务管理规则 |
| `SOUL.md` | `{workspace}/SOUL.md` | 人格设定、语言风格、对话示例 |
| `USER.md` | `{workspace}/USER.md` | 用户画像、偏好、工作上下文 |
| `TOOLS.md` | `{workspace}/TOOLS.md` | 工具详细使用文档 |
| `IDENTITY.md` | `{workspace}/IDENTITY.md` | 身份补充信息（可选，文件不存在则跳过） |

### 6.4 其他关键文件路径

| 文件/目录 | 路径 | 用途 |
|-----------|------|------|
| 长期记忆 | `{workspace}/memory/MEMORY.md` | Agent 的持久记忆 |
| 每日笔记 | `{workspace}/memory/YYYY-MM-DD.md` | 按天的临时笔记 |
| 心跳任务 | `{workspace}/HEARTBEAT.md` | 每 30 分钟检查的周期任务 |
| 表情包索引 | `{workspace}/stickers/index.json` | 表情包名称→图片URL映射 |
| 自定义技能 | `{workspace}/skills/{name}/SKILL.md` | 可扩展的技能定义 |
| 内置技能 | `nanobot/skills/{name}/SKILL.md` | 项目自带的技能 |
| 会话存储 | `~/.nanobot/sessions/*.jsonl` | 对话历史 |
| Cron 存储 | 由 `CronService(store_path=...)` 指定 | 定时任务持久化 |

---

## 七、数据流总结

```
用户消息
  ↓
Channel (dingtalk/telegram/...) 接收
  ↓
MessageBus.publish_inbound()
  ↓
AgentLoop._process_message()
  ├── SessionManager.get_or_create() → 加载历史
  ├── ContextBuilder.build_messages() → 组装 system prompt + 历史 + 当前消息
  │   ├── 读取 Bootstrap 文件 (AGENTS/SOUL/USER/TOOLS/IDENTITY.md)
  │   ├── 读取 Memory (MEMORY.md + 当日笔记)
  │   └── 加载 Skills 摘要
  ├── LLM 调用 (最多 20 轮 tool calling 迭代)
  ├── Session 保存 (只存 user + assistant 纯文本)
  └── 返回 OutboundMessage
  ↓
MessageBus.publish_outbound()
  ↓
Channel.send() → 发送给用户
```

---

## 八、自定义工具热加载

> 代码位置：`nanobot/agent/loop.py` → `AgentLoop._load_custom_tools()` 方法

### 8.1 概述

Agent 可以在运行时通过在 `{workspace}/tools/` 目录下创建 Python 文件来扩展自己的工具集。新工具在下一条消息处理时**自动加载**，无需重启。

### 8.2 加载流程

```
用户消息到达
  ↓
_process_message()
  ├── _load_custom_tools()          ← 每次消息处理前执行
  │   ├── 扫描 {workspace}/tools/*.py
  │   ├── 跳过 _ 开头的文件
  │   ├── 跳过已注册的工具（防重复加载）
  │   ├── 读取源码 → 静态安全扫描
  │   │   └── 匹配 _FORBIDDEN_TOOL_PATTERNS（正则列表）
  │   │       命中 → 拒绝加载，记录 warning
  │   ├── importlib 动态导入模块
  │   ├── 查找 Tool 子类（每文件仅取第一个）
  │   ├── 检查名称冲突（不允许覆盖内置工具）
  │   └── 注册到 ToolRegistry
  ↓
正常消息处理流程...
```

### 8.3 安全机制

| 层级 | 机制 | 说明 |
|------|------|------|
| **文件位置** | `restrictToWorkspace` | Agent 只能在 workspace 内写文件，自定义工具也只能在 workspace/tools/ 下 |
| **静态扫描** | `_FORBIDDEN_TOOL_PATTERNS` | 加载前扫描源码，禁止 `subprocess`、`open()`、`eval()`、`exec()`、`os.system()`、`ctypes`、`socket` 等 |
| **名称保护** | `tools.has()` 检查 | 自定义工具不能覆盖内置工具（read_file、write_file、exec 等） |
| **沙箱传递** | `allowed_dirs` 参数 | 自定义工具构造时传入与内置工具相同的 `allowed_dirs` 限制 |

### 8.4 禁止的代码模式

```python
_FORBIDDEN_TOOL_PATTERNS = [
    r"\bsubprocess\b",           # 绕过 exec 工具的安全守卫
    r"\bos\.system\s*\(",        # 直接执行系统命令
    r"\bos\.popen\s*\(",         # 管道执行
    r"\bos\.exec\w*\s*\(",       # exec 族函数
    r"\bos\.spawn\w*\s*\(",      # spawn 族函数
    r"\bos\.remove\s*\(",        # 直接删除文件
    r"\bos\.unlink\s*\(",        # 直接删除文件
    r"\bos\.rmdir\s*\(",         # 直接删除目录
    r"\bshutil\.rmtree\s*\(",    # 递归删除目录
    r"\b__import__\s*\(",        # 动态导入
    r"\bimportlib\b",            # 动态导入
    r"\bopen\s*\(",              # 直接文件 IO（应使用内置文件工具）
    r"\beval\s*\(",              # 代码执行
    r"\bexec\s*\(",              # 代码执行
    r"\bcompile\s*\(",           # 代码编译
    r"\bctypes\b",               # C 层调用
    r"\bsocket\b",               # 网络操作
    r"\bpathlib\.Path\s*\(",     # 直接路径操作（应使用内置文件工具）
]
```

### 8.5 关键文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 自定义工具目录 | `{workspace}/tools/*.py` | Agent 创建的自定义工具 |
| 工具基类 | `nanobot/agent/tools/base.py` | `Tool` 抽象基类，自定义工具必须继承 |
| 加载逻辑 | `nanobot/agent/loop.py` | `_load_custom_tools()` 和 `_scan_for_forbidden_patterns()` |
| Agent 文档 | `{workspace}/TOOLS.md` | 告知 Agent 如何创建自定义工具（Bootstrap 注入 system prompt） |

---

## 九、已知限制（含自定义工具相关）

1. **无 token 感知**：不计算上下文 token 数，可能超出模型 context window
2. **无自动摘要**：历史消息只做条数截断（50条），不做内容压缩
3. **记忆无上限**：`MEMORY.md` 会持续增长，全量注入 system prompt
4. **Tool calls 不持久化**：session 不保存中间的 tool_calls 和 tool results，下次对话时 Agent 不知道上次用了什么工具
5. **每日笔记不自动清理**：`memory/` 目录下的日记文件会持续累积，但只有当天的会被加载到上下文

## 十、读写限制

nanobot 提供两种互补的安全机制：

### 10.1 白名单模式（`restrictToWorkspace`）

> 适用于严格沙箱场景。开启后 Agent 只能在 workspace 及 `allowedPaths` 内操作。

| Option | Default | Description |
|--------|---------|-------------|
| `tools.restrictToWorkspace` | `false` | When `true`, restricts **all** agent tools (shell, file read/write/edit, list) to the workspace directory. |
| `tools.allowedPaths` | `[]` | Additional directories the agent is allowed to access when `restrictToWorkspace` is `true`. Supports `~` expansion. |

### 10.2 黑名单模式（`protectedPaths`）— 推荐

> 适用于需要 Agent 自由操作但保护敏感文件的场景。Agent 可以**读取**受保护文件，但不能**写入或编辑**。

| Option | Default | Description |
|--------|---------|-------------|
| `tools.protectedPaths` | `[]` | Files/directories the agent is **NOT** allowed to write or edit. Supports `~` expansion. |

**推荐配置示例**：

```json
{
  "tools": {
    "protectedPaths": [
      "~/.nanobot/config.json",
      "~/myproject/nanobot/config/",
      "~/myproject/nanobot/agent/tools/filesystem.py",
      "~/myproject/nanobot/agent/tools/shell.py",
      "~/myproject/nanobot/agent/loop.py"
    ]
  }
}
```

**保护机制覆盖范围**：

| 工具 | 保护方式 |
|------|---------|
| `write_file` / `edit_file` | `_check_protected()` 检查路径是否匹配黑名单 |
| `exec`（shell） | `_guard_command()` 检测写入操作（`>`、`>>`、`tee`、`cp`、`mv`、`sed -i`）是否指向受保护路径 |
| `read_file` / `list_dir` | 不受限制，Agent 可以读取任何文件 |

### 10.3 用户白名单

| Option | Default | Description |
|--------|---------|-------------|
| `channels.*.allowFrom` | `[]` (allow all) | Whitelist of user IDs. Empty = allow everyone; non-empty = only listed users can interact. |
