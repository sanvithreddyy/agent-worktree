#!/usr/bin/env bash
# Install agent-worktree: link the command, install the skill for Claude Code and Codex, and
# (after asking) let Claude Code's sandbox use it. Safe to re-run. --yes skips the question.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
BIN="${AGENT_WORKTREE_BIN_DIR:-$HOME/.local/bin}"
ROOT="${AGENT_WORKTREE_ROOT:-$HOME/worktrees}"
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
YES=0; [ "${1:-}" = "--yes" ] && YES=1

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v git >/dev/null || { echo "git is required"; exit 1; }

echo "Command -> $BIN"
mkdir -p "$BIN" "$ROOT"
chmod +x "$REPO/bin/agent-worktree"
ln -sfn "$REPO/bin/agent-worktree" "$BIN/agent-worktree"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "  note: add $BIN to your PATH";; esac

echo "Skill -> Claude Code and Codex"
for d in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "$HOME/.agents/skills"; do
  mkdir -p "$d" && ln -sfn "$REPO/skills/agent-worktree" "$d/agent-worktree" && echo "  linked $d/agent-worktree"
done

echo "Claude Code sandbox"
if ! command -v jq >/dev/null; then
  echo "  skipped (needs jq). If you use Claude Code's sandbox, add \"$ROOT\" to permissions.additionalDirectories"
  echo "  and \"agent-worktree *\" to sandbox.excludedCommands in $SETTINGS yourself."
  exit 0
fi
[ -f "$SETTINGS" ] || { mkdir -p "$(dirname "$SETTINGS")"; echo '{}' > "$SETTINGS"; }
if jq -e --arg d "$ROOT" '(.permissions.additionalDirectories // [] | index($d)) and (.sandbox.excludedCommands // [] | index("agent-worktree *"))' "$SETTINGS" >/dev/null; then
  echo "  already set"
  exit 0
fi
echo "  So sandboxed agents can work in $ROOT and the command can fetch from your remotes, this adds to $SETTINGS:"
echo "    permissions.additionalDirectories: \"$ROOT\""
echo "    sandbox.excludedCommands: \"agent-worktree *\""
if [ $YES -eq 0 ]; then read -r -p "  Apply? [y/N] " ok; [ "$ok" = "y" ] || { echo "  skipped; nothing changed"; exit 0; }; fi
cp "$SETTINGS" "$SETTINGS.bak-agent-worktree"
tmp=$(mktemp)
jq --arg d "$ROOT" '.permissions.additionalDirectories = ((.permissions.additionalDirectories // []) + [$d] | unique)
  | .sandbox.excludedCommands = ((.sandbox.excludedCommands // []) + ["agent-worktree *"] | unique)' "$SETTINGS" > "$tmp"
mv "$tmp" "$SETTINGS"
echo "  done (backup: $SETTINGS.bak-agent-worktree)"
