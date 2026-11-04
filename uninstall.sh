#!/usr/bin/env bash
# Remove the agent-worktree command link, the skill links and its Claude Code settings entries.
# Your worktrees in ~/worktrees are left alone: finish them with `agent-worktree done` first.
set -euo pipefail
BIN="${AGENT_WORKTREE_BIN_DIR:-$HOME/.local/bin}"
ROOT="${AGENT_WORKTREE_ROOT:-$HOME/worktrees}"
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

[ -L "$BIN/agent-worktree" ] && rm "$BIN/agent-worktree" && echo "removed $BIN/agent-worktree"
for d in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "$HOME/.agents/skills"; do
  [ -L "$d/agent-worktree" ] && rm "$d/agent-worktree" && echo "removed $d/agent-worktree"
done
if [ -f "$SETTINGS" ] && command -v jq >/dev/null; then
  tmp=$(mktemp)
  jq --arg d "$ROOT" '(if .permissions.additionalDirectories then .permissions.additionalDirectories -= [$d] else . end)
    | (if .sandbox.excludedCommands then .sandbox.excludedCommands -= ["agent-worktree *"] else . end)' "$SETTINGS" > "$tmp"
  mv "$tmp" "$SETTINGS"
  echo "removed agent-worktree entries from $SETTINGS"
fi
echo "left $ROOT as it is"
