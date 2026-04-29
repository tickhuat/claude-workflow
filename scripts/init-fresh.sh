#!/usr/bin/env bash
# init-fresh.sh — strip dogfood examples from a fresh template fork.
# Keeps: engine (.claude/scripts, lib/, tests/, pyproject.toml, README, LICENSE, CLAUDE.md),
#        ADR template (0000-template.md), and reset _index.json to [].
# Removes: spec/plan markdown under docs/superpowers/, ADRs 0001+, runtime state files.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "claude-workflow: stripping dogfood examples..."

# Specs / plans (dogfood-only patterns)
rm -f docs/superpowers/specs/2026-04-*.md
rm -f docs/superpowers/plans/2026-04-*.md

# ADRs 0001 onward (keep 0000-template.md)
for adr in ADR/*.md; do
    base=$(basename "$adr")
    if [[ "$base" != "0000-template.md" ]]; then
        rm -f "$adr"
    fi
done

# Reset ADR index
echo '[]' > ADR/_index.json

# Runtime state
rm -f .claude/dev-state.json
rm -f .claude/bypass.log

cat <<'EOF'

Done. Repository is now a clean template.

Next steps:
  1. Open Claude Code in this directory.
  2. Start with: Skill(superpowers:brainstorming)
  3. Edit .claude/dev-rules.config.yaml to customise sensitive paths,
     event keywords, etc., for your project.

EOF
