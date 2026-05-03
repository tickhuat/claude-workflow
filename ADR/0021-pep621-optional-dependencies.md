---
id: "0021"
title: PEP 621 [project.optional-dependencies] for dev deps; CI installs via pip install -e ".[dev]"
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-dx-bucket-spec-2a-design.md
related_plans: []
supersedes: null
---

## Context

`pyproject.toml` 目前只有 runtime dependencies（`PyYAML`, `pathspec`），沒有 dev / test dependencies 的宣告。

實際結果：
- README 教學寫 `python3 -m pip install --user "PyYAML>=6.0" pytest` —— **手抓清單**，與 runtime deps 重複又少了 `pathspec`
- `.github/workflows/test.yml` 寫 `python -m pip install pyyaml pathspec pytest` —— **第三份清單**
- Round 1 第一次 PR (#1) CI 實際踩到這個：runtime 加了 `pathspec` 但忘了改 workflow，CI 因此整批失敗
- 任何新增 dev 依賴（如 ruff、coverage）都要手動三處同步

這是**典型的「一個事實源被分散到多個地方」**問題，違反 DRY。Python 標準解法已存在：[PEP 621](https://peps.python.org/pep-0621/) 的 `[project.optional-dependencies]`。

## Decision

採用 **PEP 621 optional-dependencies**，把 dev 依賴集中宣告，CI 和 README 都從 `pyproject.toml` 安裝：

1. **`pyproject.toml`** 新增 `[project.optional-dependencies]`：

   ```toml
   [project.optional-dependencies]
   dev = [
       "pytest>=7.0",
   ]
   ```

   暫時只放 `pytest`；未來新增（ruff、coverage、mypy）就加進這裡，**不必動 CI 和 README**。

2. **`.github/workflows/test.yml`** 改用 editable install + extras：

   ```yaml
   - name: Install dependencies
     run: |
       python -m pip install --upgrade pip
       python -m pip install -e ".[dev]"
   ```

   一行命令同時拉 runtime + dev deps，自動跟 `pyproject.toml` 對齊。

3. **README.md** 安裝段也改：

   ```bash
   python3 -m pip install -e ".[dev]"
   python3 -m pytest tests/ -q
   ```

4. **不引入 `requirements*.txt`**：PEP 621 已是標準，setuptools 68+ 完整支援；增加 requirements.txt 反而是「兩個事實源」回頭路。

5. **不加 lock file（如 `requirements-lock.txt` / `uv.lock`）**：本 repo 是 dev tooling，不是 deployable service，不需要 reproducible builds 等級的 pinning。版本下限（`>=6.0`、`>=0.12`）已足夠。

## Consequences

- **Positive:** dev deps 單一事實源；新增 dev 工具只需動 `pyproject.toml`；CI 跟 local 100% 一致；README 安裝指令更短
- **Negative:** 用戶第一次 install 必須在 repo 根（因為 `-e .`）；對 `gh repo create --template` 後的人需要 `cd my-project && pip install -e ".[dev]"`，比舊流程多一個步驟（但更可靠）
- **Follow-up:** 未來引入 ruff/coverage/mypy 時直接加進 `dev` extras，不用再寫 ADR
