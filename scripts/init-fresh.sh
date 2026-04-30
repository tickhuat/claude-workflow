#!/usr/bin/env bash
# init-fresh.sh — strip dogfood examples from a fresh template fork.
#
# WARNING: One-time use. Run this immediately after cloning the template,
# BEFORE writing any of your own specs/plans/ADRs. It is destructive:
# any docs/superpowers/{specs,plans}/2026-04-*.md and ADR/[1-9]*.md files
# will be removed.
#
# Keeps:
#   - .claude/scripts/, .claude/settings.json, .claude/dev-rules.config.yaml
#   - tests/, pyproject.toml, README.md, LICENSE, CLAUDE.md, .gitignore
#   - .github/workflows/ (CI), scripts/init-fresh.sh (this file)
#   - ADR/0000-template.md (template for new ADRs)
#
# Removes:
#   - docs/superpowers/specs/2026-04-*.md
#   - docs/superpowers/plans/2026-04-*.md
#   - ADR/*.md except 0000-template.md
#   - .claude/dev-state.json (if present)
#   - .claude/bypass.log (if present)
#
# Resets:
#   - ADR/_index.json -> []
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
