### migrate-config-to-project-dir ###
将所有配置文件（config.json、cron/jobs.json、sessions/）从 ~/.nanobot/ 迁移到项目目录下，统一管理。修改代码中的路径引用，使 data_dir 默认为项目根目录而非 ~/.nanobot/。


## 实施计划

### 核心思路

将 `get_data_path()` 的默认值从 `~/.nanobot` 改为**项目根目录**（即 `nanobot` 包所在的目录）。这样 `config.json`、`cron/`、`sessions/` 都会存储在项目目录下，跟着 git 仓库走。

项目目录结构变化：
```
nanobot/                          # 项目根目录
├── config.json                   # 主配置（从 ~/.nanobot/config.json 迁移）
├── cron/
│   └── jobs.json                 # 定时任务（从 ~/.nanobot/cron/jobs.json 迁移）
├── sessions/                     # 会话历史（从 ~/.nanobot/sessions/ 迁移）
│   ├── dingtalk_xxx.jsonl
│   └── cli_direct.jsonl
├── workspace/                    # workspace（已在项目目录下）
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── memory/
│   └── skills/
├── nanobot/                      # Python 包
│   ├── __init__.py
│   ├── config/
│   ├── agent/
│   └── ...
└── pyproject.toml
```

### 步骤 1：修改 `nanobot/utils/helpers.py`

将 `get_data_path()` 从 `Path.home() / ".nanobot"` 改为项目根目录：

```python
def get_project_root() -> Path:
    """Get the nanobot project root directory (where pyproject.toml lives)."""
    # nanobot/utils/helpers.py → 向上 2 级到项目根目录
    return Path(__file__).parent.parent.parent.resolve()

def get_data_path() -> Path:
    """Get the nanobot data directory (project root)."""
    return get_project_root()
```

同时更新 `get_workspace_path()` 的默认值：
```python
def get_workspace_path(workspace: str | None = None) -> Path:
    if workspace:
        path = Path(workspace).expanduser()
    else:
        path = get_project_root() / "workspace"
    return ensure_dir(path)
```

### 步骤 2：修改 `nanobot/config/loader.py`

将 `get_config_path()` 改为使用项目根目录：

```python
def get_config_path() -> Path:
    """Get the default configuration file path."""
    from nanobot.utils.helpers import get_project_root
    return get_project_root() / "config.json"
```

### 步骤 3：修改 `nanobot/session/manager.py`

将 sessions 目录从 `~/.nanobot/sessions` 改为项目目录下：

```python
# 原来：self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
# 改为：
from nanobot.utils.helpers import get_data_path
self.sessions_dir = ensure_dir(get_data_path() / "sessions")
```

### 步骤 4：修改 `nanobot/config/schema.py`

将 `AgentDefaults.workspace` 的默认值改为相对路径：

```python
# 原来：workspace: str = "~/.nanobot/workspace"
# 改为：
workspace: str = ""  # Empty means use project_root/workspace
```

同时更新 `Config.workspace_path` 属性的逻辑，当 workspace 为空时使用项目根目录下的 workspace。

### 步骤 5：修改 `nanobot/cli/commands.py` 的 `onboard` 命令

`onboard` 命令不再创建 `~/.nanobot/` 目录，而是在项目目录下创建 `config.json` 和 workspace：

- `config.json` → 项目根目录
- workspace 模板文件 → `项目根目录/workspace/`

### 步骤 6：迁移现有数据文件

将 `~/.nanobot/` 下的文件迁移到项目目录：

```bash
# 迁移 config.json
cp ~/.nanobot/config.json /Users/xiongmengjun/Documents/program/nanobot/config.json

# 迁移 cron jobs
mkdir -p /Users/xiongmengjun/Documents/program/nanobot/cron
cp ~/.nanobot/cron/jobs.json /Users/xiongmengjun/Documents/program/nanobot/cron/jobs.json

# 迁移 sessions
mkdir -p /Users/xiongmengjun/Documents/program/nanobot/sessions
cp ~/.nanobot/sessions/*.jsonl /Users/xiongmengjun/Documents/program/nanobot/sessions/
```

### 步骤 7：更新 `.gitignore`

在 `.gitignore` 中添加敏感文件的排除规则：

```gitignore
# Config with API keys
config.json

# Session history (private)
sessions/

# Cron state (runtime data)
cron/
```

### 步骤 8：更新 config.json 中的 workspace 路径

将 `config.json` 中的 `agents.defaults.workspace` 从绝对路径改为空字符串（使用默认的项目目录下 workspace）：

```json
"workspace": ""
```

### 步骤 9：验证

- 确认所有路径引用正确
- 确认 `nanobot gateway` 启动后能正确加载 config、cron、sessions
- 检查 lint 错误


updateAtTime: 2026/3/6 14:43:48

planId: c47f42ee-e928-4892-b617-d1d4b9907146