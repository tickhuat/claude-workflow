---
title: Round 4 — framework boundary + multi-mode workflow redesign (Spec 0)
date: 2026-05-09
status: Draft
adrs:
  - 0026-framework-doctrine-separation
  - 0027-mode-model-first-class
  - 0028-bugfix-mode-prototype
  - 0029-version-policy-semver
  - 0030-distribution-pypi-architecture
related_plans: []
related_epic: https://github.com/tickhuat/claude-workflow/issues/8
---

## 1. Purpose

Round 4 的 master spec。對應 [GitHub Epic #8](https://github.com/tickhuat/claude-workflow/issues/8) 與 [docs/PHILOSOPHY.md](../../PHILOSOPHY.md) 的兩個 architectural moves：

- **Move A — Framework / dev-history physical separation**
- **Move B — Multi-mode workflow**

並順帶解掉 PHILOSOPHY 7-criterion v1.0 list 中的第 1、2、4、7 條（framework 分離、多模式、分發升級路徑、backwards-compat policy）。第 3 條（hook contract tests）、第 5 條（CHANGELOG 自動化）、第 6 條（external user）由獨立 issue 追蹤、不在本輪。

本 spec **不直接觸碰 code**。它的產出是 5 條新 ADR（0026–0030）+ 一份 5 phase 的 implementation phasing。每個 phase 各自有獨立 sub-spec / sub-plan 觸 code。

**ADR 落檔時序**：5 條新 ADR（0026–0030）在 Spec 0 通過 user review 後、`writing-plans` skill 呼叫前寫入 `ADR/` 並標 `Accepted`，作為後續所有 plan frontmatter `adrs:` 欄位可引用的目標。**§5 各 phase 描述的是實作工作，不再重複「ADR 落檔」**。

## 2. Non-goals

- 不解 v1.0 criterion #3（hook contract tests with fixtures）— 獨立 issue
- 不實作 CHANGELOG 自動化工具（如 `release-please`）— 本輪只決 SemVer policy，工具留之後
- 不真的把 package 推上 PyPI — 0 external user 階段是純投機（PHILOSOPHY 第 1 條），架構 ready 即可
- 不實作 iterate / chore / hotfix 三個 mode — 第一輪只 prototype `bugfix`，其他 mode 等 bugfix 跑穩後另開 issue
- 不改變 superpowers skill 的呼叫方式（仍用 `Skill(...)` 工具）

## 3. Strategic decisions（5 個 ADR 槽位的核心立場）

### 3.1 ADR 0026 — Framework / dev-history physical separation

**Decision**: 採用 **γ partition + 選項 1 機制**（PHILOSOPHY 命名）。

- 既有 25 個 ADR（0001–0025）**全部歸 dev-history bucket**，原地凍結
- 開新目錄 `docs/doctrine/`，內含 5–8 份 living doctrine docs，由現有 ADR 蒸餾而來
- ADR injection 機制（`on_user_prompt.py:_print_adr_index`）改 source path：`ADR/` → `docs/doctrine/`
- `init-fresh.sh` 對 fork user 刪 `ADR/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`；維護者本地保留全部
- **新框架變更的紀錄規則**：寫 ADR（紀錄事件）+ 同步更新對應 doctrine doc（更新規則）。ADR 仍進 `ADR/` 目錄（會繼續累積，但對 fork user 透明）

**Living doctrine ≠ ADR**：doctrine 描述 STATE（規則本身），ADR 描述 EVENT（在某時點做出的決定）。doctrine 文件**不用 supersede 鏈**，直接 edit；frontmatter 僅 `title` + `last_updated`。

**為什麼 γ 而非 α/β**：
- α（minimal preservation，3–5 個 ADR 留下）丟掉 0001、0017、0020 那些「為什麼長這樣」的脈絡，fork user 與維護者 archeology 都受損
- β（generous preservation，~20 個 ADR 留下）injection token tax 沒降，PHILOSOPHY 識別的根本問題沒解
- γ 在「fork user 清爽」與「維護者完整 archeology」之間取得最佳分離點

**為什麼選項 1（ADR/ 凍結）而非選項 2（rename to history/）/ 選項 4（separate repo）**：
- rename 會破壞所有 internal cross-link（25 個 ADR 互相引用、多份 spec/plan 引用）
- separate repo 的 cross-repo reference 維護痛 + CI 雙倍，0 external user 階段不划算
- 選項 1 的「原地凍結 + injection 改 source + init-fresh strip」三招組合，零連結破壞、零 CI 改動

### 3.2 ADR 0027 — Multi-mode workflow: mode as first-class field

**Decision**: 採用**軸 1 = A（mode 是 enum + per-mode YAML record）**。

- 在 `dev-state.json` schema 加 `mode: str` 欄位（schema v3 migration）
- mode 定義集中在 `dev-rules.config.yaml.modes:`，每個 mode 的 record 結構：

  ```yaml
  modes:
    feature:  # 預設 mode，等同目前的 linear flow
      required_stages: [idle, brainstorming, spec-ready, planning, plan-ready,
                        exec-running, reviewed, done]
      require_spec: true
      require_plan: true
      require_phase_verify: true
      require_review: true
      sensitive_globs_strict: true
  ```

- `lib/modes.py`（新 module）提供 `ModeRegistry`、`get_mode(name) -> ModeConfig`、`current_mode_config(state) -> ModeConfig`
- hook 改成讀 mode record 決定 gating：`pre_skill.py` 看 `required_stages` 是否包含目標；`pre_edit.py` 看 `require_spec` / `require_plan` 是否 true；`pre_bash.py` 看 `sensitive_globs_strict` 是否 true
- Default mode = `feature`（避免 backward break）
- legacy `dev-state.json` 無 `mode` 欄位 → schema v3 migration 自動補 `"mode": "feature"`，比照 ADR 0010/0018 pattern

**為什麼 A 而非 B（純 flags）/ C（hardcoded enum）**：
- B 把 mode 解構成原子 flags，使用者要自行組合 → 落回「靠自律」的老坑
- C 寫死在 Python，違反 PHILOSOPHY 第 5 條 stable extension surface — fork user 加 mode 必須 fork 框架碼
- A 維持 mode 為一級概念，同時把定義放在 fork user 可改的 YAML，最佳平衡

**對齊既有 pattern**：ADR 0007（config 外移）+ ADR 0015（YAML source-of-truth + Python DEFAULTS sync）的 pattern 直接套用，零新機制。

### 3.3 ADR 0028 — bugfix as first prototyped mode + manual skill switch

**Decision**: 採用**選項 α（manual skill）**作為 mode 切換機制；`bugfix` 為第一個落地的非預設 mode。

- 新增 skill `Skill(switch-mode-bugfix)`、`Skill(switch-mode-feature)`
- 切 mode 限制：**只能在 `idle` 或 `done` 狀態切**。半截 spec/plan 切 mode 會造成 state confusion + data-loss，禁止
- 新 skill 同時做兩件事：寫 `state.mode = "bugfix"` + advance 到該 mode 的第一個 stage（feature → `brainstorming`、bugfix → `exec-running`）

**bugfix mode 的 YAML 定義**：

```yaml
modes:
  bugfix:
    required_stages: [idle, exec-running, reviewed, done]
    require_spec: false
    require_plan: false
    require_phase_verify: false
    require_review: true              # 仍要 code review
    sensitive_globs_strict: true      # bugfix on auth/migrations 仍要新 ADR
```

**為什麼 α 而非 β（slash command）/ γ（CLI）/ δ（auto-detect）**：
- δ 是 ADR 0017 已驗證過的失敗 pattern — keyword 自動偵測造成 brainstorm 被卡住
- γ 要求使用者離開 Claude session 跑 CLI，違反 in-session 自動化精神
- β 是過早優化，需要新增 slash command surface；如未來 bugfix mode 高頻使用、`Skill(switch-mode-bugfix)` 字串太煩，再加 slash command 也來得及
- α 重用現有 skill machinery（`pre_skill.py:_try_transition()`、`SKILL_TO_STAGE` 表），實作量最小

**為什麼 bugfix 而非 chore / iterate**（Epic #8 也建議 bugfix）：
- 維護者過去兩週實際踩坑：「想 fix 一個 hook bug 但被強制走 brainstorm → spec → plan → 4-phase verify → review」是高頻情境
- bugfix 跳過 brainstorm/plan/phase-verify 但保留 review = ROI 最高的 mode
- chore 跳得太多（review 也跳）、實際 self-utility 較低；iterate 跟 feature 邊界模糊、留待 bugfix 跑穩後再設計

### 3.4 ADR 0029 — Version policy: SemVer applied immediately, pre-1.0 breaking via MINOR

**Decision**: 從本 round 結束起套用 SemVer。

- Pre-1.0：breaking change → bump MINOR（`0.4.0` → `0.5.0`）
- Post-1.0：breaking change → bump MAJOR + 寫 migration ADR
- 維護 `CHANGELOG.md`，每 release 一段（手寫，自動化工具留之後）
- Round 4 完成時打 git tag `v0.4.0`
- **「breaking」的範圍**：
  - hook contract（hook script 的 stdin/stdout/exit code 約定）
  - `dev-state.json` schema（不含已有的 schema_version migration 機制 — 那本身就是 backwards-compat 設計）
  - `dev-rules.config.yaml` schema 中**已標為 stable 的部分**（見 0030 extension API 切分）
  - `init-fresh.sh` 的 CLI contract
  - `python -m claude_workflow.*` 的 entry point 名稱
- **「非 breaking」**：新增 mode、新增 doctrine、`src/claude_workflow/**/*.py` 內部重構、新增 hook（不改舊 hook）

**為什麼從 v0.4.0 起算**：Round 1–3 已累積三輪重大設計變動，視為 v0.1 / v0.2 / v0.3，Round 4 自然是 v0.4.0。git tag 從本 round 起補打（0.1/0.2/0.3 不回頭補，但 CHANGELOG.md 補一段歷史 summary）。

### 3.5 ADR 0030 — Distribution: PyPI-installable architecture (deferred publish) + extension API contract

**Decision**: 採用**選項 β（PyPI-installable architecture，不發 PyPI）**。

**Repository layout 重構**：

```text
claude-workflow/                       # repo root
  pyproject.toml                       # [project] name = "claude-workflow"
                                       # 含 entry points, optional-dependencies (ADR 0021)
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
      skills.py                        # SKILL_TO_STAGE etc.
      modes.py                         # NEW: ModeRegistry (ADR 0027)
      frontmatter.py
      adr_index.py
  templates/                           # init-fresh.sh 複製來源
    .claude/
      settings.json                    # hook command = python -m claude_workflow.hooks.<name>
      dev-rules.config.yaml            # 含 modes: 段
      skills/                          # framework-shipped skills (cascade-auditing 等)
    docs/doctrine/                     # 5–8 份 living docs (ADR 0026)
  scripts/
    init-fresh.sh                      # 升級為 scaffold（pip install + 複製 templates）
  tests/                               # 不入 package
  ADR/                                 # frozen at 0025; fork user 由 init-fresh 刪
  docs/
    PHILOSOPHY.md
    superpowers/
      specs/                           # frozen for fork user
      plans/                           # frozen for fork user
  CHANGELOG.md                         # NEW (ADR 0029)
  README.md
  LICENSE
```

**Extension API 合約**（PHILOSOPHY 第 5 條 stable extension surface 落地）：

| Surface | Stability | 說明 |
|---|---|---|
| `dev-rules.config.yaml` schema | **Stable** | fork user 編輯預期路徑；schema 變更受 SemVer 約束（0029） |
| `.claude/skills/**/SKILL.md` | **Stable** | fork user 加自訂 skill 的標準位置；命名空間與 hook 整合契約穩定 |
| `docs/doctrine/**/*.md` | **Stable** | fork user 可加自家 doctrine（不會被框架改寫） |
| `src/claude_workflow/**/*.py` | **Internal** | 無 stability guarantee（fork 自負風險）；MAJOR 邊界可大改 |
| `templates/**` 的內容 | **Internal** | 框架預設模板，可隨時更新 |
| Hook entry point 名稱 (`python -m claude_workflow.hooks.<name>`) | **Stable** | 算 hook contract 的一部分；變更需 MAJOR bump |

**為什麼 β 而非 α（template + selective merge）/ γ（PyPI 立刻發）**：
- α 的 `git fetch upstream + git merge` 在實際使用時必撞 conflict（user 改 config，框架也改 config，merge 自動失敗）
- γ 違反 PHILOSOPHY 第 1 條 ship-for-self；0 external user 時推 PyPI 是純投機
- β 把 framework code 跟 user state 物理分離（site-packages vs project），第一個 external user 出現時 30 分鐘就能補發 PyPI

**順便清掉的舊債**：`.claude/scripts/lib/runtime_paths.py`（pre-integration-audit 那輪加的 worktree-path 偵測 hack）在重構後 import 路徑乾淨，可整支移除。

**為什麼把 distribution 跟 extension API 包在同一條 ADR**：extension API 的本質就是「distribution boundary 的合約」— stable surface 是 distribute 出去的東西，internal 是不 distribute 的東西。拆開反而會出現 cross-reference 痛點。

## 4. 既有 24 ADR（連 0023 superseded 共 25）migration plan

對應 Epic #8 acceptance: 「Migration plan for current 24 ADRs documented」。

### 4.1 規則

1. 全部 25 個 ADR 檔**原地不動**，不改檔名、不改 frontmatter、不重編號 — internal cross-link 不破
2. 新增 [`ADR/README.md`](../../../ADR/README.md) 說明：「本目錄為 dev-history bucket（凍結於 0025）。framework doctrine 請看 `docs/doctrine/`。新框架變更會繼續寫到此目錄並同步更新 doctrine」
3. ADR injection 機制（`on_user_prompt.py:_print_adr_index`）改 source path：`ADR/` → `docs/doctrine/`（注入 doctrine summary，不再注入 ADR title 列表）
4. `init-fresh.sh` 對 fork user 刪 `ADR/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`
5. 既有 ADR 的 frontmatter `related_specs` / `related_plans` 不動 — 連到也凍結了的 specs/plans，archeology 完整可用

### 4.2 doctrine docs 蒸餾對應表

預定 6 份 doctrine（每份 ~150–400 行，因主題複雜度而異）：

| Doctrine doc | 蒸餾來源 ADR | 主旨 |
|---|---|---|
| `state-machine.md` | 0001, 0006, 0010, 0013, 0017, 0018, 0020 | dev-state.json 結構、stage transition、schema versioning、event-flag 語意 |
| `hook-contract.md` | 0001, 0004, 0005, 0012 | 各 hook 的 stdin/stdout/exit code 約定、namespace stripping |
| `config-model.md` | 0007, 0011, 0015, 0016, 0025 | YAML source-of-truth、DEFAULTS sync、ADR id 來源、injection filter rules |
| `dependency-policy.md` | 0003, 0014, 0019, 0021, 0022 | 唯一外部 runtime dep（PyYAML + pathspec）、PEP 621 optional-deps、cross-platform notify |
| `distribution-and-versioning.md` | 0008, 0009 + 本輪 0029, 0030 | rename、license、template→PyPI 演進、SemVer policy、extension API |
| `mode-model.md` | 本輪新增（0027, 0028） | mode 概念、YAML schema、切換規則、bugfix prototype |

**doctrine frontmatter（最簡）**：

```yaml
---
title: State machine
last_updated: 2026-05-XX
---
```

無 `id`、`status`、`supersedes` — 它是 living doc，直接 edit 不留 supersede 鏈。

## 5. Implementation phasing

對應 Epic #8 acceptance: 「Plan(s) created for execution」+「at least one mode prototyped end-to-end」。

實作切成 5 phase，順序有 critical-path 依賴：

### 5.1 Phase 1 — Move A 落地

- 寫 6 份 doctrine docs（從既有 25 個 ADR 蒸餾）
- 改 ADR injection（`on_user_prompt.py`）source path
- 更新 `init-fresh.sh`：對 fork user 加刪 `ADR/`、`docs/superpowers/specs|plans/` 步驟
- 新增 `ADR/README.md`（凍結說明）
- ADR 0026 落檔（Accepted）

依賴：無。**Phase 1 先做**因為它是最小依賴 phase。

### 5.2 Phase 2 — Package 重構

- `.claude/scripts/` → `src/claude_workflow/`
- 改 `.claude/settings.json` 的所有 hook command 為 `python -m claude_workflow.hooks.<name>`
- `pyproject.toml` 加 `[project]` entry point；確認 `pip install -e .` 跑得起來
- `init-fresh.sh` 升級為 scaffold（先跑 `pip install -e .`、再從 `templates/` 複製檔案）
- 移除 `lib/runtime_paths.py`（重構後 import 路徑乾淨，hack 不再需要）
- ADR 0030 落檔（Accepted）

依賴：Phase 1 完成。**循序**因為兩 phase 都動 `init-fresh.sh`，平行做會 merge conflict。

### 5.3 Phase 3 — Mode 機制

- `dev-state.json` schema v2 → v3 migration（補 `mode: "feature"`）
- 新增 `lib/modes.py` (`ModeRegistry`, `ModeConfig`, `current_mode_config()`)
- `dev-rules.config.yaml` 加 `modes:` 段（含 `feature` 完整定義）
- `lib/config.py` DEFAULTS 同步加 `modes:` 對應結構（ADR 0015 pattern）
- hook 改成讀 mode record 決定 gating：
  - `pre_skill.py`: `required_stages` check
  - `pre_edit.py`: `require_spec` / `require_plan` check
  - `pre_bash.py`: `sensitive_globs_strict` check
- ADR 0027 落檔（Accepted）

依賴：Phase 2 完成。**循序**因為 `lib/modes.py` 要進新 package 結構，先重構 layout 再加 module 較乾淨。

### 5.4 Phase 4 — bugfix mode prototype

- 新增 skills：`switch-mode-bugfix`、`switch-mode-feature`（在 `templates/.claude/skills/` 落檔）
- `lib/skills.py` `SKILL_TO_STAGE` 加新 skill mapping
- `dev-rules.config.yaml.modes:` 加 `bugfix` 完整定義
- enforce 「mid-flow 不可切 mode」：`switch-mode-*` skill 的 transition 條件限定 `idle` / `done`
- end-to-end test：模擬一條 bugfix 流程跑通（switch-mode → exec-running → review → done）
- ADR 0028 落檔（Accepted）

依賴：Phase 3 完成。

### 5.5 Phase 5 — 版本與文件收尾

- 寫 `CHANGELOG.md`（v0.4.0 段含整個 Round 4；v0.1–0.3 寫一段歷史 summary）
- git tag `v0.4.0`
- `docs/doctrine/distribution-and-versioning.md` 補上 SemVer policy 內容
- README 更新 extension API 章節（指向 `docs/doctrine/`）
- ADR 0029 落檔（Accepted）

依賴：Phase 4 完成。**版本 tag 在 mode prototype 跑通才打**（v0.4.0 = 含 Round 4 全部成果）。

## 6. Acceptance criteria

對應 Epic #8 checklist：

- [ ] **Spec 0 written, reviewed, committed** — 本檔
- [ ] **Foundational ADRs accepted (5 條 0026–0030)** — 各 phase 完成時對應 ADR 寫入並 Accepted
- [ ] **Migration plan for current 24 ADRs documented** — §4
- [ ] **Plan(s) created for execution** — 進 writing-plans skill 後產出
- [ ] **At least one mode prototyped end-to-end** — Phase 4 完成

對應 PHILOSOPHY v1.0 criterion:

- [x] #1 Framework code 與 dev-history 物理可分離 → 0026 + Phase 1
- [x] #2 Workflow 多 mode 支援不同 change scope → 0027 + 0028 + Phase 3, 4
- [ ] #3 Hook contract fixture-based tests — 獨立 issue，本輪不解
- [x] #4 Distribution mechanism supports upgrades → 0030 + Phase 2
- [ ] #5 SemVer + CHANGELOG + release tags — 0029 解 SemVer 與 CHANGELOG 政策；release 自動化工具留之後
- [ ] #6 README + onboarding tested by external user — 本輪非範圍
- [x] #7 Backwards-compat policy documented → 0029 的「breaking 範圍」+ 0030 的 extension API 表

## 7. Open questions / risks

### 7.1 Risk: doctrine 寫作量被低估

6 份 doctrine 從 25 個 ADR 蒸餾，每份 150–400 行。Phase 1 預計工作量是 ~6 個 doc 寫作 session，可能落在 2–4 天。如果延宕，後面 phase 會 cascade。

**Mitigation**: Phase 1 先寫**最薄的 1 份**（例如 `dependency-policy.md`，只整合 5 個 ADR、且都是純技術選擇）作為 spike，校準寫作速度後再決定是否加人或拆 phase。

### 7.2 Risk: Phase 2 重構後 hook 在 worktree 中失效

ADR pre-integration-audit 那輪剛加的 `runtime_paths.py` 是在處理「scripts 路徑可能在 worktree 或 main 兩處」的問題。改用 `python -m claude_workflow.hooks.<name>` 後，理論上 import 走 site-packages，與 worktree 無關 — 但需要實際在 worktree 中跑通才確認。

**Mitigation**: Phase 2 的 verify command 包含「在 `.worktrees/` 子目錄 invoke 一個 skill，確認 hook 正常觸發」的 live verification（呼應 PHILOSOPHY lesson 3）。

### 7.3 Risk: bugfix mode 的 sensitive_globs 仍 strict 是否會擋實際 bugfix

bugfix mode 仍維持 `sensitive_globs_strict: true`，意味著修 `auth*` / `migrations/**` / `*.config.*` 還是要新 ADR。但很多真實的 bugfix 就是修 auth 漏洞或 schema 問題，加 ADR ceremony 等同 bugfix mode 沒少多少摩擦。

**Mitigation**: Phase 4 的 end-to-end test 跑一條 sensitive bugfix（例如修 `lib/auth.py` 的假設性 bug），確認實際摩擦水位。如果太重，回頭加 `sensitive_globs_strict: warn-once`（呼應 ADR 0017 pattern）作為 bugfix mode 的選項。

### 7.4 Open: 新框架變更的「ADR 一定要寫嗎」

§3.1 說「新框架變更 → 寫 ADR + 更新 doctrine」。但對於 framework 內部 refactor（例如 `lib/state.py` 內部重構），是否每次都要 ADR？可能太重。

**留待 doctrine 寫作時決定**：`config-model.md` 或 `state-machine.md` 內可能會立下「ADR 寫作 trigger criteria」（例如：跨 module 介面變更 → ADR；同 module 內重構 → 不必）。本 spec 不預先決定。

## 8. Cross-references

- [Epic #8](https://github.com/tickhuat/claude-workflow/issues/8) — 上層追蹤 issue
- [docs/PHILOSOPHY.md](../../PHILOSOPHY.md) — 北極星與 7 條 v1.0 criterion
- [ADR 0009](../../../ADR/0009-github-template-distribution.md) — 既有 distribution 決策（被本輪 0030 演進）
- [ADR 0010](../../../ADR/0010-state-schema-version.md) — schema_version migration pattern（0027 schema v3 沿用）
- [ADR 0015](../../../ADR/0015-defaults-yaml-sync.md) — YAML source-of-truth pattern（0027 modes 沿用）
- [ADR 0017](../../../ADR/0017-event-flag-prompt-scope.md) — keyword-based detection 失敗教訓（0028 拒絕 auto-detect 的依據）
- [ADR 0021](../../../ADR/0021-pep621-optional-dependencies.md) — PEP 621 dep 結構（0030 package layout 沿用）
