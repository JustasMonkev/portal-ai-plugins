"""Exercise public shunt scripts with token-free OpenCode and Codex stubs."""

import json
from itertools import product
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import time
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
STUB = '''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
Path(os.environ["CAPTURE"]).write_text(json.dumps({
    "args": sys.argv[1:], "input": sys.stdin.read(),
    "config": json.loads(os.environ.get("OPENCODE_CONFIG_CONTENT", "{}")),
    "permission": os.environ.get("OPENCODE_PERMISSION"), "cwd": os.getcwd(),
    "pid": os.getpid(), "runner_pid": os.getppid(),
}))
mode = os.environ.get("RESPONSE", "ok")
if mode == "cancel":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    capture = Path(os.environ["CAPTURE"])
    data = json.loads(capture.read_text())
    data["child_pid"] = child.pid
    capture.write_text(json.dumps(data))
    time.sleep(30)
if mode == "timeout": time.sleep(30)
if mode == "exit":
    print("subscription unavailable", file=sys.stderr)
    sys.exit(2)
if mode == "garbled":
    print("not json")
elif mode == "error":
    print(json.dumps({"type": "error", "error": {"message": "quota exhausted"}}))
else:
    if Path(sys.argv[0]).name == "codex":
        answer = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
        if mode != "missing":
            answer.write_text("" if mode == "empty" else "worker answer")
        print(json.dumps({"type": "thread.started", "thread_id": "test-session"}))
        print(json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": "intermediate commentary, not the answer"}}))
        if mode == "wrong_format":
            print(json.dumps({"type": "step_finish", "part": {"reason": "stop"}}))
        elif mode != "truncated":
            print(json.dumps({"type": "turn.completed"}))
    else:
        if mode != "empty":
            print(json.dumps({"type": "text", "part": {"text": "worker answer"}}))
        print(json.dumps({"type": "step_finish", "sessionID": "test-session",
            "part": {"reason": "length" if mode == "truncated" else "stop"}}))
'''


class WorkerEvals(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shunt-eval-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for harness in ("opencode", "codex"):
            stub = self.root / harness
            stub.write_text(STUB)
            stub.chmod(0o755)
        self.reference = self.root / "reference with spaces.txt"
        self.reference.write_text("reference `literal` $(not-executed)\nsecond line\n")
        self.capture = self.root / "capture.json"
        self.env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}",
                    "SHUNT_BACKEND": "opencode", "CAPTURE": str(self.capture),
                    "SHUNT_TIMEOUT_SECONDS": "5", "SHUNT_MAX_PAYLOAD_BYTES": "400000"}
        for name in ("SHUNT_WORKER_MODEL", "SHUNT_WORKER_EFFORT", "RESPONSE"):
            self.env.pop(name, None)

    def run_script(self, script="bulk-read", args=None):
        if args is None:
            args = ["--question", "Explain", "--paths", str(self.reference)]
        return subprocess.run(["bash", str(PLUGIN / "scripts" / script), *args],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_routing_corpus_permissions_and_cleanup(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "worker answer\n")
        captured = json.loads(self.capture.read_text())
        self.assertIn("zai-coding-plan/glm-5.3-flash", captured["args"])
        self.assertEqual(captured["args"][captured["args"].index("--variant") + 1], "max")
        self.assertIn(self.reference.read_text(), captured["input"])
        self.assertNotIn(self.reference.read_text(), captured["args"])
        self.assertEqual(json.loads(captured["permission"]), {"*": "deny"})
        self.assertEqual(captured["config"]["agent"]["shunt-worker"]["permission"], {"*": "deny"})
        self.assertEqual(captured["config"]["share"], "disabled")
        self.assertFalse(Path(captured["cwd"]).exists())
        self.assertIn("test-session", result.stderr)

    def test_code_write_target(self):
        target = self.root / "result.txt"
        result = self.run_script("code-write", ["--spec", "Generate", "--reference",
                                 str(self.reference), "--target", str(target)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "worker answer\n")

    def test_model_and_effort_overrides(self):
        for backend, model in (("opencode", "openrouter/deepseek/deepseek-v4.1-flash"),
                               ("codex", "gpt-5.6-luna")):
            for effort in ("high", ""):
                with self.subTest(backend=backend, effort=effort):
                    self.env.update(SHUNT_BACKEND=backend, SHUNT_WORKER_MODEL=model,
                                    SHUNT_WORKER_EFFORT=effort)
                    result = self.run_script()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "worker answer\n")
                    captured = json.loads(self.capture.read_text())
                    args = captured["args"]
                    self.assertEqual(args[args.index("--model") + 1], model)
                    if backend == "opencode":
                        self.assertEqual("--variant" in args, bool(effort))
                        if effort:
                            self.assertEqual(args[args.index("--variant") + 1], effort)
                        self.assertEqual(captured["config"]["small_model"], model)
                    else:
                        settings = [arg for arg in args if arg.startswith("model_reasoning_effort=")]
                        self.assertEqual(settings, [f'model_reasoning_effort="{effort}"'] if effort else [])
                    self.assertIn(model, result.stderr)

    def test_codex_default_isolated_worker_and_final_answer(self):
        self.env["SHUNT_BACKEND"] = "codex"
        (self.root / "opencode").unlink()  # The other harness is not required.
        target = self.root / "generated.txt"
        result = self.run_script("code-write", ["--spec", "Generate", "--reference",
                                 str(self.reference), "--target", str(target)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "worker answer\n")
        captured = json.loads(self.capture.read_text())
        args = captured["args"]
        self.assertEqual(args[args.index("--model") + 1], "gpt-5.6-luna")
        self.assertIn('model_reasoning_effort="medium"', args)
        self.assertIn("--ephemeral", args)
        self.assertIn("--ignore-user-config", args)
        self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
        for setting in ('approval_policy="never"', 'features.shell_tool=false',
                        'features.apps=false', 'agents.enabled=false', 'web_search="disabled"'):
            self.assertIn(setting, args)
        self.assertIn(self.reference.read_text(), captured["input"])
        self.assertFalse(Path(captured["cwd"]).exists())
        self.assertIn("test-session", result.stderr)

    def test_codex_failures_preserve_target(self):
        self.env["SHUNT_BACKEND"] = "codex"
        for mode in ("exit", "garbled", "error", "empty", "missing", "truncated", "wrong_format", "timeout"):
            with self.subTest(mode=mode):
                self.env.update(RESPONSE=mode, SHUNT_TIMEOUT_SECONDS="1")
                target = self.root / "existing.txt"
                target.write_text("keep existing content")
                result = self.run_script("code-write", ["--spec", "Generate", "--reference",
                                         str(self.reference), "--target", str(target)])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(target.read_text(), "keep existing content")
                if mode == "error":
                    self.assertIn("quota exhausted", result.stderr)

    def test_empty_model_fails_before_invocation(self):
        self.env["SHUNT_WORKER_MODEL"] = ""
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_failures_do_not_write_partial_answers(self):
        for mode in ("exit", "garbled", "error", "empty", "truncated", "timeout"):
            with self.subTest(mode=mode):
                self.env.update(RESPONSE=mode, SHUNT_TIMEOUT_SECONDS="1")
                target = self.root / "existing.txt"
                target.write_text("keep existing content")
                result = self.run_script("code-write", ["--spec", "Generate", "--reference",
                                         str(self.reference), "--target", str(target)])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(target.read_text(), "keep existing content")

    def test_payload_and_timeout_validation_before_invocation(self):
        for key, value in (("SHUNT_MAX_PAYLOAD_BYTES", "1"),
                           ("SHUNT_TIMEOUT_SECONDS", "0"),
                           ("SHUNT_TIMEOUT_SECONDS", "bad")):
            with self.subTest(key=key, value=value):
                self.env[key] = value
                result = self.run_script()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.capture.exists())
                self.env[key] = "400000" if "PAYLOAD" in key else "5"

    def test_invalid_backend_fails_without_fallback(self):
        self.env["SHUNT_BACKEND"] = "typo"
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHUNT_BACKEND", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_missing_file_fails_before_invocation(self):
        self.reference.unlink()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_shell_pid_cancellation_stops_runner_and_worker_tree(self):
        for backend, script, signum in product(
                ("opencode", "codex"), ("bulk-read", "code-write"), (signal.SIGTERM, signal.SIGINT)):
            with self.subTest(backend=backend, script=script, signal=signum):
                self.env["SHUNT_BACKEND"] = backend
                self.capture.unlink(missing_ok=True)
                self.env["RESPONSE"] = "cancel"
                target = self.root / "existing.txt"
                target.write_text("keep existing content")
                args = (["--question", "Explain", "--paths", str(self.reference)]
                        if script == "bulk-read" else
                        ["--spec", "Generate", "--reference", str(self.reference),
                         "--target", str(target)])
                process = subprocess.Popen(
                    ["bash", str(PLUGIN / "scripts" / script), *args], env=self.env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                )
                captured = {}
                try:
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        try:
                            captured = json.loads(self.capture.read_text())
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                        if "child_pid" in captured:
                            break
                        time.sleep(0.02)
                    self.assertIn("child_pid", captured, "worker did not start")
                    process.send_signal(signum)  # Only the public shell PID.
                    process.wait(timeout=3)
                    pids = [captured[key] for key in ("runner_pid", "pid", "child_pid")]
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        alive = []
                        for pid in pids:
                            state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                                                   capture_output=True, text=True).stdout.strip()
                            if state and not state.startswith("Z"):
                                alive.append(pid)
                        if not alive:
                            break
                        time.sleep(0.02)
                    self.assertEqual(alive, [], "cancellation left worker processes running")
                    self.assertEqual(process.returncode, 128 + signum)
                    self.assertFalse(Path(captured["cwd"]).exists())
                    self.assertEqual(target.read_text(), "keep existing content")
                finally:
                    for group in (process.pid, captured.get("pid")):
                        if group:
                            try:
                                os.killpg(group, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    process.communicate(timeout=3)
                    if captured.get("cwd"):
                        shutil.rmtree(captured["cwd"], ignore_errors=True)

    def test_codex_launcher_selects_astra_medium_and_preserves_arguments(self):
        stub = self.root / "codex"
        stub.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        stub.chmod(0o755)
        args = ["-C", str(self.root), "exec", "a task with spaces"]
        result = self.run_script("codex-shunt", args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["--model", "gpt-6-astra",
                         "-c", 'model_reasoning_effort="medium"',
                         "-c", 'shell_environment_policy.set.SHUNT_BACKEND="opencode"', *args])

    def test_launcher_preserves_worker_settings_without_changing_lead(self):
        stub = self.root / "codex"
        stub.write_text('''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({"args": sys.argv[1:], "worker": {
    key: os.environ.get(key) for key in
    ("SHUNT_BACKEND", "SHUNT_WORKER_MODEL", "SHUNT_WORKER_EFFORT")}}))
''')
        stub.chmod(0o755)
        self.env.update(SHUNT_BACKEND="codex", SHUNT_WORKER_MODEL="gpt-5.6-luna",
                        SHUNT_WORKER_EFFORT="high")
        result = self.run_script("codex-shunt", ["-C", str(self.root)])
        captured = json.loads(result.stdout)
        self.assertEqual(captured["worker"], {key: self.env[key] for key in captured["worker"]})
        self.assertIn("gpt-6-astra", captured["args"])
        self.assertIn('model_reasoning_effort="medium"', captured["args"])
        for key, value in captured["worker"].items():
            self.assertIn(f"shell_environment_policy.set.{key}={json.dumps(value)}", captured["args"])
        self.env.pop("SHUNT_BACKEND")
        result = self.run_script("codex-shunt", [])
        captured = json.loads(result.stdout)
        self.assertEqual(captured["worker"]["SHUNT_BACKEND"], "opencode")
        self.assertFalse(any(arg.startswith("shell_environment_policy.set.SHUNT_BACKEND=")
                             for arg in captured["args"]))


if __name__ == "__main__":
    unittest.main()
