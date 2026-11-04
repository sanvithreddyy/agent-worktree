# agent-worktree

Git worktrees for coding agents: one folder per chat, across as many repos as the task needs, removed only when the work is safe on a remote.

```
~/worktrees/
  my-project/
    fix-the-login-page-3f9a1c/      one chat
      lead/acme-api                 the agent you talk to
      lead/acme-web
      api-part/acme-api             an agent it started
      tests/acme-shared             an agent that one started
```

## Why

Agents that work in parallel need their own checkouts, so they make git worktrees. When a task spans several repos, and agents start other agents, they end up running `git worktree add` themselves, wherever they like. Nothing tracks those checkouts, so they pile up and fill the disk.

`agent-worktree` gives them one command to make worktrees and one to finish, and a daily `clean` for what they forget. It never removes a checkout that has uncommitted changes or commits missing from the remote.

## Install

```sh
git clone https://github.com/sanvithreddyy/agent-worktree && cd agent-worktree && ./install.sh
```

The installer:
- links `agent-worktree` into `~/.local/bin`
- links the `agent-worktree` skill into `~/.claude/skills` (Claude Code) and `~/.agents/skills` (Codex)
- if you have `jq`, shows a Claude Code settings change and asks before applying it. The change lets sandboxed agents write in `~/worktrees` and lets the command run outside the sandbox, so `git fetch` can log in.

It needs Python 3.10+ and git 2.31+. `./uninstall.sh` undoes it and leaves `~/worktrees` alone.

Then tell your agents to use it, for example in `AGENTS.md` or `CLAUDE.md`:

> Make git worktrees only with `agent-worktree new <task> <repo>…`, and run `agent-worktree done <task>` once that work is pushed. Never run `git worktree add` yourself.

## Use

```sh
agent-worktree new fix-login api web --branch fix/login   # worktrees of two repos on a new branch
agent-worktree new review-42 web --branch feat/pr-42      # an existing remote branch, tracked
agent-worktree new spike api=origin/release               # detached at a given ref
agent-worktree new quick-look                             # the repo you're in, detached at origin's default branch
agent-worktree list                                       # this chat's tasks (--all: every chat)
agent-worktree done fix-login                             # remove them, if everything is pushed
agent-worktree clean --dry-run                            # what the daily clean would remove
```

- `new` fetches origin first. Without `--branch`, the checkout is detached at origin's default branch, or at `repo=<ref>`. With `--branch`, it uses the local branch if one exists, otherwise tracks `origin/<branch>`, otherwise creates the branch. If any repo fails, nothing is left half made.
- A repo name is a folder in the project (`web`), or a unique `-web` suffix of one (`acme-web`), or a path.

Run `clean` once a day, for example from cron:

```
0 7 * * * $HOME/.local/bin/agent-worktree clean >> $HOME/worktrees/clean.log 2>&1
```

## How it decides

**Which chat.** The chat is the top-level conversation. Agents started by agents share its folder.
- **`AGENT_WORKTREE_CHAT`**, if set, wins.
- **[T3 Code](https://github.com/pingdotgg/t3code):** it reads the thread's lineage from T3's local database (read-only), so every sub-agent and delegated thread lands in its top chat's folder. Folder and project names come from the chat and project titles. A renamed chat keeps its folder.
- **Claude Code:** `CLAUDE_CODE_SESSION_ID`. Subagents share their parent's session.
- **Codex:** `CODEX_THREAD_ID`.

**Which project.** It's the T3 project. Outside T3, it's the repo you're in, and repo names are looked up among that repo's sibling folders. Set `AGENT_WORKTREE_PROJECT` to choose the name.

**When it's safe to remove.** `done` and `clean` remove a checkout only if:
- it has no uncommitted changes, ignoring untracked `node_modules` and `.DS_Store`;
- its commit is on a remote branch, or is the head of a GitHub PR (checked with `gh`, if it's installed and logged in).

`clean` also skips anything touched in the last 24 hours (`--idle-hours N`) and anything a process is working in. One unsafe checkout keeps its whole task. Branches are never deleted.

## Settings

| Variable | Default |
|---|---|
| `AGENT_WORKTREE_ROOT` | `~/worktrees` |
| `AGENT_WORKTREE_CHAT` | from T3, Claude Code or Codex |
| `AGENT_WORKTREE_PROJECT` | the T3 project, or the repo you're in |
| `AGENT_WORKTREE_T3_DB` | `~/.t3/userdata/statev2.sqlite` |

## Tests

```sh
python3 -m unittest discover tests   # 23 tests against throwaway repos and a fake T3 database
python3 tests/mutations.py           # breaks each safety rule in a copy and checks a test catches it
```

## License

MIT
