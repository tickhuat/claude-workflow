#!/usr/bin/env bash
# init-fresh.sh — strip dogfood examples from a fresh template fork.
#
# WARNING: One-time use. Run this immediately after cloning the template,
# BEFORE writing any of your own specs/plans/ADRs. It is destructive:
# all docs/superpowers/{specs,plans}/*.md and ADR/*.md (except the
# template) will be removed.
#
# Keeps:
#   - .claude/scripts/, .claude/settings.json, .claude/dev-rules.config.yaml
#   - tests/, pyproject.toml, README.md, LICENSE, CLAUDE.md, .gitignore
#   - .github/workflows/ (CI), scripts/init-fresh.sh (this file)
#   - ADR/0000-template.md (template for new ADRs)
#   - docs/doctrine/ (framework rules; ADR 0026)
#
# Removes:
#   - docs/superpowers/specs/*.md (all dogfood specs)
#   - docs/superpowers/plans/*.md (all dogfood plans)
#   - ADR/*.md except 0000-template.md
#   - ADR/README.md (maintainer-only freeze notice; ADR 0026)
#   - .claude/dev-state.json (if present)
#   - .claude/bypass.log (if present)
#   - .claude/bypass.log.old (if present)
#
# Resets:
#   - ADR/_index.json -> []
set -euo pipefail

cd "$(dirname "$0")/.."

# Find a Python >=3.10 to host the project venv. claude-workflow's hook
# entry points (.claude/settings.json) call `.venv/bin/python -m
# claude_workflow.hooks.<name>`, so the venv path is part of the contract.
# PEP 668 makes system-site installs hostile on modern macOS/Linux anyway.
PY=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
            PY="$cmd"
            break
        fi
    fi
done

if [[ -z "$PY" ]]; then
    echo "ERROR: claude-workflow requires Python >=3.10. Install via brew/apt/pyenv and re-run." >&2
    exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
    echo "claude-workflow: creating venv at .venv/ with $PY..."
    "$PY" -m venv .venv
fi

# Ensure framework is installed (editable mode so future upgrades are easy).
echo "claude-workflow: installing framework (.venv/bin/pip install -e .)..."
.venv/bin/pip install -e . --quiet

echo "claude-workflow: stripping dogfood examples..."

# Specs / plans — wildcard delete (these directories only hold dogfood at
# template-fork time; the user hasn't written anything yet).
rm -f docs/superpowers/specs/*.md
rm -f docs/superpowers/plans/*.md

# ADRs 0001 onward (keep 0000-template.md)
for adr in ADR/*.md; do
    base=$(basename "$adr")
    if [[ "$base" != "0000-template.md" ]]; then
        rm -f "$adr"
    fi
done

# ADR/README.md is maintainer-only freeze notice (per ADR 0026); fork users
# don't need it. Doctrine lives in docs/doctrine/ (preserved).
rm -f ADR/README.md

# Reset ADR index
echo '[]' > ADR/_index.json

# Runtime state
rm -f .claude/dev-state.json
rm -f .claude/bypass.log
rm -f .claude/bypass.log.old

# Restore .claude/ baseline from shipped templates. We use cp -Rn so any
# pre-existing user config (rare for a fresh fork, but possible) is
# preserved. BSD cp returns 1 when -n skips a conflict (GNU cp returns 0);
# the partial copy is still correct, so 0 and 1 are both healthy. Any
# other exit code (permissions, missing source, full disk) is a real error.
if [[ -d templates/.claude ]]; then
    echo "claude-workflow: copying templates/.claude/ baseline..."
    cp_rc=0
    cp -Rn templates/.claude/. .claude/ || cp_rc=$?
    case "$cp_rc" in
        0|1) ;;
        *) echo "ERROR: cp failed with rc=$cp_rc" >&2; exit "$cp_rc" ;;
    esac
fi

cat <<'EOF'

Done. Repository is now a clean template.

Next steps:
  1. Open Claude Code in this directory.
  2. Start with: Skill(superpowers:brainstorming)
  3. Edit .claude/dev-rules.config.yaml to customise sensitive paths,
     event keywords, etc., for your project.

EOF
