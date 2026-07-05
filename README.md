# Feishu Bot ↔ 本地 LLM Agent

飞书 bot 收到用户消息 → 转给 OpenAI 兼容协议 LLM（默认走阿里云百炼的
DashScope）→ 把回复发回飞书。**无 agent 框架、无工具调用、无多媒体**，
代码尽量短。

## 目录结构

```
feishu-bot/
├── main.py            # WS 入口 + 事件分发
├── feishu.py          # 消息解析（text、@ 提及）+ reply 封装
├── agent.py           # httpx 调 OpenAI 兼容 /chat/completions
├── session.py         # 内存版多轮会话（按 user 隔离）
├── config.py          # stdlib 解析 .env
├── send_card_to_user.py  # 发送卡片消息
├── JohnnyTao.card     # 卡片模板
├── pyproject.toml
├── .env.example       # 环境变量模板
└── .gitignore
```

## 跑通步骤

### 1. 配置环境变量

```bash
# 复制环境变量模板
 cp .env.example .env

# 编辑 .env 填入你的配置
```

### 2. 启动 bot

```bash
# 用项目自带的 venv
.venv/bin/python main.py
```

看到 `starting feishu ws client, model=qwen3.5-flash` 就说明 WS 已经连上
飞书了。

### 3. 在飞书开放平台配置

打开 [飞书开放平台](https://open.feishu.cn/) → 你的应用 → 左侧菜单：

1. **应用能力 → 机器人**：开启「机器人能力」。
2. **事件订阅**：
   - 订阅方式选 **「使用长连接接收事件」**（WebSocket，不用配公网回调）
   - 添加事件 `im.message.receive_v1`（接收消息 v2.0）
3. **权限管理**：开通以下 scope（搜索即可）
   - `im:message` — 获取与发送消息
   - `im:message:send_as_bot` — 以应用身份发消息
   - `im:message.group_at_msg` — 接收群聊中 @ 机器人 的消息（可选，开了更稳）
   - `im:message.p2p_msg` — 接收私聊消息（可选）
   - `im:message:readonly` — 读取消息内容
4. 保存后**创建版本并发布**（自定义机器人也要发布才能用）。
5. 在飞书里搜你 bot 的名字，开个私聊发条消息试试。

### 4. 行为约定

- **私聊**：用户发的所有 text 消息都会回复。
- **群聊**：只回复 @bot 的 text 消息；@ 前缀会被剥掉再喂给 LLM。
- **多轮对话**：按 `user_open_id`（私聊）/ `chat_id+user_open_id`（群聊）
  隔离，内存里保留最近 `MAX_HISTORY_TURNS`（默认 20）轮。
- **非 text 消息**（图片/文件/语音/卡片等）直接忽略。
- **回复长度**：超过 3500 字符会截断并加 `…(回复过长，已截断)`。

## 切到「真正本地」的 LLM

`agent.py` 用的是 OpenAI 兼容协议，所以切换 model 不用改代码，只改
`.env` 即可：

```env
# 切到 Ollama（假设本机跑着 Ollama 并下载了 qwen2.5:7b）
DASHSCOPE_BASE_URL=http://localhost:11434/v1
DASHSCOPE_API_KEY=ollama            # Ollama 不校验 key，填什么都行
DASHSCOPE_MODEL=qwen2.5:7b

# 切到 LM Studio（默认端口 1234）
DASHSCOPE_BASE_URL=http://localhost:1234/v1
DASHSCOPE_API_KEY=lm-studio
DASHSCOPE_MODEL=your-loaded-model-id
```

> 💡 现在 `.env` 里变量名带 `DASHSCOPE_` 是历史原因（最初想接百炼），
> 切到本地时 base_url/key/model 复用同一组就行，名字叫啥不影响调用。

## 调参

`config.py` 暴露了几个可调项（也支持用同名环境变量覆盖 `.env` 默认值）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SYSTEM_PROMPT` | 中文友好助手 | 写在 system message 里 |
| `MAX_HISTORY_TURNS` | `20` | 每个 session 保留多少轮对话 |
| `LLM_TIMEOUT_SECONDS` | `60` | 调 LLM 的 HTTP 超时 |

## 排错

- **`Missing required env var: APP_ID`** → `.env` 没找到，看一眼项目根目录。
- **飞书回调一直不进来** → 99% 是事件订阅没开 `im.message.receive_v1`，
  或者 app 没发布。
- **`LLM returned 401`** → `DASHSCOPE_API_KEY` 不对；切本地时填什么都行。
- **`LLM returned 404`** → base_url 拼出来路径不对；切到本地要确认服务
  监听的端口和模型名都对得上。
- **群消息 bot 不回** → 确认消息里确实 @ 了 bot（不是 @ 别人），并且
  `im:message.group_at_msg` 权限开了。
