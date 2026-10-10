import fcntl
import hashlib
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
        for name in ("docker", "curl", "sleep", "timeout", "skopeo"):
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

    def sync_env(self):
        self.env["GHCR_AUTH_FILE"] = str(self.root / "auth.json")
        self.env["BACKEND_DIGEST"] = "sha256:" + hashlib.sha256(b"backend-manifest").hexdigest()
        self.env["NEWAPI_DIGEST"] = "sha256:" + hashlib.sha256(b"frontend-manifest").hexdigest()

    def test_mirror_preserves_full_index_and_source_digests(self):
        self.sync_env()
        result = self.run_script("sync-registry.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        copies = [command for command in self.commands() if command[:2] == ["skopeo", "copy"]]
        self.assertEqual(len(copies), 2)
        for command in copies:
            self.assertIn("--all", command)
            self.assertIn("--preserve-digests", command)
            self.assertIn("@sha256:", command[-2])
            self.assertTrue(command[-1].startswith("docker://127.0.0.1:15000/"))
        self.assert_no_switch()

    def test_mirror_rejects_failed_copy_or_wrong_digest(self):
        self.sync_env()
        for failure in ("sync_failure", "sync_digest_mismatch", "sync_manifest_mismatch"):
            with self.subTest(failure=failure):
                self.flag(failure)
                self.assertNotEqual(self.run_script("sync-registry.sh").returncode, 0)
                self.flag(failure, False)
        self.assert_no_switch()


if __name__ == "__main__":
    unittest.main()
