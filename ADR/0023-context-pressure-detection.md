---
id: "0023"
title: Context pressure detection — suggest /compact at natural breaks above threshold
status: Accepted
date: 2026-05-04
related_specs:
  - docs/superpowers/specs/2026-05-04-context-pressure-design.md
related_plans: []
supersedes: null
---

## Context

Claude Code 預設只在 context 接近 100% 時才自動 compact —— 這是 safety net，使用者體感是「卡了」才反應。理想情況是**提前**在自然斷點（task 完成、phase verified、commit 後）先 compact，避免在敏感工作流中段被打斷。

關鍵限制：**Claude 自己不能呼叫 `/compact`**。`/compact` 是 Claude Code CLI 的 slash command，由 harness 處理；它不是 skill 或 tool，Claude 在對話中無法 invoke。所以本 feature 的本質是：

> **detector + suggester** —— hook 偵測「context 過大 + 在自然斷點」，輸出建議；user 看到後手動跑 `/compact`，或 Claude 看到 state flag 後**主動提醒** user。

設計 surface：
- stderr `[INFO]` 訊息（user / Claude 都看到）
- `state.event_flags.compact_recommended: true` flag（Claude 主動提醒的依據）
- 兩者協同：user 不會錯過，Claude 也會 nudge

## Decision

新增一套 context pressure detection 機制：

1. **新 lib `lib/context_pressure.py`** —— pure helpers + 1 mutator helper：
   ```python
   def find_transcript() -> Path | None
   def estimate_tokens(transcript_path: Path, chars_per_token: float = 3.5) -> int
   def is_natural_break(stage: str, *, after_verify_pass: bool = False,
                        after_commit: bool = False) -> bool
   def compute_pressure(window_tokens: int,
                        chars_per_token: float = 3.5
                        ) -> tuple[int, float, Path | None]   # (tokens, pct, transcript)
   def maybe_alert_and_update_flag(s, cfg: dict, *,
                                    after_verify_pass: bool = False,
                                    after_commit: bool = False) -> bool
   ```

2. **Token 估算法（char count / chars_per_token）**：
   - 讀取 transcript file size（bytes ≈ chars for ASCII-heavy content）
   - 除以 `chars_per_token = 3.5`（English + code 混合的合理估算）
   - **誤差 ±15-20%**（image tokens 偏低、純 code 偏高）—— 這是 trade-off，換零依賴和 < 5ms 執行
   - 不引入 tiktoken / Anthropic API（成本不值得）

3. **Transcript 路徑解析**：
   - filesystem query：`~/.claude/projects/<dash-encoded-cwd>/*.jsonl` glob，取最新 mtime
   - 不依賴 hook event payload（PostToolUse 不一定帶 `transcript_path`）
   - 找不到時 gracefully return None，hook 跳過 pressure check

4. **Config schema 新增（nested object）**：
   ```yaml
   context_pressure:
     enabled: true
     window_tokens: 200000      # Claude 4.x context window
     threshold_pct: 60          # over this → recommend compact
     chars_per_token: 3.5       # estimation factor
   ```
   - DEFAULTS in `lib/config.py` 同步 yaml（per ADR 0015）
   - 新 test `test_config_context_pressure_defaults_synced`

5. **State schema 加 flag**（不需要 schema_version v3）：
   - `INITIAL_STATE.event_flags.compact_recommended: False`
   - 既有 v2 state file 載入時，`State.load()` 的 `merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}` 會自動補 default `False`
   - 向前相容、無 migration

6. **Hook 整合 — post_skill + post_bash**：
   - 在「自然斷點」事件後 call `compute_pressure()`
   - 若 `is_over_threshold=True` AND `event_flags.compact_recommended` 仍為 False：
     - 印 stderr `[INFO by dev-rules] context ~62% (~125K/200K). Natural break detected (stage=phase-2-verified). Recommend /compact before next major step.`
     - 設 `s.data["event_flags"]["compact_recommended"] = True` + save
   - 若 flag 已是 True → 不重複印（warn-once）

7. **自然斷點定義**：
   - ✅ stage in (`idle`, `phase-N-verified`, `all-phases-verified`, `reviewed`, `done`)
   - ✅ post_bash 偵測到 git commit 成功
   - ✅ post_skill 偵測到 Agent VERIFY-PASS
   - ❌ stage in (`exec-running` mid-phase, `phase-N-done` 未 verify)
   - 不算的情況下 hook 仍計算 pressure，但**不**設 flag、不印 stderr

8. **特例：on_user_prompt 不 reset `compact_recommended`**：
   - ADR 0017 規定 `event_flags` 每個 prompt 開頭 reset 為 false
   - 但 `compact_recommended` 是「context 量級」的狀態，**跨 prompt 仍有效**直到 user 真的 /compact
   - on_user_prompt.py 改成 reset 「除了 compact_recommended 之外」的 flags
   - 加註解明確標示為 ADR 0017 的例外，連結到本 ADR

9. **Flag 何時清**：
   - User 跑 `/compact` 後，transcript size 大幅縮減（compact summary 取代原 transcript）
   - 下次 hook fire 時 `compute_pressure()` 看到 pct 已掉回 threshold 以下
   - hook 偵測「flag is True but pressure dropped」→ 清 flag + 印 `[INFO] context cleared (~25%)`，避免 stale

10. **Claude 行為層 nudge（CLAUDE.md）**：
    - `## LLM behavior` 加一條：「If `event_flags.compact_recommended` is true, tell user 'context is at ~X%, recommend /compact before continuing.' Don't run further heavy work in this turn.」

## Consequences

- **Positive:**
  - 提前 compact 提示，減少 100% 卡死 → 自動 compact 的 jarring 體驗
  - state flag + stderr 雙管，user 跟 Claude 都不會錯過
  - 自然斷點偵測利用既有 state machine，無需新 stage
  - char count 估算零依賴、跑得快（< 5ms hook overhead）
  - config 可關（`enabled: false`），對 init-fresh template user 友善

- **Negative:**
  - char count 對 image-heavy session 偏低（~1.5K tokens / image 看不到）→ user 可能晚點才看到警告 → mitigation: threshold 設 60%（其實是粗估的 60%，留 20% margin）
  - Cross-platform（Windows）`~/.claude/projects/` 路徑可能不同 —— 但 ADR 0019 已記錄 repo 假設 POSIX 環境，本 ADR 跟隨
  - on_user_prompt 對單一 flag 例外處理 = 跟 ADR 0017 局部不一致 → mitigation: code comment + link 本 ADR

- **Follow-up:**
  - 若估算誤差太大，可加 hybrid mode（每 N 次 hook 用 Anthropic API `messages.count_tokens` 校準一次）
  - status line 顯示 context % 是 future work（本 ADR 不含）
  - Windows 支援需另一個 ADR
