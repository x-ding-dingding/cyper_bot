### 为 nanobot 添加会话摘要机制 ###
当会话上下文 token 数达到 context_window 的 60% 时，后台异步生成摘要。摘要未完成期间继续使用旧的完整上下文，完成后将摘要注入 system prompt 并裁剪旧消息。


## 设计概述

### 核心思路

每次 LLM 调用返回后，从 `response.usage["prompt_tokens"]` 获取实际 token 消耗。当 prompt_tokens 达到 `context_window * summarize_threshold`（默认 60% of 32768 = 19660 tokens）时：

1. **不立即裁剪** -- 当前请求和后续请求继续使用完整的旧上下文
2. **后台摘要** -- 启动 asyncio.Task，将当前历史消息发给 LLM 生成摘要
3. **摘要完成后替换** -- 摘要写入 `session.summary`，同时裁剪旧消息只保留最近 `message_buffer_min` 条
4. **后续对话** -- 使用裁剪后的消息 + 摘要（注入 system prompt）继续对话

### 数据流

```
LLM 响应返回，获取 prompt_tokens
    |
    +-- prompt_tokens < 60% context_window --> 正常继续
    |
    +-- prompt_tokens >= 60% context_window 且 summary_in_progress=False
            |
            +-- 标记 summary_in_progress = True
            +-- 启动后台 Task:
            |     1. 将 session.messages + 旧 summary 发给 LLM 生成新摘要
            |     2. 摘要完成后:
            |        - session.summary = 新摘要
            |        - session.messages 裁剪为最近 message_buffer_min 条
            |        - session.summary_in_progress = False
            |        - save session
            |
            +-- 当前请求及后续请求: 继续使用完整旧上下文 + 旧 summary（如有）

下次构建 system prompt 时:
    如果 session.summary 存在 --> 注入到 system prompt 中
```

---

## 具体改动

### 1. 新建 `nanobot/agent/summarizer.py`

**职责**: 后台摘要服务

- `Summarizer` 类，持有 `LLMProvider` 引用和 model 名称
- `fire_and_forget(session, session_manager, messages_snapshot, previous_summary, min_keep)` 方法:
  - 创建 `asyncio.Task`
  - 内部调用 `_do_summarize()`:
    - 将 messages_snapshot 格式化为 `role: content` 文本
    - 如有旧摘要，拼在前面
    - 构造 system + user 消息调用 `self.provider.chat()`
    - 完成后: `session.summary = result`，裁剪 `session.messages` 保留最近 `min_keep` 条，`session.summary_in_progress = False`，调用 `session_manager.save(session)`
  - 异常时 log warning，设置 `summary_in_progress = False`，不影响主流程

**摘要 Prompt**（改编自 Letta 的 SHORTER_SUMMARY_PROMPT）:

```
The following messages are being evicted from the conversation window.
Write a concise summary that captures what happened in these messages.

This summary will be provided as background context for future conversations. Include:

1. **What happened**: The conversations, tasks, and exchanges that took place.
2. **Important details**: Specific names, data, or facts that were discussed.
3. **Ongoing context**: Any unfinished tasks, pending questions, or commitments made.

If there is a previous summary provided, incorporate it to maintain continuity
and avoid losing track of long-term context.

Keep your summary under 500 words. Only output the summary.
```

### 2. 修改 `nanobot/session/manager.py`

**Session 类增加字段**:

- `summary: str = ""` -- 当前摘要文本
- `summary_in_progress: bool = False` -- 是否正在摘要（防止重复触发，不持久化）

**修改持久化格式**: metadata 行增加 `"summary"` 字段，`_load` 和 `save` 方法对应读写。

### 3. 修改 `nanobot/agent/context.py`

**修改 `build_messages` 方法**: 增加 `summary: str | None = None` 参数。如果 summary 不为空，在 system prompt 末尾追加:

```
## Conversation Summary

The following is a summary of earlier conversation that is no longer
in the message history:

{summary}
```

### 4. 修改 `nanobot/agent/loop.py`

**`__init__` 中**:
- 新增 `self.summarizer = Summarizer(provider=provider, model=model)`
- 从配置读取 `context_window`（默认 32768）、`summarize_threshold`（默认 0.6）、`message_buffer_min`（默认 10）

**`_process_message` 中**:

- `build_messages` 调用时传入 `summary=session.summary`
- LLM 调用返回后（agent loop 结束），检查最后一次 `response.usage.get("prompt_tokens", 0)`:
  - 如果 `prompt_tokens >= context_window * summarize_threshold` 且 `not session.summary_in_progress`:
    - 设置 `session.summary_in_progress = True`
    - 调用 `self.summarizer.fire_and_forget(session, self.sessions, session.messages.copy(), session.summary, self.message_buffer_min)`
- 同样修改 `_process_system_message` 中的对应逻辑

### 5. 修改 `nanobot/config/schema.py`

**`AgentDefaults` 类增加**:

- `context_window: int = 32768` -- 上下文窗口大小（tokens）
- `summarize_threshold: float = 0.6` -- 触发摘要的 token 占比
- `message_buffer_min: int = 10` -- 摘要完成后保留的最少消息数
- `summary_model: str | None = None` -- 摘要用的模型（默认用主模型）

---

## 并发安全设计

### 摘要进行中，新消息来了怎么办？

**不裁剪，不阻塞，继续使用完整旧上下文。**

1. `summary_in_progress = True` 防止重复触发
2. 后台 Task 完成后才执行裁剪 + 更新 summary + save
3. 摘要期间新消息正常追加到 `session.messages`，使用完整历史 + 旧 summary 回复
4. nanobot 的 AgentLoop 是单线程 asyncio 循环，消息串行处理，后台 Task 只在 await 点切换，不存在真正的并发写入

### 时序示例

```
T1: 用户消息 -> LLM 返回 prompt_tokens=20000 (>60%) -> 启动后台摘要 -> 正常回复
T2: 用户消息 -> summary_in_progress=True -> 不触发新摘要 -> 用完整历史+旧summary回复
T3: 后台摘要完成 -> session.summary更新 -> messages裁剪为最近10条 -> save -> summary_in_progress=False
T4: 用户消息 -> 用裁剪后的10条消息 + 新summary回复
```

### 边界情况: 摘要完成时 messages 已经又增长了

后台 Task 裁剪时操作的是 `session.messages` 的实际引用（同一个 list），裁剪逻辑为 `session.messages = session.messages[-min_keep:]`，此时会保留摘要期间新增的消息（因为它们在列表末尾）。

---

## 文件改动清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `nanobot/agent/summarizer.py` | 新建 | ~90 行 |
| `nanobot/session/manager.py` | 修改 | ~20 行新增 |
| `nanobot/agent/context.py` | 修改 | ~10 行新增 |
| `nanobot/agent/loop.py` | 修改 | ~25 行新增 |
| `nanobot/config/schema.py` | 修改 | ~4 行新增 |

总计约 **150 行新代码**，无需引入新依赖。


updateAtTime: 2026/2/17 13:55:23

planId: 21e06aee-4b20-4713-9690-37b9c4696741