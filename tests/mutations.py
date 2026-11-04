"""Break one safety rule at a time in a copy of bin/agent-worktree and check that a test fails.

Run: python3 tests/mutations.py
A rule whose break no test notices is a rule the tests don't really check.
"""
import os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "bin", "agent-worktree")
M = [
    ("done ignores problems", "    if problems:\n        return problems", "    if False:\n        return problems",
     ["DoneTests.test_uncommitted_change_keeps_everything", "DoneTests.test_unpushed_commit_keeps_everything"]),
    ("unpushed commits look pushed", 'if not on_remote and c["head"] not in pr_heads(c["repo"], cache):', "if False:",
     ["DoneTests.test_unpushed_commit_keeps_everything"]),
    ("sub-agents ignore the top chat", '.get("rootThreadId") or tid', '.get("nope") or tid',
     ["NewTests.test_nested_agents_share_the_top_chat_folder"]),
    ("renamed chat gets a new folder", 'if name.endswith("-" + tag)', 'if False and name.endswith("-" + tag)',
     ["NewTests.test_renamed_chat_keeps_its_folder"]),
    ("no rollback", "for q in made:  # leave nothing half made", "for q in []:",
     ["NewTests.test_failure_midway_rolls_back"]),
    ("bad refs accepted", 'if git(p["repo"], "rev-parse", "--verify", "--quiet", p["ref"] + "^{commit}").returncode:', "if False:",
     ["NewTests.test_unknown_ref_creates_nothing"]),
    ("node_modules counts as work", 'if xy == "??" and os.path.basename(f.rstrip("/")) in NOISE:', "if False:",
     ["DoneTests.test_node_modules_and_ds_store_do_not_block"]),
    ("clean ignores recent use", "elif recent or git_recent:", "elif False:",
     ["CleanTests.test_removes_only_safe_idle_tasks"]),
    ("clean ignores --dry-run", "                if dry_run:\n", "                if False:\n",
     ["CleanTests.test_dry_run_removes_nothing"]),
    ("empty chat folder left", "    if os.path.isdir(cdir) and not subdirs(cdir) and only_records(cdir):\n        shutil.rmtree(cdir)\n    return []",
     "    return []", ["CleanTests.test_last_task_removed_drops_the_chat_folder"]),
]

missed = 0
for name, old, new, tests in M:
    tmp = tempfile.mkdtemp(prefix="awt-mut-")
    try:
        copy = os.path.join(tmp, "agent-worktree")
        with open(TOOL) as f:
            src = f.read()
        if src.count(old) != 1:
            print(f"SETUP   {name}: pattern found {src.count(old)} times")
            missed += 1
            continue
        with open(copy, "w") as f:
            f.write(src.replace(old, new))
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", *[f"test_agent_worktree.{t}" for t in tests]],
                           cwd=HERE, env={**os.environ, "AGENT_WORKTREE_BIN": copy}, capture_output=True, text=True)
        caught = r.returncode != 0
        missed += not caught
        print(f"{'caught' if caught else 'MISSED'}  {name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
print(f"{len(M) - missed} of {len(M)} breaks caught")
sys.exit(1 if missed else 0)
