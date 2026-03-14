### iFlow 工作目录自动整理功能 ###
为 nanobot 添加 iFlow 工作目录自动整理能力，通过 Skill + Cron 定时任务实现每日 18:00 自动整理 inbox 内容到对应项目，自动 git 提交，并通过钉钉通知整理结果。


## 方案概述

纯配置方案，不修改 nanobot Python 代码。通过 1 个 Skill + 1 个 Cron 定时任务 + AGENTS.md 补充说明实现。

---

## 第一步：创建 iFlow 工作整理 Skill

**文件**: `workspace/skills/iflow-organizer/SKILL.md`

**设置**: `always: false`（不需要每次对话都注入，只在整理任务触发时由 agent 按需读取，节省 tokens）

**内容要点**:

- 描述 iFlow 目录结构（`00_inbox/`, `10_projects/`, `20_knowledge/`, `90_journal/`）
- 定义整理流程：
  1. 读取 `00_inbox/daily_dump.md` 内容
  2. 按内容语义分类，匹配到对应的 `10_projects/` 子目录
  3. 将内容追加到对应项目的 `work_log.md`（按日期格式）
  4. 识别备忘内容（```备忘 xxx``` 格式），归档到对应项目
  5. 更新 `global_context_today.md`
  6. 清空 `daily_dump.md`（先备份到 `daily_last.md`）
- 定义变更日志格式：在工作目录下维护 `CHANGELOG.md`，每次整理追加一条记录，包含：
  - 日期时间
  - 整理了哪些内容（摘要）
  - 备忘内容放到了哪里
  - 重要整理项（需要用户确认的）
- 定义 Git 操作规范：整理完成后执行 `git add -A && git commit -m "daily organize: YYYY-MM-DD" && git push`
- 定义钉钉通知格式：
  - **备忘类**：简短告知"XX 备忘已归档到 10_projects/XX/work_log.md"
  - **重要整理**：列出整理摘要，问用户"这样整理可以吗？有需要调整的告诉我"
  - **无内容**：不发消息

**工作目录路径**: 使用占位符 `{WORK_DIR}`，在 Skill 中说明"工作目录路径请参考 config.json 中的 allowed_paths 配置，默认为 `~/工作助手/`"

---

## 第二步：更新 AGENTS.md — 添加 iFlow 整理的 Cron 配置说明

**文件**: `workspace/AGENTS.md`

在已有的 "CBT Coach" Cron 配置段落后面，追加 iFlow 整理的 Cron 说明：

- 每天 18:00（北京时间）触发一次整理任务，cron 表达式：`0 18 * * 1-5`
- 任务内容：先用 `read_file` 读取 iflow-organizer Skill，然后按 Skill 中的流程执行整理
- 整理前先检查 `00_inbox/daily_dump.md` 是否有内容，无内容则跳过
- 整理完成后通过 `message` 工具发钉钉消息通知用户
- 同时支持用户在聊天中手动说"帮我整理一下"触发

---

## 第三步：确保工作目录在 allowed_paths 中

**文件**: 用户的 `~/.nanobot/config.json`

需要确认/添加工作目录路径到 `tools.allowedPaths` 数组中，这样 bot 的文件工具和 shell 工具才能访问工作目录。同时 `tools.restrictToWorkspace` 如果为 `true`，也需要把工作目录加进去。

示例配置片段：
```json
{
  "tools": {
    "allowedPaths": ["~/工作助手"]
  }
}
```

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `workspace/skills/iflow-organizer/SKILL.md` | iFlow 整理 Skill 定义 |
| 修改 | `workspace/AGENTS.md` | 追加 iFlow Cron 配置说明 |
| 确认 | `~/.nanobot/config.json` | 确保 allowed_paths 包含工作目录 |

---

## 整理流程示意

```
Cron 18:00 触发
    |
    v
Agent 读取 iflow-organizer Skill
    |
    v
读取 00_inbox/daily_dump.md
    |
    +-- 为空 --> 跳过，不发消息
    |
    +-- 有内容 -->
        |
        v
    备份到 daily_last.md
        |
        v
    按语义分类内容，匹配项目目录
        |
        v
    追加到对应 work_log.md
        |
        v
    识别备忘内容，归档
        |
        v
    更新 global_context_today.md
        |
        v
    清空 daily_dump.md
        |
        v
    追加 CHANGELOG.md
        |
        v
    git add -A && git commit && git push
        |
        v
    通过钉钉发送整理报告
        |
        +-- 备忘类：简短告知存放位置
        +-- 重要整理：展示摘要，等用户确认
```

---

## 注意事项

- **Git 安全**：Skill 中明确限制只允许 `git add`、`git commit`、`git push`，禁止 `git reset`、`git force-push` 等危险操作
- **幂等性**：整理前先备份 `daily_dump.md` 到 `daily_last.md`，防止数据丢失
- **手动触发**：用户在钉钉对话中说"整理"、"帮我整理一下"时，agent 也能识别并执行同样的流程
- **未来扩展**：Skill 中预留说明，后续可以添加生活、学习等不同目录的整理逻辑，每个目录一个独立的 Skill


updateAtTime: 2026/2/27 17:16:39

planId: be68152d-c967-45eb-a75c-c12d0858fd19