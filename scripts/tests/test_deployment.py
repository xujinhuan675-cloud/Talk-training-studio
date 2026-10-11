import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        runtime = self.bin / "fake_runtime.py"
        runtime.write_bytes((SCRIPTS / "tests/fake_runtime.py").read_bytes())
        runtime.chmod(0o755)
        for name in ("docker", "curl", "sleep", "timeout", "skopeo", "ssh", "scp"):
            (self.bin / name).symlink_to(runtime)
        for name, service in (("backend", "backend"), ("newapi", "new-api")):
            directory = self.root / name
            directory.mkdir()
            (directory / "docker-compose.yml").write_text(
                f"services:\n  {service}:\n    image: old-{name}\n", encoding="utf-8")
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "commands.jsonl"
        self.write_state({
            "images": {"old-backend": {"id": "sha256:" + "1" * 64, "digests": []},
                       "old-newapi": {"id": "sha256:" + "2" * 64, "digests": []}},
            "containers": {"talkwise-backend": {"image": "old-backend"},
                           "1Panel-new-api-4jUC": {"image": "old-newapi"}},
        })
        self.env = {
            **os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_STATE": str(self.state_path), "FAKE_LOG": str(self.log_path),
            "BACKEND_IMAGE_REF": "ghcr.io/test/talkwise-backend:release",
            "NEWAPI_IMAGE_REF": "ghcr.io/test/talkwise-frontend-host:release",
            "ROOT_COMMIT": "a" * 40, "NEWAPI_COMMIT": "e" * 40,
            "BACKEND_DIGEST": "sha256:" + "b" * 64,
            "NEWAPI_DIGEST": "sha256:" + "f" * 64,
            "PREFETCH_ID": "test-release", "PREFETCHED": "true",
            "PREFETCH_ROOT": str(self.root / "prefetch"),
            "DEPLOY_LOCK_FILE": str(self.root / "deploy.lock"),
            "BACKUP_ROOT": str(self.root / "backups"),
            "TALKWISE_DIR": str(self.root / "backend"), "NEWAPI_DIR": str(self.root / "newapi"),
            "HEALTH_ATTEMPTS": "2", "HEALTH_INTERVAL_SECONDS": "0", "PULL_RETRIES": "0",
        }

    def write_state(self, state):
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def flag(self, key, value=True):
        state = self.state()
        state[key] = value
        self.write_state(state)

    def run_script(self, name):
        return subprocess.run(["bash", str(SCRIPTS / name)], env=self.env,
                              capture_output=True, text=True, timeout=12)

    def prepare(self):
        result = self.run_script("remote-prefetch.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def commands(self):
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    def assert_old_running(self):
        self.assertEqual(self.state()["containers"], {
            "talkwise-backend": {"image": "old-backend"},
            "1Panel-new-api-4jUC": {"image": "old-newapi"},
        })

    def assert_no_switch(self):
        self.assert_old_running()
        self.assertFalse(any("up" in command for command in self.commands()))

    def test_pull_failure_preserves_containers(self):
        self.flag("pull_failure")
        self.assertNotEqual(self.run_script("remote-prefetch.sh").returncode, 0)
        self.assert_no_switch()
        self.assertFalse((self.root / "prefetch/test-release").exists())

    def test_failed_prefetch_records_duration(self):
        self.flag("pull_failure")
        result = self.run_script("remote-prefetch.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prefetch_duration_seconds=", result.stdout)

    def test_prefetch_pulls_local_registry_by_digest(self):
        self.prepare()
        pulls = [command[-1] for command in self.commands() if command[:2] == ["docker", "pull"]]
        self.assertEqual(pulls, [f"127.0.0.1:5000/talkwise-backend@{self.env['BACKEND_DIGEST']}",
                                 f"127.0.0.1:5000/talkwise-frontend-host@{self.env['NEWAPI_DIGEST']}"])

    def test_missing_digest_is_rejected(self):
        self.env.pop("BACKEND_DIGEST")
        self.assertNotEqual(self.run_script("remote-prefetch.sh").returncode, 0)
        self.assert_old_running()
        self.assertFalse(self.log_path.exists())

    def test_digest_mismatch_is_rejected(self):
        self.flag("digest_mismatch")
        self.assertNotEqual(self.run_script("remote-prefetch.sh").returncode, 0)
        self.assert_no_switch()

    def test_missing_marker_rejects_switch_even_if_tags_exist(self):
        self.prepare()
        (self.root / "prefetch/test-release").unlink()
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_no_switch()

    def test_stale_marker_rejects_switch(self):
        self.prepare()
        self.env["ROOT_COMMIT"] = "3" * 40
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_no_switch()

    def test_changed_local_image_rejects_switch(self):
        self.prepare()
        state = self.state()
        state["images"]["talkwise-backend:prod-aaaaaaaaaaaa-bbbbbbbbbbbb"]["id"] = "sha256:" + "9" * 64
        self.write_state(state)
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_no_switch()

    def test_successful_switch_never_pulls_or_starts_dependencies(self):
        self.prepare()
        self.log_path.write_text("", encoding="utf-8")
        result = self.run_script("remote-deploy.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(self.state()["containers"]["talkwise-backend"]["image"], "old-backend")
        self.assertNotEqual(self.state()["containers"]["1Panel-new-api-4jUC"]["image"], "old-newapi")
        self.assertFalse(any(command[:2] == ["docker", "pull"] for command in self.commands()))
        for command in self.commands():
            if command[:2] == ["docker", "compose"] and "up" in command:
                self.assertIn("--no-deps", command)
                self.assertIn("--no-build", command)
                self.assertEqual(command[command.index("--pull") + 1], "never")
        self.assertIn("switch_duration_seconds=", result.stdout)

    def test_frontend_partial_compose_failure_rolls_back(self):
        self.prepare()
        self.flag("compose_failure", "new-api")
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_old_running()
        self.assertEqual(sum(command[:2] == ["docker", "compose"] and "up" in command for command in self.commands()), 2)

    def test_backend_partial_compose_failure_rolls_back_both(self):
        self.prepare()
        self.flag("compose_failure", "backend")
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_old_running()
        self.assertEqual(sum(command[:2] == ["docker", "compose"] and "up" in command for command in self.commands()), 4)

    def test_backend_health_failure_rolls_back_both(self):
        self.prepare()
        self.flag("health_failure")
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_old_running()
        self.assertEqual(sum(command[:2] == ["docker", "compose"] and "up" in command for command in self.commands()), 4)

    def test_running_image_mismatch_is_not_success(self):
        self.prepare()
        self.flag("running_mismatch")
        self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_old_running()

    def test_concurrent_deployment_is_rejected(self):
        self.prepare()
        with open(self.env["DEPLOY_LOCK_FILE"], "w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertNotEqual(self.run_script("remote-deploy.sh").returncode, 0)
        self.assert_no_switch()

    def runner_env(self):
        self.env.update(DEPLOY_SSH_HOST="test.invalid", DEPLOY_SSH_USER="test",
                        DEPLOY_SSH_KEY="test-only-key", DEPLOY_SSH_KNOWN_HOSTS="test-only-host-key",
                        GHCR_USERNAME="test", GHCR_TOKEN="test-only-token")

    def run_runner(self):
        return subprocess.run(["bash", str(SCRIPTS / "runner-release.sh"), "prefetch"],
                              env=self.env, capture_output=True, text=True, timeout=12)

    def test_runner_only_sends_scripts_and_control_commands(self):
        self.runner_env()
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertFalse(any(command[0] in ("docker", "skopeo") for command in commands))
        self.assertFalse(any(command[0] == "ssh" and ("-N" in command or "-L" in command)
                             for command in commands))
        uploads = [command for command in commands if command[0] == "scp"]
        self.assertEqual(len(uploads), 1)
        self.assertTrue(any(item.endswith("download-oci.py") for item in uploads[0]))
        self.assertFalse(any(item.endswith((".tar", ".tar.gz")) for item in uploads[0]))
        remote_calls = [command[-1] for command in commands if command[0] == "ssh"]
        self.assertIn("remote-mirror.sh", remote_calls[-2])
        self.assertIn("remote-prefetch.sh", remote_calls[-1])
        self.assertNotIn(self.env["GHCR_TOKEN"], json.dumps(commands) + result.stdout + result.stderr)
        self.assertTrue(self.state().get("credential_stdin_received"))
        self.assert_no_switch()

    def test_failed_direct_download_never_prefetches_or_falls_back(self):
        self.runner_env()
        self.flag("direct_download_failure")
        result = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(command[0] == "ssh" and "remote-prefetch.sh" in command[-1]
                             for command in self.commands()))
        self.assertFalse(any("-L" in command or command[0] == "docker" for command in self.commands()))
        self.assert_no_switch()

    def test_transient_download_retries_same_identity_once(self):
        self.runner_env()
        self.flag("transient_download_failures", 1)
        self.env["GITHUB_STEP_SUMMARY"] = str(self.root / "summary")
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mirrors = [c[-1] for c in self.commands() if c[0] == "ssh" and "remote-mirror.sh" in c[-1]]
        self.assertEqual(len(mirrors), 2)
        self.assertEqual(mirrors[0], mirrors[1])
        self.assertEqual(sum(c[0] == "ssh" and "remote-prefetch.sh" in c[-1] for c in self.commands()), 1)
        summary = Path(self.env["GITHUB_STEP_SUMMARY"]).read_text()
        self.assertIn("success", summary)
        self.assertIn("Mirror attempts | 2", summary)
        self.assertNotIn(self.env["GHCR_TOKEN"], summary)
        self.assert_no_switch()

    def test_exhausted_download_retries_report_failure_without_prefetch(self):
        self.runner_env()
        self.flag("transient_download_failures", 3)
        self.env["GITHUB_STEP_SUMMARY"] = str(self.root / "summary")
        self.env["GITHUB_RUN_ID"] = "12345"
        result = self.run_runner()
        self.assertEqual(result.returncode, 75)
        calls = [c[-1] for c in self.commands() if c[0] == "ssh"]
        self.assertEqual(sum("remote-mirror.sh" in c for c in calls), 2)
        self.assertFalse(any("remote-prefetch.sh" in c for c in calls))
        summary = Path(self.env["GITHUB_STEP_SUMMARY"]).read_text()
        self.assertIn("failure", summary)
        self.assertIn("gh run rerun 12345 --failed", summary)
        self.assert_no_switch()

    def test_nonretryable_download_failure_is_not_retried(self):
        self.runner_env()
        self.flag("direct_download_failure")
        self.assertNotEqual(self.run_runner().returncode, 0)
        self.assertEqual(sum(c[0] == "ssh" and "remote-mirror.sh" in c[-1] for c in self.commands()), 1)

    def test_workflow_prefetch_only_dispatch_keeps_switch_gate(self):
        import yaml
        workflow = yaml.safe_load((SCRIPTS.parent / ".github/workflows/deploy.yml").read_text())
        prefetch = workflow["jobs"]["prefetch"]
        self.assertNotIn("if", prefetch)
        self.assertIn("inputs.deploy", workflow["jobs"]["deploy"]["if"])
        self.assertEqual(prefetch["timeout-minutes"], 300)

    def test_switch_is_not_retried_and_summary_cannot_mask_result(self):
        self.runner_env()
        self.env["GITHUB_STEP_SUMMARY"] = str(self.root / "missing/summary")
        for failure in (False, True):
            self.flag("switch_failure", failure)
            self.log_path.write_text("", encoding="utf-8")
            result = subprocess.run(["bash", str(SCRIPTS / "runner-release.sh"), "switch"],
                                    env=self.env, capture_output=True, text=True, timeout=12)
            self.assertEqual(result.returncode, 75 if failure else 0, result.stdout + result.stderr)
            self.assertEqual(len(self.commands()), 1)
        calls = [c[-1] for c in self.commands() if c[0] == "ssh"]
        self.assertEqual(len(calls), 1)
        self.assertIn("remote-deploy.sh", calls[0])
        self.assertFalse(any("remote-mirror.sh" in c for c in calls))

    def test_bot_actor_can_start_server_direct_prefetch(self):
        self.runner_env()
        self.env["GHCR_USERNAME"] = "dependabot[bot]"
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
