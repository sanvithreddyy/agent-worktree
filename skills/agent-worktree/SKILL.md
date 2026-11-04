---
name: agent-worktree
description: Make and remove git worktrees with the agent-worktree command. Use whenever you need your own checkout of a repo (a branch to work on, a PR to review, several repos at once) instead of running git worktree add yourself, and when your work in one is pushed or finished.
---

# agent-worktree

Use `agent-worktree` for every git worktree you need. Don't run `git worktree add` or delete worktree folders yourself: the command keeps every worktree from this chat in one folder and only removes work that is safe on a remote.

## Make worktrees

```sh
agent-worktree new <task> <repo>...                 # detached at origin's default branch, after a fetch
agent-worktree new <task> <repo> --branch fix/login # new branch (or the existing remote one)
agent-worktree new <task> api web=origin/release    # a different starting ref per repo
agent-worktree new <task>                           # the repo you're in
```

- `<task>` is a short lowercase name for your piece of work, like `fix-login` or `review-pr-42`. Pick one no other agent in this chat uses.
- `<repo>` is a repo folder in the project (`web` finds `acme-web`), or a path.
- It prints each worktree's path. Work there.
- Run `new` again with the same task to add another repo.
- If it says the fetch failed (a sandbox can block GitHub logins), run `git -C <repo> fetch origin` as its own command, then rerun with `--no-fetch`.

## Finish

When your work is committed and pushed, run:

```sh
agent-worktree done <task>
```

It removes the task's worktrees, or refuses and removes nothing if any of them has uncommitted changes or commits that aren't on a remote branch. Then either push what's left or tell the user why you're keeping it. Never force it by deleting the folder.

`agent-worktree list` shows this chat's tasks; `agent-worktree list --all` shows every chat.

Agents you start share your chat's folder, so give each of them its own task name.
