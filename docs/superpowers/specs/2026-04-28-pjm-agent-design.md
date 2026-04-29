# PJM Agent — Design Spec

**Date:** 2026-04-28
**Status:** Phase 1 (MVP) — design approved, ready for implementation plan
**Scope:** 整體骨架 + Phase 1 MVP 完整設計。Phase 2/3 僅列出範圍，細節留待後續 spec。

---

## 1. Vision

PJM Agent 是一個個人/小團隊的專案管理助手。它接 Slack、ClickUp、GitLab、Google Drive，把所有專案相關的對話、會議記錄、commit、task 統一進 DB，讓使用者透過 Slack DM 跟它對話、查詢、自動化 task 開立。

**核心定位：** Agent 的工作不是「在腦袋裡記住所有東西」，而是「把資訊整理進 DB → 從 DB 撈出回答」。DB 是 working memory，LLM 是聰明的 DB 操作員 + 資訊整理器。

---

## 2. 整體骨架（跨所有 phase）

### 2.1 模組清單

| Module | 角色 | Phase |
|---|---|---|
| `agent-runner` | LLM 大腦 + HTTP webhook 接口 | Phase 1 |
| `slack-mcp` | Slack listener + MCP server（讀 + 寫 + 搜尋訊息） | Phase 1 |
| `gdrive-mcp` | Google Drive 監聽 + 讀取會議記錄 | Phase 2 |
| `clickup-mcp` | ClickUp task CRUD | Phase 2 |
| `gitlab-mcp` | GitLab repo / commit / issue / MR 讀取 | Phase 3 |
| Postgres + pgvector | 共用資料層 | Phase 1 |

### 2.2 Phase 切分

- **Phase 1 (MVP)** — Slack ingestion + DM Q&A。最小可動閉環，驗證核心架構。本 spec 詳述。
- **Phase 2** — Killer flow：會議記錄 → ClickUp task。加 `gdrive-mcp` + `clickup-mcp`。
- **Phase 3** — 專案上下文：加 `gitlab-mcp`。
- **Phase 4+** — 自動化 status report、stand-up 摘要、文件生成等。

### 2.3 整體架構決策（影響所有 phase）

| 決策 | 選擇 | 理由 |
|---|---|---|
| Agent 編排 | Single agent + tool modules | 多 agent 對此規模 over-engineered；專業 prompt 透過 tool description 達成 |
| 模組 runtime | 獨立 MCP servers（HTTP/SSE transport） | 為未來擴充 / 維護 / 獨立部署留空間 |
| DB | Postgres + pgvector | 結構化 + 語意搜尋一站搞定 |
| 事件觸發 | HTTP webhook（MCP server → agent-runner） | 簡單、低延遲，未來可升級至 queue |
| 互動介面 | Slack DM only（agent 監聽群組但只回 DM） | 使用者已在 Slack；不增加 UI 工程負擔 |
| 語言 | Python 3.12+ | MCP / Anthropic / Slack / Postgres 生態系最完整 |
| Repo | Monorepo（uv workspace） | Dependency 版本管理簡單，CI 一致 |
| 部署 | Docker Compose | Phase 1 跑在家裡/辦公室常開機；不需 public IP |

---

## 3. Phase 1 MVP — 範圍

**做：**
- Slack 群組訊息自動 ingest 到 DB（含 embedding）
- 使用者 DM bot → agent 透過語意搜尋 / 結構化查詢 / 摘要回答
- 對話 state 保留（每個 user 一條長期 conversation）

**不做（Phase 1 故意排除）：**
- 群組 @mention（agent 結論只走 DM）
- Agent 主動播報（無觸發來源；Phase 2 才有 GDrive 事件）
- ClickUp / GitLab / GDrive 整合
- Message edits / deletes / reactions 處理
- 多 user 對話狀態（Phase 1 預期單一 user）
- Distributed tracing、metrics dashboard、自動 E2E test

---

## 4. Phase 1 — Architecture

```
                                 Slack Workspace
                                       │
                                  Events API (Socket Mode)
                                       │
        ┌──────────────────────────────┴───────────────────────────────┐
        │                Local Machine / Server (Docker Compose)        │
        │                                                                │
        │   ┌─────────────────────┐   webhook   ┌────────────────────┐  │
        │   │ slack-mcp           │ ───────────▶│ agent-runner       │  │
        │   │  - listener thread  │             │  - HTTP server     │  │
        │   │  - MCP HTTP server  │ ◀───────────│  - MCP client      │  │
        │   │                     │  MCP calls  │  - Anthropic SDK   │  │
        │   └──────────┬──────────┘             └─────────┬──────────┘  │
        │              │                                  │              │
        │              └──────────────┬───────────────────┘              │
        │                             ▼                                  │
        │              ┌─────────────────────────────┐                   │
        │              │ Postgres + pgvector         │                   │
        │              │ tables: messages, channels, │                   │
        │              │ users, conversations,       │                   │
        │              │ conversation_turns          │                   │
        │              └─────────────────────────────┘                   │
        └────────────────────────────────────────────────────────────────┘
                                       │
                                  Anthropic API (Claude Sonnet 4.6)
                                  Voyage AI (voyage-3 embeddings)
```

三個 process：`postgres` / `slack-mcp` / `agent-runner`，由 docker-compose 編排。

---

## 5. Phase 1 — Components

### 5.1 slack-mcp

**單一 Slack 進出口。**

**Internal — 背景 listener（slack-bolt SDK）：**
- 啟動時連 Slack Events API（Socket Mode）
- Phase 1 訂閱：`message.channels`, `message.groups`, `message.im`
- （`app_mention` Phase 1 不訂閱，因為 Phase 1 排除群組 @mention 處理；Phase 2 視需要再加）
- 收到 message → INSERT 到 `messages`（含 embedding）
- 若 channel.type == 'im' 且非 bot 自己發的 → POST `agent-runner:8000/events/slack-dm`

**External — MCP tools（透過 HTTP/SSE 給 agent-runner 呼叫）：**

| Tool | Description |
|---|---|
| `send_dm(user_id, text)` | 送 DM 給指定 user。`user_id` 由 agent-runner 在 system prompt 帶入當前對話 user。 |
| `search_messages(query, channel?, time_range?, limit=10)` | 語意 + 結構化搜尋。回 ranked messages。 |
| `get_recent_messages(channel?, limit=20)` | 最近 N 則訊息。 |
| `get_thread(channel_id, thread_ts)` | 撈整串 thread。 |

**Owns：** `users`, `channels`, `messages` tables。

### 5.2 agent-runner

**LLM 大腦 + 事件處理器。**

**HTTP endpoints：**
- `POST /events/slack-dm` — body: `{user_id, text, ts, channel_id}`
- `GET /healthz` — health check

**事件處理流程：**
1. 收 webhook → 從 DB 讀 conversation state（依 user_id）
2. 沒有 conversation 就 INSERT 新的
3. 組 prompt：system + 過去 ≤20 turns + 新訊息
4. `anthropic.messages.create(model=ENV.AGENT_MODEL, tools=[...slack-mcp tools])`
5. Tool use loop（max 10 iterations）— Claude 自行決定 tool calls
6. 最終文字 → 呼叫 `slack-mcp.send_dm()`
7. INSERT 新一輪 turns 到 `conversation_turns`

**Owns：** `conversations`, `conversation_turns` tables；system prompt；Anthropic API key。

### 5.3 Postgres + pgvector

- `pgvector/pgvector:pg16` Docker image
- 啟用 `vector` extension
- 各 module 各自有 Alembic migration 目錄，跑同一個 DB（共用 default schema）
- 每個 process 自己的 connection pool（asyncpg）

---

## 6. Phase 1 — Data Flow

### 6.1 Flow A — 被動 Ingestion（永遠在跑）

```
Slack channel msg
  → Slack Events API
  → slack-mcp listener thread
  → upsert user / channel
  → 算 embedding（Voyage API）
  → INSERT messages (..., embedding)
  → 結束（不通知 agent）
```

無 LLM 介入。Voyage API call 是唯一外部呼叫。

### 6.2 Flow B — DM 對話（agent 處理）

```
User DM bot
  → Slack Events API
  → slack-mcp listener
    → INSERT message（同 Flow A）
    → 偵測 channel.type=='im' 且 user!=BOT_USER_ID
    → POST agent-runner /events/slack-dm
  → agent-runner 收 webhook
    → load conversation state
    → 組 prompt
    → anthropic.messages.create(tools=[...])
    → loop: tool_use → tool_result
       (e.g., search_messages → Voyage embed query → vector search → 回 results)
    → 最終文字 → send_dm tool_use
    → slack-mcp.send_dm() → Slack chat.postMessage
    → INSERT conversation_turns
```

Tool use loop 可能多輪（Claude 自己決定要 search 幾次）。

---

## 7. Phase 1 — DB Schema

### 7.1 slack-mcp 擁有

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,           -- Slack user id
    real_name       TEXT,
    display_name    TEXT,
    is_bot          BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE channels (
    id              TEXT PRIMARY KEY,           -- Slack channel id
    name            TEXT,                       -- nullable for DMs
    type            TEXT NOT NULL,              -- 'channel' | 'im' | 'group' | 'mpim'
    is_monitored    BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_ts        TEXT NOT NULL,
    channel_id      TEXT NOT NULL REFERENCES channels(id),
    user_id         TEXT NOT NULL REFERENCES users(id),
    text            TEXT NOT NULL,
    thread_ts       TEXT,                       -- nullable
    is_dm_to_bot    BOOLEAN NOT NULL DEFAULT FALSE,
    embedding       VECTOR(1024),               -- Voyage voyage-3
    raw_payload     JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, slack_ts)
);

CREATE INDEX messages_embedding_hnsw ON messages
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX messages_channel_ts ON messages (channel_id, slack_ts DESC);
CREATE INDEX messages_user ON messages (user_id);
CREATE INDEX messages_created_at ON messages (created_at DESC);
CREATE INDEX messages_text_fts ON messages
    USING GIN (to_tsvector('simple', text));
```

### 7.2 agent-runner 擁有

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL REFERENCES users(id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX conversations_user_active ON conversations (user_id, last_active_at DESC);

CREATE TABLE conversation_turns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    turn_index      INTEGER NOT NULL,
    role            TEXT NOT NULL,              -- 'user' | 'assistant' | 'tool_result'
    content         JSONB NOT NULL,             -- Anthropic message format
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX conversation_turns_idx ON conversation_turns (conversation_id, turn_index);
```

### 7.3 Schema 設計決策

- `messages.id` 用 UUID 方便 join；`(channel_id, slack_ts)` 是邏輯 unique key（防 Slack 重送）
- `raw_payload` 保留完整 Slack event，未來新增欄位不用 backfill
- `conversation_turns.content` 存 Anthropic message format JSON（含 tool_use / tool_result 結構），下次 prompt 直接餵
- Embedding 用 Voyage `voyage-3`（1024 dim, Anthropic 官方推薦）。可改 OpenAI `text-embedding-3-small`（1536 dim）

---

## 8. Phase 1 — Slack 整合細節

### 8.1 Slack App 設定

1. `api.slack.com/apps` → Create New App → From scratch
2. 啟用 **Socket Mode** → 取得 App-Level Token (`xapp-...`)
3. Bot Scopes：
   - `channels:history`, `channels:read`
   - `groups:history`, `groups:read`
   - `im:history`, `im:read`, `im:write`
   - `chat:write`
   - `users:read`
4. Event Subscriptions：`message.channels`, `message.groups`, `message.im`
5. Install to Workspace → 取得 Bot User OAuth Token (`xoxb-...`)
6. `/invite @bot` 進要 monitor 的 channels

### 8.2 為什麼 Socket Mode

不用 public URL、不用 ngrok / nginx / SSL、不用驗 signing secret。Local / 家裡 server / Docker 都直接跑。未來 cloud production 想換 HTTP Events，slack-bolt 改 init 參數即可。

### 8.3 Edge cases

| Case | 處理 |
|---|---|
| Slack 重連 / 重送 event | `UNIQUE (channel_id, slack_ts)` + `ON CONFLICT DO NOTHING` |
| Bot 自己發的訊息 | listener 偵測 `user_id == BOT_USER_ID` 跳過 |
| Message edits / deletes | Phase 1 忽略（保留 raw_payload，未來 backfill） |
| Slack rate limit | slack-bolt SDK 內建 retry |
| Threaded messages | 存 `thread_ts`，Phase 1 當一般訊息處理 |

### 8.4 Secrets（env vars，不進版控）

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
POSTGRES_URL=postgresql://pjm:pjm@postgres:5432/pjm
AGENT_RUNNER_URL=http://agent-runner:8000
BOT_USER_ID=U...
AGENT_MODEL=claude-sonnet-4-6
```

---

## 9. Phase 1 — Agent Prompt Strategy

### 9.1 System prompt 大綱

實作時迭代具體文字，spec 只定大綱：

1. **Identity** — 你是 [user] 的專案管理助手
2. **Knowledge sources** — 你能查詢 Slack 訊息（語意搜尋 + 結構化搜尋）
3. **Tool usage rules：**
   - 「之前討論過 X 嗎」→ `search_messages`
   - 「最近 Y channel 在說什麼」→ `get_recent_messages`
   - 引用 Slack 訊息要附 link / timestamp
   - 找不到資料就誠實說
4. **Reply style** — 簡潔、條列、繁中
5. **Reply mechanism** — 永遠透過 `send_dm` 回覆

### 9.2 Conversation 管理

- **每個 user 一條長期 conversation**（不按 session 切）
- **Sliding window**：每次 prompt 帶最近 ≤20 turns
- **Older turns** Phase 1 直接丟（YAGNI；Phase 2+ 視需求做摘要）
- **新對話 vs 延續** Phase 1 不分

### 9.3 模型 & 性能

- 預設 `claude-sonnet-4-6`，env var `AGENT_MODEL` 可切
- **Prompt caching 啟用**：system prompt + tool defs 標記為 cacheable（5-min TTL）
- **Tool use loop max iterations = 10**：超過強制中止
- **Streaming 不開**：MVP 等完整回覆再送
- **Empty / 失敗 response fallback**：DM「sorry, 我這邊出了點問題，再試一次？」

---

## 10. Phase 1 — Error Handling

### 10.1 slack-mcp listener

| 失敗 | 處理 |
|---|---|
| DB 寫入失敗 | log + 不 ack event（讓 Slack 重送） |
| Embedding API 失敗 | retry 3 次 (exp backoff)；都失敗就 INSERT 但 `embedding=NULL`（背景補做留 Phase 2） |
| Slack websocket 斷線 | slack-bolt 自動重連，event 重送，UNIQUE 防重複 |
| Webhook POST agent 失敗 | retry 3 次；都失敗 log warning，事件丟失（Phase 2 升級成 queue） |

### 10.2 agent-runner

| 失敗 | 處理 |
|---|---|
| Anthropic rate limit / overload | SDK 內建 retry；最終失敗 → DM「忙線中，請稍後再試」 |
| Anthropic API timeout (>60s) | 中止 → DM「處理太久了，能不能換個問法」 |
| MCP tool call 失敗 | 把 error 餵回 Claude，由 Claude 決定 |
| Tool loop > 10 輪 | 強制中止 + DM「我繞迷路了，請換個問法」 |
| `send_dm` 失敗 | log error；無法通知（Slack 不通），等下次互動 |

### 10.3 通用

- 結構化 logging（structlog，JSON），每筆含 `conversation_id` / `message_ts`
- Crash recovery：docker-compose `restart: on-failure`
- 無 distributed tracing / metrics dashboard（Phase 1 排除）

---

## 11. Phase 1 — Testing Strategy

| 層 | 工具 | 範圍 |
|---|---|---|
| Unit | pytest | 純邏輯：解析 Slack payload、組 prompt、parse tool result。不打外部 API/DB |
| Integration (DB) | pytest + testcontainers | slack-mcp ↔ Postgres：給假 event，驗 DB 狀態；vector search 排序 |
| Integration (MCP) | pytest + mock Anthropic | agent-runner ↔ slack-mcp via MCP；驗 tool call → response |
| Manual E2E | 真 Slack workspace + 真 Anthropic | release 前 smoke test。自動化留 Phase 2+ |

---

## 12. Phase 1 — Repo 結構 & Deployment

### 12.1 Monorepo 結構（uv workspace）

```
PJM_Agent/
├── pyproject.toml              # workspace root
├── docker-compose.yml
├── .env.example
├── README.md
│
├── packages/
│   ├── core/                   # 共用 lib（DB conn、logging、config）
│   │   ├── pyproject.toml
│   │   └── pjm_core/
│   │
│   ├── slack-mcp/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── alembic/
│   │   ├── pjm_slack_mcp/
│   │   │   ├── listener.py     # background Slack listener
│   │   │   ├── server.py       # MCP HTTP server
│   │   │   ├── tools.py        # tool 實作
│   │   │   └── db.py
│   │   └── tests/
│   │
│   └── agent-runner/
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── alembic/
│       ├── pjm_agent/
│       │   ├── http_server.py  # webhook 接口
│       │   ├── orchestrator.py # tool use loop
│       │   ├── prompts.py
│       │   └── db.py
│       └── tests/
│
├── docs/
│   └── superpowers/specs/
│
└── docker/
    └── postgres-init.sql       # CREATE EXTENSION vector
```

### 12.2 docker-compose.yml（三 service）

- **postgres** — `pgvector/pgvector:pg16`，volume persist，healthcheck
- **slack-mcp** — `depends_on: postgres healthy`，`restart: on-failure`，內部 expose port 9000（MCP HTTP/SSE，僅 docker network 內可達，不對外）
- **agent-runner** — `depends_on: postgres + slack-mcp`，內部 listen port 8000（slack-mcp 透過 docker network `http://agent-runner:8000` 戳 webhook；要不要 mapping 到 host 看開發需求），`restart: on-failure`

### 12.3 MCP transport

`agent-runner` 透過 **HTTP/SSE** 連 slack-mcp（不用 stdio，因為兩個獨立 container）。slack-mcp 起 MCP HTTP server on port 9000，agent-runner 連 `http://slack-mcp:9000/mcp`。

### 12.4 部署目標

- **Phase 1 預設**：家裡/辦公室常開機（NUC / mini PC / NAS docker）
- **不需要**公開 IP（Socket Mode 自己連 Slack）
- **未來可選**：Cloud VPS（DO / Hetzner）月 $5-10
- **不適用**：serverless（Slack listener 是 long-lived process）

---

## 13. Future Phases — 範圍預告

### Phase 2 — 會議記錄 → ClickUp Task（killer flow）
新增：
- `gdrive-mcp`（poll/webhook 新 doc，read content）
- `clickup-mcp`（list/create/update task）
- 主動 webhook：新會議記錄 → agent 分析 → DM 提案 task → user confirm → ClickUp 開 task
- Slack interactive components（buttons / modal）做 confirmation UI

### Phase 3 — GitLab 整合（專案上下文）
新增：
- `gitlab-mcp`（read repo / commits / issues / MRs；webhook on push/MR）
- Agent 能跨資料源回答：「這個 task 的 code 改在哪」「最近一次 deploy 討論的痛點是什麼」

### Phase 4+ — 自動化
- 每日 stand-up 摘要
- 自動 status report
- 文件生成（架構文件、API doc）
- Deadline / 進度監控

---

## 14. Decisions Deferred / Open Questions

下列先採預設，未來可調整：

| 項目 | 預設 | 重新審視時機 |
|---|---|---|
| Embedding 模型 | Voyage `voyage-3` | 若 Voyage 出問題或想省錢，考慮 OpenAI |
| 預設 LLM 模型 | `claude-sonnet-4-6` | 視成本 / 品質實測調整 |
| Sliding window 大小 | 20 turns | 視 prompt 長度 / 品質實測調整 |
| Tool loop max iterations | 10 | 觀察是否常被觸發 |
| Channel ingestion 策略 | 預設全部 monitor | 若噪音太多，加白名單機制 |
| Older turns 處理 | 直接丟 | 若使用者抱怨「健忘」，做摘要壓縮 |
| 部署位置 | 家裡 / 常開機 | 若協作者多了，搬 Cloud VPS |

---

## 15. 完成定義（Definition of Done — Phase 1）

Phase 1 視為完成當且僅當：

- [ ] `docker-compose up` 一鍵啟動三個 service，全部 healthy
- [ ] Bot 可加入 Slack workspace，邀進 channel 後新訊息自動進 DB（含 embedding）
- [ ] DM bot 能觸發 agent，且 agent 能透過 `search_messages` 找到相關歷史對話並回覆
- [ ] Conversation state 跨 agent-runner 重啟後仍保留
- [ ] 所有 unit + integration tests 通過
- [ ] 手動 E2E smoke test pass：ingestion + DM Q&A 至少 5 種典型 query
- [ ] README 有 setup 流程（Slack app 建立 → env vars → docker-compose up）
