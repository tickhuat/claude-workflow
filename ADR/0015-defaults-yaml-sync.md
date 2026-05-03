---
id: "0015"
title: Sync lib/config.py DEFAULTS with shipped dev-rules.config.yaml; add consistency test
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-review-fixes-round1-design.md
related_plans: []
supersedes: null
---

## Context

Code review 發現 [`lib/config.py` 的 `DEFAULTS`](.claude/scripts/lib/config.py#L13-L32) 與 commit 進倉的 [`.claude/dev-rules.config.yaml`](.claude/dev-rules.config.yaml) **內容已 diverge**。實測比對 `global_whitelist`：

| 來源 | 條目數 | 多出的條目 |
|---|---|---|
| `DEFAULTS`（程式碼） | 10 | — |
| 倉內 yaml（dogfood） | 14 | `*.yml`, `*.yaml`, `.github/**`, `scripts/**` |

差異來自 commit `08d0462`（"ci: opt into Node.js 24 + whitelist .github/scripts in dev-rules"）—— 當時只改了 yaml、沒同步改 DEFAULTS。

實際後果：
- **新使用者跑 `init-fresh.sh` 後**：yaml 仍保留（`init-fresh.sh` 不刪 yaml），所以正常路徑沒事
- **「沒帶 yaml」的安裝路徑**（例如別的 fork、或 yaml 被誤刪）：DEFAULTS 接管，行為與 dogfood 不同 —— `.github/workflows/*.yml` 不在白名單，CI 改動會被 stage gate 擋
- **更深的問題**：DEFAULTS 應該是「shipped 預設」的 source-of-truth，現在它 lag 在後，README / docs 引用 DEFAULTS 行為當保證會誤導

## Decision

採「**shipped yaml 是 source-of-truth、DEFAULTS 同步它**」原則：

1. **手動同步**：把 yaml 內容**完整反映**進 `DEFAULTS`，包含所有四項：`global_whitelist`、`sensitive_globs`、`event_keywords`、`auto_advance_phase`、`commit_deviation_keyword`。同步後兩者**逐欄相等**
2. **加 consistency test**：`tests/scripts/test_config.py` 新增測試
   ```python
   def test_defaults_match_shipped_yaml():
       """DEFAULTS must match the shipped .claude/dev-rules.config.yaml exactly."""
       repo_root = Path(__file__).resolve().parents[2]
       shipped = yaml.safe_load((repo_root / ".claude" / "dev-rules.config.yaml").read_text())
       for key, value in shipped.items():
           assert DEFAULTS[key] == value, f"DEFAULTS[{key!r}] diverged from shipped yaml"
   ```
   未來 yaml 改動不同步 DEFAULTS → CI 會掛 → 強制兩者保持同步
3. **不改 yaml**：yaml 是現行 dogfood 環境的事實狀態，使用者依賴它，不要動

## Consequences

- **Positive:** 「沒 yaml 也能跑」與「dogfood 環境」行為一致；test 強制未來不再 diverge；README 引用 DEFAULTS 不再誤導
- **Negative:** 多一個必須同步的點（但 test 會擋），約束未來修改 yaml 時必須同時改 DEFAULTS
- **Follow-up:** 未來若 DEFAULTS 與 yaml 又出現故意差異（例如 yaml 加 dogfood-only 條目），ADR 必須明寫「故意 diverge」，並在 test 加 exclusion list
