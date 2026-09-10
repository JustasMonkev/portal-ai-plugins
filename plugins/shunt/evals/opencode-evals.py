"""Exercise public shunt scripts with a token-free OpenCode executable stub."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
STUB = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
Path(os.environ["CAPTURE"]).write_text(json.dumps({
    "args": sys.argv[1:], "input": sys.stdin.read(),
    "config": json.loads(os.environ["OPENCODE_CONFIG_CONTENT"]),
    "permission": os.environ["OPENCODE_PERMISSION"], "cwd": os.getcwd(),
}))
mode = os.environ.get("RESPONSE", "ok")
if mode == "timeout": time.sleep(30)
if mode == "exit":
    print("subscription unavailable", file=sys.stderr)
    sys.exit(2)
if mode == "garbled":
    print("not json")
elif mode == "error":
    print(json.dumps({"type": "error", "error": {"message": "quota exhausted"}}))
else:
    if mode != "empty":
        print(json.dumps({"type": "text", "part": {"text": "worker answer"}}))
    print(json.dumps({"type": "step_finish", "sessionID": "test-session",
        "part": {"reason": "length" if mode == "truncated" else "stop"}}))
'''


class OpenCodeEvals(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shunt-eval-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        stub = self.root / "opencode"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.reference = self.root / "reference with spaces.txt"
        self.reference.write_text("reference `literal` $(not-executed)\nsecond line\n")
        self.capture = self.root / "capture.json"
        self.env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}",
                    "SHUNT_BACKEND": "opencode", "CAPTURE": str(self.capture),
                    "SHUNT_TIMEOUT_SECONDS": "5", "SHUNT_MAX_PAYLOAD_BYTES": "400000"}

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

    def test_codex_launcher_selects_astra_medium_and_preserves_arguments(self):
        stub = self.root / "codex"
        stub.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        stub.chmod(0o755)
        args = ["-C", str(self.root), "exec", "a task with spaces"]
        result = self.run_script("codex-shunt", args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["--model", "gpt-6-astra",
                         "-c", 'model_reasoning_effort="medium"', *args])


if __name__ == "__main__":
    unittest.main()
