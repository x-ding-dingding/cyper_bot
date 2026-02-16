### 为 nanobot 添加会话摘要机制 ###
当会话消息数超过阈值时，自动裁剪旧消息并在后台异步生成摘要，摘要结果注入 system prompt 供后续对话使用。采用 Letta 的 Static Buffer 模式（fire-and-forget），不阻塞当前对话。


## 设计概述

### 核心思路

当 session 消息数超过 `message_buffer_limit`（默认 50）时：
1. **立即裁剪**：只保留最近 `message_buffer_min`（默认 10）条消息
2. **后台摘要**：把被裁剪的消息异步发给 LLM 生成摘要
3. **存储摘要**：摘要结果写入 session 的 `summary` 字段并持久化
4. **注入上下文**：下次构建消息时，把摘要作为 system prompt 的一部分注入

新消息到来时不等摘要完成，直接用裁剪后的消息列表 + 上一次已有的摘要继续对话。

### 数据流

```
用户消息到来
    │
    ▼
session.get_history()
    │
    ├─ 消息数 <= 50 → 正常返回全部消息
    │
    └─ 消息数 > 50 → 裁剪，只保留最近 10 条
                      │
                      ├─ 立即返回裁剪后的消息（不阻塞）
                      │
                      └─ 后台 asyncio.Task：
                           把被裁剪的消息 + 旧摘要 → 发给 LLM
                           → 生成新摘要 → 写入 session.summary
                           → save session

构建 system prompt 时：
    如果 session.summary 存在 → 注入到 system prompt 中
```

---

## 具体改动

### 1. 新建 `nanobot/agent/summarizer.py`

**职责**：后台摘要服务，接收被裁剪的消息，调用 LLM 生成摘要。

**关键设计**：

- `Summarizer` 类，持有 `LLMProvider` 引用
- `summarize_async(evicted_messages, previous_summary, callback)` 方法：
  - 将被裁剪的消息格式化为文本（`role: content` 格式，简单拼接）
  - 如果有旧摘要，拼在前面作为上下文
  - 构造 3 条消息发给 LLM：
    - system: 摘要 prompt（见下方）
    - user: 格式化后的对话记录
  - 调用 `self.provider.chat(messages=..., tools=None, model=self.model)` 获取摘要
  - 通过 callback 回写结果
- `fire_and_forget(session, evicted_messages)` 方法：
  - 创建 `asyncio.Task` 执行摘要
  - 完成后调用 `session.update_summary(result)` + `session_manager.save(session)`
  - 异常时 log warning，不影响主流程

**摘要 Prompt**（从 Letta 的 `SHORTER_SUMMARY_PROMPT` 改编，去掉 Letta 绑定内容）：

```
The following messages are being evicted from the conversation window.
Write a concise summary that captures what happened in these messages.

This summary will be provided as background context for future conversations. Include:

1. **What happened**: The conversations, tasks, and exchanges that took place.
2. **Important details**: Specific names, data, or facts that were discussed.
3. **Ongoing context**: Any unfinished tasks, pending questions, or commitments made.

If there is a previous summary provided, incorporate it to maintain continuity
and avoid losing track of long-term context.

Keep your summary under 200 words. Only output the summary.
```

### 2. 修改 `nanobot/session/manager.py`

**Session 类增加字段**：

- `summary: str = ""`  — 存储当前摘要文本
- `summary_in_progress: bool = False` — 标记是否正在摘要（防止重复触发）

**修改 `get_history` 方法**：

当前逻辑是简单截取最近 N 条。改为：
- 如果消息数 <= `message_buffer_limit`，正常返回
- 如果消息数 > `message_buffer_limit`：
  - 计算被裁剪的消息列表 `evicted = self.messages[:-message_buffer_min]`
  - 裁剪 `self.messages = self.messages[-message_buffer_min:]`
  - 返回 `(裁剪后的消息, evicted)` — 通过新方法 `trim_if_needed()` 实现

新增 `trim_if_needed(limit, min_keep)` 方法：
- 返回 `(需要摘要的消息列表, 是否发生了裁剪)`
- 裁剪时确保切割点在 `user` 消息边界上（不切断一轮对话）

新增 `update_summary(text)` 方法：
- 更新 `self.summary = text`
- 设置 `self.summary_in_progress = False`

**修改持久化格式**：

在 JSONL 的 metadata 行中增加 `summary` 字段：
```json
{"_type": "metadata", "created_at": "...", "summary": "之前的对话摘要..."}
```

`_load` 方法读取时恢复 `summary` 字段。`save` 方法写入时包含 `summary`。

### 3. 修改 `nanobot/agent/context.py`

**修改 `build_messages` 方法**：

增加 `summary: str | None = None` 参数。如果 summary 不为空，在 system prompt 末尾追加：

```
## Conversation Summary

The following is a summary of earlier conversation that is no longer
in the message history:

{summary}
```

### 4. 修改 `nanobot/agent/loop.py`

**`__init__` 中**：
- 新增 `self.summarizer = Summarizer(provider=provider, model=model)` 初始化

**`_process_message` 中**：

在 `session.get_history()` 调用后、`build_messages` 调用前，插入裁剪逻辑：

```python
# 裁剪检查
evicted, did_trim = session.trim_if_needed(
    limit=self.message_buffer_limit,
    min_keep=self.message_buffer_min,
)
if did_trim and not session.summary_in_progress:
    session.summary_in_progress = True
    self.summarizer.fire_and_forget(
        session=session,
        session_manager=self.sessions,
        evicted_messages=evicted,
        previous_summary=session.summary,
    )

# 构建消息时传入摘要
messages = self.context.build_messages(
    history=session.get_history(),
    current_message=msg.content,
    summary=session.summary,  # 新增参数
    ...
)
```

同样修改 `_process_system_message` 中的对应逻辑。

### 5. 修改 `nanobot/config/schema.py`

**`AgentDefaults` 类增加**：

```python
message_buffer_limit: int = 50      # 触发裁剪的消息数阈值
message_buffer_min: int = 10        # 裁剪后保留的最少消息数
summary_model: str | None = None    # 摘要用的模型（默认用主模型）
```

**`AgentLoop.__init__` 中**从配置读取这些值。

---

## 并发安全设计

### 问题：摘要进行中，新消息来了怎么办？

**方案：不等待，直接用旧摘要 + 裁剪后的消息继续对话。**

具体保障：

1. `session.summary_in_progress` 标记防止重复触发摘要
2. 裁剪是**同步立即完成**的（只是 list 切片），不阻塞
3. 后台摘要 Task 完成后才更新 `session.summary` 并 save
4. 如果摘要还没完成，新消息来时用的是**上一次的旧摘要**（可能为空），这是可接受的——最多丢失一批被裁剪消息的摘要，但这些消息仍然保存在 session 文件中
5. nanobot 的 `AgentLoop.run()` 是单线程 `asyncio` 循环（`await self.bus.consume_inbound()`），消息是**串行处理**的，所以不存在真正的并发写入问题。后台 Task 只写 `session.summary` 字段，主流程只读它

### 时序示例

```
T1: 用户消息 → 消息数=55 → 裁剪保留10条 → 启动后台摘要 → 用旧摘要回复
T2: 用户消息 → 消息数=12 → 不裁剪 → summary_in_progress=True，不重复触发 → 用旧摘要回复
T3: 后台摘要完成 → session.summary 更新 → summary_in_progress=False → save
T4: 用户消息 → 消息数=14 → 不裁剪 → 用新摘要回复
```

---

## 文件改动清单

| 文件 | 操作 | 改动量 |
|------|------|--------|
| `nanobot/agent/summarizer.py` | 新建 | ~80 行 |
| `nanobot/session/manager.py` | 修改 | ~40 行新增 |
| `nanobot/agent/context.py` | 修改 | ~10 行新增 |
| `nanobot/agent/loop.py` | 修改 | ~20 行新增 |
| `nanobot/config/schema.py` | 修改 | ~3 行新增 |

总计约 **150 行新代码**，无需引入新依赖。


updateAtTime: 2026/2/16 17:34:12

planId: dc5657be-be13-49ff-93fa-752e74f2ee32