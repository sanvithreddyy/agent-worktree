"""Tests for bin/agent-worktree.

Run: python3 -m unittest discover tests
Everything happens in a temp folder: bare repos stand in for the remote, a small sqlite file
stands in for T3 Code's database.
"""
import json, os, shutil, sqlite3, subprocess, sys, tempfile, time, unittest

TOOL = os.environ.get("AGENT_WORKTREE_BIN") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "agent-worktree")
GIT_ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
          "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
CLEAR = ("T3CODE_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "AGENT_WORKTREE_CHAT", "AGENT_WORKTREE_PROJECT")


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def load(path):
    with open(path) as f:
        return json.load(f)


def sh(*cmd, cwd=None, env=None, check=True):
    base = {k: v for k, v in os.environ.items() if k not in CLEAR}
    r = subprocess.run(cmd, cwd=cwd, env={**base, **GIT_ID, **(env or {})}, capture_output=True, text=True)
    if check and r.returncode:
        raise AssertionError(f"{cmd} failed: {r.stdout}{r.stderr}")
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="awt-"))
        self.root = os.path.join(self.tmp, "worktrees")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        for name in ("acme-api", "acme-web", "acme-shared"):
            self.make_repo(name)
        self.db = os.path.join(self.tmp, "state.sqlite")
        db = sqlite3.connect(self.db)
        db.execute("CREATE TABLE projection_projects (project_id TEXT, title TEXT, workspace_root TEXT)")
        db.execute("CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT, project_id TEXT, title TEXT, payload_json TEXT)")
        db.execute("INSERT INTO projection_projects VALUES ('p1', 'My Project', ?)", (self.proj,))
        db.commit()
        db.close()
        self.thread("lead", "Fix the login page", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_repo(self, name, where=None):
        bare = os.path.join(self.tmp, "remote", name + ".git")
        sh("git", "init", "--quiet", "--bare", "-b", "main", bare)
        seed = os.path.join(self.tmp, "seed-" + name)
        sh("git", "clone", "--quiet", bare, seed)
        write(os.path.join(seed, "README.md"), name + "\n")
        sh("git", "-C", seed, "add", ".")
        sh("git", "-C", seed, "commit", "--quiet", "-m", "init")
        sh("git", "-C", seed, "push", "--quiet", "origin", "HEAD:main")
        sh("git", "clone", "--quiet", bare, os.path.join(where or self.proj, name))
        shutil.rmtree(seed)

    def thread(self, tid, title, root):
        db = sqlite3.connect(self.db)
        payload = {"lineage": {"rootThreadId": root or tid, "parentThreadId": root}}
        db.execute("INSERT INTO orchestration_v2_projection_threads VALUES (?, 'p1', ?, ?)", (tid, title, json.dumps(payload)))
        db.commit()
        db.close()

    def tool(self, *args, tid="lead", check=True, cwd=None, **extra):
        env = {"AGENT_WORKTREE_ROOT": self.root, "AGENT_WORKTREE_T3_DB": self.db, **extra}
        if tid:
            env["T3CODE_THREAD_ID"] = tid
        return sh(sys.executable, TOOL, *args, env=env, check=check, cwd=cwd or self.tmp)

    def chat(self, project="my-project"):
        (name,) = os.listdir(os.path.join(self.root, project))
        return os.path.join(self.root, project, name)

    def worktrees(self, repo):
        out = sh("git", "-C", os.path.join(self.proj, repo), "worktree", "list", "--porcelain").stdout
        return [l.split(" ", 1)[1] for l in out.splitlines() if l.startswith("worktree ")][1:]

    def age(self, path, days=2):
        """Make a folder and, for a checkout, its git records look untouched for `days`."""
        t = time.time() - days * 86400
        tops = [path]
        if os.path.isfile(os.path.join(path, ".git")):
            with open(os.path.join(path, ".git")) as f:
                tops.append(f.read().split("gitdir:", 1)[1].strip())
        for top in tops:
            for dp, dns, fns in os.walk(top):
                for n in dns + fns:
                    os.utime(os.path.join(dp, n), (t, t), follow_symlinks=False)
            os.utime(top, (t, t))

    def age_task(self, tdir):
        self.age(tdir)
        for name in os.listdir(tdir):
            if os.path.isdir(os.path.join(tdir, name)):
                self.age(os.path.join(tdir, name))


class NewTests(Base):
    def test_nested_agents_share_the_top_chat_folder(self):
        self.thread("child", "API part", "lead")
        self.thread("grandchild", "tests", "lead")
        self.tool("new", "lead", "api", "web", "--branch", "fix/login")
        self.tool("new", "api-part", "api", tid="child")
        self.tool("new", "tests", "shared", tid="grandchild")
        chat = self.chat()
        self.assertTrue(os.path.basename(chat).startswith("fix-the-login-page-"))
        for rel in ("lead/acme-api", "lead/acme-web", "api-part/acme-api", "tests/acme-shared"):
            self.assertTrue(os.path.isfile(os.path.join(chat, rel, ".git")), rel)
        self.assertEqual(sh("git", "-C", os.path.join(chat, "lead/acme-web"), "branch", "--show-current").stdout.strip(), "fix/login")
        self.assertEqual(sh("git", "-C", os.path.join(chat, "api-part/acme-api"), "branch", "--show-current").stdout.strip(), "")
        self.assertEqual(load(os.path.join(chat, ".chat.json"))["chat_id"], "t3:lead")

    def test_renamed_chat_keeps_its_folder(self):
        self.tool("new", "one", "web")
        before = self.chat()
        db = sqlite3.connect(self.db)
        db.execute("UPDATE orchestration_v2_projection_threads SET title = 'Something else' WHERE thread_id = 'lead'")
        db.commit()
        db.close()
        self.tool("new", "two", "api")
        self.assertEqual(self.chat(), before)

    def test_second_call_adds_repos_to_a_task(self):
        self.tool("new", "lead", "web")
        self.tool("new", "lead", "shared")
        rec = load(os.path.join(self.chat(), "lead", ".agent-worktree.json"))
        self.assertEqual(sorted(os.path.basename(c["path"]) for c in rec["checkouts"]), ["acme-shared", "acme-web"])
        r = self.tool("new", "lead", "web", check=False)
        self.assertIn("already exists", r.stderr)

    def test_unknown_and_ambiguous_repos_create_nothing(self):
        r = self.tool("new", "x", "nope", check=False)
        self.assertIn("no such repo", r.stderr)
        self.assertIn("acme-web", r.stderr)
        self.make_repo("other-web")
        r = self.tool("new", "x", "api", "web", check=False)
        self.assertIn("more than one repo matches", r.stderr)
        self.assertFalse(os.path.exists(self.root))
        self.assertEqual(self.worktrees("acme-api"), [])

    def test_exact_name_beats_suffix(self):
        self.make_repo("web")
        self.tool("new", "x", "web")
        self.assertTrue(os.path.isdir(os.path.join(self.chat(), "x", "web")))

    def test_unknown_ref_creates_nothing(self):
        r = self.tool("new", "x", "api", "web=origin/no-such-branch", check=False)
        self.assertIn("unknown ref", r.stderr)
        self.assertEqual(self.worktrees("acme-api"), [])

    def test_existing_remote_branch_is_checked_out_and_tracked(self):
        other = os.path.join(self.tmp, "other")
        sh("git", "clone", "--quiet", os.path.join(self.tmp, "remote", "acme-web.git"), other)
        sh("git", "-C", other, "commit", "--quiet", "--allow-empty", "-m", "pr work")
        sh("git", "-C", other, "push", "--quiet", "origin", "HEAD:refs/heads/feat/pr-7")
        head = sh("git", "-C", other, "rev-parse", "HEAD").stdout.strip()
        self.tool("new", "review", "web", "--branch", "feat/pr-7")
        co = os.path.join(self.chat(), "review", "acme-web")
        self.assertEqual(sh("git", "-C", co, "rev-parse", "HEAD").stdout.strip(), head)
        self.assertEqual(sh("git", "-C", co, "rev-parse", "--abbrev-ref", "@{u}").stdout.strip(), "origin/feat/pr-7")

    def test_branch_already_checked_out_is_refused(self):
        self.tool("new", "a", "web", "--branch", "fix/one")
        r = self.tool("new", "b", "web", "--branch", "fix/one", check=False)
        self.assertIn("already checked out", r.stderr)

    def test_failure_midway_rolls_back(self):
        locked = os.path.join(self.proj, "acme-web", ".git", "worktrees")
        os.makedirs(locked, exist_ok=True)
        os.chmod(locked, 0o555)
        try:
            r = self.tool("new", "x", "api", "web", "--branch", "fix/two", check=False)
        finally:
            os.chmod(locked, 0o755)
        if r.returncode == 0:
            self.skipTest("this machine lets git write into a read-only folder (running as root?)")
        self.assertIn("git worktree add failed", r.stderr)
        self.assertEqual(self.worktrees("acme-api"), [])
        api = os.path.join(self.proj, "acme-api")
        self.assertNotEqual(sh("git", "-C", api, "show-ref", "--verify", "--quiet", "refs/heads/fix/two", check=False).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, "my-project")) and os.listdir(os.path.join(self.root, "my-project")))

    def test_bad_task_name(self):
        r = self.tool("new", "Fix Login", "web", check=False)
        self.assertIn("task name must look like 'fix-login'", r.stderr)

    def test_claude_session_inside_a_repo(self):
        self.tool("new", "x", tid=None, cwd=os.path.join(self.proj, "acme-web"), CLAUDE_CODE_SESSION_ID="abc123")
        chat = self.chat("acme-web")
        self.assertTrue(os.path.basename(chat).startswith("session-"))
        self.assertTrue(os.path.isdir(os.path.join(chat, "x", "acme-web")))
        self.tool("new", "y", "api", tid=None, cwd=os.path.join(chat, "x", "acme-web"), CLAUDE_CODE_SESSION_ID="abc123")
        self.assertTrue(os.path.isdir(os.path.join(chat, "y", "acme-api")))

    def test_codex_and_explicit_chat(self):
        self.tool("new", "x", "web", tid=None, cwd=self.proj, CODEX_THREAD_ID="t-1")
        self.tool("new", "y", "web", tid="lead", cwd=self.proj, AGENT_WORKTREE_CHAT="shared-chat")
        names = sorted(os.listdir(os.path.join(self.root, "proj")))
        self.assertEqual(len(names), 2)
        self.assertTrue(any(n.startswith("chat-") for n in names))
        self.assertTrue(any(n.startswith("session-") for n in names))


class DoneTests(Base):
    def setUp(self):
        super().setUp()
        self.tool("new", "lead", "api", "web", "--branch", "fix/login")
        self.tool("new", "side", "shared")
        self.lead = os.path.join(self.chat(), "lead")

    def test_uncommitted_change_keeps_everything(self):
        write(os.path.join(self.lead, "acme-web", "new.txt"), "x")
        r = self.tool("done", "lead", check=False)
        self.assertIn("nothing removed", r.stderr)
        self.assertIn("1 uncommitted changes", r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.lead, "acme-api")))
        self.assertTrue(os.path.isdir(os.path.join(self.lead, "acme-web")))

    def test_unpushed_commit_keeps_everything(self):
        web = os.path.join(self.lead, "acme-web")
        sh("git", "-C", web, "commit", "--quiet", "--allow-empty", "-m", "local only")
        r = self.tool("done", "lead", check=False)
        self.assertIn("fix/login: 1 commits not on any remote branch", r.stderr)
        self.assertTrue(os.path.isdir(web))

    def test_pushed_work_is_removed_and_folders_tidied(self):
        web = os.path.join(self.lead, "acme-web")
        write(os.path.join(web, "change.txt"), "x")
        sh("git", "-C", web, "add", ".")
        sh("git", "-C", web, "commit", "--quiet", "-m", "change")
        sh("git", "-C", web, "push", "--quiet", "origin", "fix/login")
        chat = self.chat()
        self.tool("done", "lead")
        self.assertFalse(os.path.exists(self.lead))
        self.assertEqual(self.worktrees("acme-web"), [])
        self.assertTrue(os.path.isdir(chat))
        self.tool("done", "side")
        self.assertFalse(os.path.exists(chat))
        self.assertEqual(sh("git", "-C", os.path.join(self.proj, "acme-web"), "branch", "--list", "fix/login").stdout.strip(), "fix/login")

    def test_node_modules_and_ds_store_do_not_block(self):
        os.makedirs(os.path.join(self.lead, "acme-web", "node_modules", "x"))
        write(os.path.join(self.lead, "acme-api", ".DS_Store"), "x")
        self.tool("done", "lead")
        self.assertFalse(os.path.exists(self.lead))

    def test_checkout_deleted_by_hand_is_pruned(self):
        shutil.rmtree(os.path.join(self.lead, "acme-web"))
        self.tool("done", "lead")
        self.assertEqual(self.worktrees("acme-web"), [])

    def test_unknown_task(self):
        r = self.tool("done", "nope", check=False)
        self.assertIn("no task nope", r.stderr)

    def test_list(self):
        write(os.path.join(self.lead, "acme-web", "new.txt"), "x")
        out = self.tool("list").stdout
        self.assertIn("lead/", out)
        self.assertIn("acme-web: fix/login, 1 uncommitted", out)
        self.assertIn("acme-shared: detached", out)
        self.assertIn("lead/", self.tool("list", "--all", tid=None).stdout)


class CleanTests(Base):
    def test_removes_only_safe_idle_tasks(self):
        self.tool("new", "clean", "web")
        self.tool("new", "dirty", "api")
        self.tool("new", "fresh", "shared")
        chat = self.chat()
        write(os.path.join(chat, "dirty", "acme-api", "x.txt"), "x")
        self.age_task(os.path.join(chat, "clean"))
        self.age_task(os.path.join(chat, "dirty"))
        out = self.tool("clean", tid=None).stdout
        self.assertIn("removed  my-project/", out)
        self.assertIn("1 uncommitted changes", out)
        self.assertIn("used in the last 24 h", out)
        self.assertFalse(os.path.exists(os.path.join(chat, "clean")))
        self.assertTrue(os.path.isdir(os.path.join(chat, "dirty", "acme-api")))
        self.assertTrue(os.path.isdir(os.path.join(chat, "fresh", "acme-shared")))
        self.assertEqual(self.worktrees("acme-web"), [])

    def test_dry_run_removes_nothing(self):
        self.tool("new", "clean", "web")
        self.age_task(os.path.join(self.chat(), "clean"))
        out = self.tool("clean", "--dry-run", tid=None).stdout
        self.assertIn("would remove my-project/", out)
        self.assertTrue(os.path.isdir(os.path.join(self.chat(), "clean", "acme-web")))

    def test_last_task_removed_drops_the_chat_folder(self):
        self.tool("new", "only", "web")
        chat = self.chat()
        self.age_task(os.path.join(chat, "only"))
        self.tool("clean", tid=None)
        self.assertFalse(os.path.exists(chat))

    def test_idle_hours_setting(self):
        self.tool("new", "only", "web")
        self.age_task(os.path.join(self.chat(), "only"))
        out = self.tool("clean", "--idle-hours", "72", "--dry-run", tid=None).stdout
        self.assertIn("used in the last 72 h", out)


if __name__ == "__main__":
    unittest.main()
