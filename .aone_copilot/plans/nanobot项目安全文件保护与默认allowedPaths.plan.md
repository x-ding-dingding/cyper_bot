### nanobot项目安全文件保护与默认allowedPaths ###
将 nanobot 项目根目录默认加入 allowedPaths，并对项目内的安全敏感文件（路径校验、命令执行守卫等）做写保护，防止模型工具篡改这些文件后绕过安全限制。保护范围仅限 nanobot 项目目录，不影响其他 allowedPaths 下的文件操作。


## 步骤一：在 `nanobot/config/schema.py` 中新增配置项

在 `ToolsConfig` 中：

- 新增 `project_root: str` 字段，默认值通过 `Path(__file__).parent.parent` 计算得到 nanobot 项目根目录的绝对路径
- 新增 `protected_files: list[str]` 字段，默认值为项目内需要保护的安全文件相对路径列表：
  - `nanobot/agent/tools/filesystem.py`
  - `nanobot/agent/tools/shell.py`
  - `nanobot/agent/tools/base.py`
  - `nanobot/agent/tools/registry.py`
  - `nanobot/agent/loop.py`
  - `nanobot/config/schema.py`
  - `nanobot/config/loader.py`
  - `nanobot/agent/subagent.py`
- 新增 `effective_allowed_paths` 属性方法，自动将 `project_root` 合并到 `allowed_paths` 中返回（去重）

## 步骤二：修改 `nanobot/agent/tools/filesystem.py` 的路径校验逻辑

修改 `_resolve_path()` 函数：

- 新增参数 `protected_paths: list[Path] | None = None`
- 在 `allowed_dirs` 校验通过后，增加一步检查：如果 `protected_paths` 不为空，判断 resolved path 是否命中其中任何一个，若命中则抛出 `PermissionError`
- 这里的 `protected_paths` 是绝对路径列表（由 `project_root + 相对路径` 拼接而成），只会匹配到 nanobot 项目内的特定文件

修改 `ReadFileTool` 构造函数：不限制读取（保护文件允许读，不允许写/改）

修改 `WriteFileTool`、`EditFileTool` 构造函数：新增 `protected_paths` 参数，传入 `_resolve_path`

`ListDirTool` 不需要保护（列目录不影响安全）

## 步骤三：修改 `nanobot/agent/tools/shell.py` 的命令守卫

在 `ExecTool.__init__` 中新增 `protected_paths: list[Path] | None = None` 参数

在 `_guard_command()` 中增加检查：如果命令中包含对 `protected_paths` 中文件的写入/删除操作（如 `> protected_file`、`rm protected_file`、`mv ... protected_file`、`cp ... protected_file`、`sed -i ... protected_file` 等），则拦截

## 步骤四：修改 `nanobot/agent/loop.py` 的工具注册逻辑

在 `AgentLoop.__init__` 中：

- 新增 `protected_files: list[str] | None = None` 参数
- 将 `project_root + protected_files` 拼接为绝对路径列表 `self.protected_paths`

在 `_register_default_tools()` 中：

- `WriteFileTool` 和 `EditFileTool` 传入 `protected_paths=self.protected_paths`
- `ExecTool` 传入 `protected_paths=self.protected_paths`
- `ReadFileTool` 和 `ListDirTool` 不传（允许读取和列目录）

## 步骤五：修改 `nanobot/agent/subagent.py` 的工具注册逻辑

在 `SubagentManager.__init__` 中新增 `protected_paths` 和 `allowed_paths` 参数

在 `_run_subagent()` 中注册工具时：

- 将 `allowed_paths` 传递给文件工具（修复现有的安全漏洞：子 agent 未继承 `allowed_paths`）
- 将 `protected_paths` 传递给 `WriteFileTool`、`EditFileTool`、`ExecTool`

## 步骤六：修改 `nanobot/cli/commands.py` 的参数传递

在 `gateway` 命令和 `agent` 命令中构造 `AgentLoop` 时：

- `allowed_paths` 改用 `config.tools.effective_allowed_paths`（自动包含项目目录）
- 新增传入 `protected_files=config.tools.protected_files` 和 `project_root=config.tools.project_root`

## 步骤七：更新 `README.md` 配置文档

在 tools 配置表格中新增：

- `tools.protectedFiles` 的说明：项目内受保护的安全文件列表，模型工具不允许对这些文件进行写入、编辑或删除操作，但允许读取
- 说明保护范围仅限 nanobot 项目目录内，不影响其他 `allowedPaths` 下的文件


updateAtTime: 2026/2/14 14:34:18

planId: 65abecdc-88f8-4129-864e-813e853ab263