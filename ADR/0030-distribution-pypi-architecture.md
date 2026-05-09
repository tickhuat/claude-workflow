---
id: "0030"
title: Distribution — PyPI-installable architecture (deferred publish) + extension API contract
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_plans: []
supersedes: null
---

## Context

PHILOSOPHY.md v1.0 criterion #4：「Distribution mechanism supports upgrades, not just clone-and-fork」。[ADR 0009](0009-github-template-distribution.md) 採 GitHub template + `init-fresh.sh`，但 fork user 沒有 upgrade path（git merge upstream 必撞 conflict）。同時，PHILOSOPHY 第 5 條要求 stable extension surface — 但目前哪些是 stable / 哪些是 internal 沒明文。詳見 [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md) §3.5。

## Decision

採用 **PyPI-installable architecture，但暫不發 PyPI**（Spec 0 選項 β）：

### 1. Repository layout 重構

```text
claude-workflow/                       # repo root
  pyproject.toml                       # [project] entry points, optional-deps (ADR 0021)
  src/claude_workflow/                 # installable package
    __init__.py
    hooks/
      pre_skill.py
      post_skill.py
      pre_edit.py
      pre_bash.py
      post_bash.py
      post_read.py
      on_user_prompt.py
    lib/
      state.py
      config.py
      skills.py
      modes.py                         # NEW (ADR 0027)
      frontmatter.py
      adr_index.py
  templates/                           # init-fresh.sh 複製來源
    .claude/
      settings.json                    # hook command = python -m claude_workflow.hooks.<name>
      dev-rules.config.yaml            # 含 modes: 段
      skills/                          # framework-shipped skills
    docs/doctrine/                     # 5–8 份 living docs (ADR 0026)
  scripts/
    init-fresh.sh                      # 升級為 scaffold（pip install + 複製 templates）
  tests/                               # 不入 package
  ADR/                                 # frozen at 0025; fork user 由 init-fresh 刪
  docs/
    PHILOSOPHY.md
    superpowers/specs|plans/           # frozen for fork user
  CHANGELOG.md                         # NEW (ADR 0029)
  README.md
  LICENSE
```

### 2. Hook entry point 全面改用 `python -m`

`.claude/settings.json` 內所有 hook command 從 `python .claude/scripts/<name>.py` 改為 `python -m claude_workflow.hooks.<name>`。fork user 跑 `pip install -e .` 後 entry point 走 site-packages，不依賴專案內路徑。**順便清掉 `lib/runtime_paths.py`**（pre-integration-audit 那輪加的 worktree-path 偵測 hack）。

### 3. `init-fresh.sh` 升級為 scaffold

從「刪 dogfood examples」升級為：
1. `pip install -e .`（讓 hook entry point 可達）
2. 複製 `templates/.claude/`、`templates/docs/doctrine/` 到 user repo
3. 刪 `ADR/`、`docs/superpowers/{specs,plans}/`（[ADR 0026](0026-framework-doctrine-separation.md)）
4. 初始化空的 `dev-state.json`

### 4. PyPI 不發布

0 external user 階段推 PyPI 違反 PHILOSOPHY 第 1 條 ship-for-self。第一個 external user 出現時，補發 PyPI 是 30 分鐘 `twine upload` 的事，不需要重構。本 round 只做架構 ready。

### 5. Extension API 合約（PHILOSOPHY 第 5 條落地）

| Surface | Stability | 說明 |
|---|---|---|
| `dev-rules.config.yaml` schema | **Stable** | fork user 編輯預期路徑；schema 變更受 SemVer 約束（[ADR 0029](0029-version-policy-semver.md)） |
| `.claude/skills/**/SKILL.md` | **Stable** | fork user 加自訂 skill 的標準位置；命名空間 + hook 整合契約穩定 |
| `docs/doctrine/**/*.md` | **Stable** | fork user 可加自家 doctrine（不被框架改寫） |
| Hook entry point 名稱 (`python -m claude_workflow.hooks.<name>`) | **Stable** | hook contract 一部分；變更需 MAJOR bump |
| `src/claude_workflow/**/*.py` | **Internal** | 無 stability guarantee（fork 自負風險）；MAJOR 邊界可大改 |
| `templates/**` 內容 | **Internal** | 框架預設模板，可隨時更新 |

### 6. 為什麼合併 distribution + extension API 為單一 ADR

extension API 的本質就是「distribution boundary 的合約」— stable surface 是 distribute 出去的，internal 是不 distribute 的。拆開反而出現 cross-reference 痛點。

## Consequences

- **Positive**:
  - framework code 跟 user state 物理分離（site-packages vs project）→ upgrade 走 `pip install -U`，無 git merge conflict
  - hook entry point 變成穩定 API surface（hook contract 落地）
  - extension API 合約明文化，fork user 知道改什麼安全
  - `lib/runtime_paths.py` 可整支移除（架構升級的副作用）
- **Negative**:
  - 重構工作量中等（移檔、改 settings.json、調 init-fresh.sh）。Spec 0 §7.2 列為 risk，verify 包含 worktree live test。
  - fork user 需先跑 `pip install -e .` 才能用，比純 clone 多一步。Mitigation：`init-fresh.sh` 自動跑此步。
- **Follow-up**:
  - Phase 2 落地（package 重構、entry point 改名、init-fresh 升級）
  - 第一個 external user 出現時開新 ADR 評估 PyPI 發布
  - 未來考慮加 `claude-workflow upgrade` CLI 簡化升級流程（不在本輪）
