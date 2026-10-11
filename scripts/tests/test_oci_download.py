import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

SCRIPT = Path(__file__).resolve().parents[1] / "download-oci.py"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"


def descriptor(payload, media_type):
    return {"mediaType": media_type, "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "size": len(payload)}


class OCIDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.resources = {}
        self.blobs = {}
        self.requests = []
        self.processes = []
        self.bad_download = False
        self.download_failure = False
        self.copy_mismatch = False
        self.metadata_mismatch = False
        self.destination_mismatch = False
        self.secret = "test-only-sensitive-value"
        layer = self.add_blob(b"shared layer", "application/vnd.oci.image.layer.v1.tar+gzip")
        children = []
        for kind in ("runtime", "attestation"):
            config = self.add_blob(kind.encode(), "application/vnd.oci.image.config.v1+json")
            manifest = json.dumps({"schemaVersion": 2, "mediaType": OCI_MANIFEST,
                                   "config": config, "layers": [layer]}).encode()
            child = descriptor(manifest, OCI_MANIFEST)
            self.resources["manifests/" + child["digest"]] = manifest
            children.append(child)
        self.index = json.dumps({"schemaVersion": 2, "mediaType": OCI_INDEX,
                                 "manifests": children}).encode()
        self.digest = descriptor(self.index, OCI_INDEX)["digest"]
        self.resources["manifests/" + self.digest] = self.index

    def add_blob(self, payload, media_type):
        item = descriptor(payload, media_type)
        self.resources["blobs/" + item["digest"]] = payload
        self.blobs[item["digest"]] = payload
        return item

    def load_module(self):
        self.assertTrue(SCRIPT.is_file(), "server-direct OCI downloader is not implemented")
        spec = importlib.util.spec_from_file_location("oci_download", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fetch(self, request, **kwargs):
        self.requests.append(request)
        if request.full_url.startswith("https://ghcr.io/token?"):
            return io.BytesIO(json.dumps({"token": self.secret}).encode())
        key = request.full_url.split("/v2/test/backend/", 1)[-1]
        payload = self.resources[key]
        if self.metadata_mismatch:
            payload += b" "
        return io.BytesIO(payload)

    def process(self, command, **kwargs):
        self.processes.append((command, kwargs))
        if command[0] == "aria2c":
            job = {}
            for line in kwargs["input"].splitlines() + ["https://end"]:
                if line.startswith("https://"):
                    if job:
                        path = Path(job["dir"]) / job["out"]
                        content = self.resources["blobs/sha256:" + job["out"]]
                        path.write_bytes(b"corrupt" if self.bad_download else
                                         content[:1] if self.download_failure else content)
                    job = {}
                elif "=" in line:
                    key, value = line.strip().split("=", 1)
                    job[key] = value
            if self.download_failure:
                raise subprocess.CalledProcessError(1, command, stderr=self.secret)
        elif command[:2] == ["skopeo", "copy"]:
            output = command[command.index("--digestfile") + 1]
            Path(output).write_text("sha256:" + "0" * 64 if self.copy_mismatch else self.digest)
        elif command[:2] == ["skopeo", "inspect"]:
            return subprocess.CompletedProcess(command, 0,
                                               stdout=b"tampered" if self.destination_mismatch else self.index,
                                               stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    def download(self, module=None):
        module = module or self.load_module()
        with patch.object(module.urllib.request, "urlopen", side_effect=self.fetch), \
                patch.object(module.subprocess, "run", side_effect=self.process):
            layout = module.download_image("ghcr.io/test/backend", self.digest, self.cache,
                                           username="test", password=self.secret)
            return layout

    def test_complete_index_and_attestations_are_preserved(self):
        layout = self.download()
        index = json.loads((layout / "index.json").read_text())
        self.assertEqual(index["manifests"][0]["digest"], self.digest)
        self.assertEqual((layout / "blobs/sha256" / self.digest[7:]).read_bytes(), self.index)
        for identity, payload in self.blobs.items():
            self.assertEqual((layout / "blobs/sha256" / identity[7:]).read_bytes(), payload)
        downloads = [item for item in self.processes if item[0][0] == "aria2c"]
        self.assertEqual(len(downloads), 1)
        command, kwargs = downloads[0]
        self.assertIn("--continue=true", command)
        self.assertIn("--check-integrity=true", command)
        self.assertIn("--max-concurrent-downloads=8", command)
        self.assertIn("--split=16", command)
        self.assertIn("--max-connection-per-server=16", command)
        self.assertGreater(kwargs["timeout"], 3500)
        self.assertNotIn(self.secret, " ".join(command))
        self.assertEqual(kwargs["input"].count("https://ghcr.io/v2/test/backend/blobs/"), 3)
        self.assertIn("checksum=sha-256=", kwargs["input"])

    def test_valid_cache_avoids_downloading_blobs_again(self):
        self.download()
        self.processes.clear()
        self.download()
        self.assertFalse(self.processes)

    def test_cache_metrics_count_only_verified_blob_bytes(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.download()
        total = sum(map(len, self.blobs.values()))
        self.assertIn("cache_verified_bytes=0", output.getvalue())
        self.assertIn(f"download_required_bytes={total}", output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            self.download()
        self.assertIn(f"cache_verified_bytes={total}", output.getvalue())
        self.assertIn("download_required_bytes=0", output.getvalue())

    def test_timeout_is_retryable_without_exposing_subprocess_output(self):
        module = self.load_module()
        with patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                "aria2c", 1, output=self.secret)), self.assertRaises(module.RetryableDownloadError) as caught:
            module.run(["aria2c"])
        self.assertNotIn(self.secret, str(caught.exception))
        with patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(
                1, "aria2c", stderr=self.secret)), self.assertRaises(module.DownloadError) as caught:
            module.run(["aria2c"])
        self.assertNotIsInstance(caught.exception, module.RetryableDownloadError)
        with patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                "skopeo", 1)), self.assertRaises(module.DownloadError) as caught:
            module.run(["skopeo"])
        self.assertNotIsInstance(caught.exception, module.RetryableDownloadError)

    def test_corrupt_cache_is_downloaded_again(self):
        layout = self.download()
        identity = next(iter(self.blobs))
        (layout / "blobs/sha256" / identity[7:]).write_bytes(b"tampered")
        self.processes.clear()
        self.download()
        self.assertEqual((layout / "blobs/sha256" / identity[7:]).read_bytes(), self.blobs[identity])
        self.assertEqual(self.processes[0][1]["input"].count("https://"), 1)

    def test_interrupted_blob_is_not_mistaken_for_complete_cache(self):
        layout = self.download()
        identity = next(iter(self.blobs))
        control = layout / "blobs/sha256" / (identity[7:] + ".aria2")
        control.write_bytes(b"resume-state")
        self.processes.clear()
        # aria2 removes its control file after completing the resumed transfer.
        original = self.process
        def resumed(command, **kwargs):
            result = original(command, **kwargs)
            if command[0] == "aria2c":
                control.unlink()
            return result
        module = self.load_module()
        with patch.object(module.urllib.request, "urlopen", side_effect=self.fetch), \
                patch.object(module.subprocess, "run", side_effect=resumed):
            module.download_image("ghcr.io/test/backend", self.digest, self.cache)
        self.assertEqual(len(self.processes), 1)

    def test_downloaded_blob_mismatch_is_rejected(self):
        self.bad_download = True
        module = self.load_module()
        with self.assertRaises(module.DownloadError):
            self.download(module)

    def test_untrusted_manifest_is_rejected_before_blob_download(self):
        self.metadata_mismatch = True
        module = self.load_module()
        with self.assertRaises(module.DownloadError):
            self.download(module)
        self.assertFalse(self.processes)

    def test_failed_download_retains_cache_and_does_not_expose_token(self):
        self.download_failure = True
        module = self.load_module()
        with self.assertRaises(module.DownloadError) as error:
            self.download(module)
        self.assertNotIn(self.secret, str(error.exception))
        self.assertTrue(any(self.cache.rglob("blobs/sha256/*")))
        self.download_failure = False
        self.download(module)

    def test_retry_refreshes_pull_token_and_resumes_only_missing_blobs(self):
        module = self.load_module()
        attempts = []
        original = self.process
        def interrupted(command, **kwargs):
            if command[0] == "aria2c":
                attempts.append(kwargs["input"])
                if len(attempts) == 1:
                    # One blob completed before the repository token expired.
                    first = next(iter(self.blobs))
                    path = self.cache / "blobs/sha256" / first[7:]
                    path.write_bytes(self.blobs[first])
                    raise subprocess.CalledProcessError(1, command)
            return original(command, **kwargs)
        with patch.object(module.urllib.request, "urlopen", side_effect=self.fetch), \
                patch.object(module.subprocess, "run", side_effect=interrupted):
            module.download_image("ghcr.io/test/backend", self.digest, self.cache,
                                  username="test", password=self.secret)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[1].count("https://"), 2)
        self.assertEqual(sum("/token?" in item.full_url for item in self.requests), 2)

    def test_private_registry_authentication_stays_in_memory(self):
        self.download()
        auth = self.requests[0].get_header("Authorization")
        self.assertTrue(auth.startswith("Basic "))
        self.assertIn("scope=repository%3Atest%2Fbackend%3Apull", self.requests[0].full_url)
        self.assertTrue(all(self.secret.encode() not in item.read_bytes()
                            for item in self.cache.rglob("*") if item.is_file()))

    def test_local_registry_copy_preserves_digest_and_checks_destination(self):
        module = self.load_module()
        layout = self.download(module)
        with patch.object(module.subprocess, "run", side_effect=self.process):
            module.mirror_image(layout, self.digest, "127.0.0.1:5000/backend:release")
        copy = self.processes[-2][0]
        self.assertIn("--all", copy)
        self.assertIn("--preserve-digests", copy)
        self.assertTrue(copy[-2].startswith("oci:"))
        self.assertEqual(copy[-1], "docker://127.0.0.1:5000/backend:release")

    def test_local_registry_digest_mismatch_is_rejected(self):
        module = self.load_module()
        layout = self.download(module)
        self.copy_mismatch = True
        with patch.object(module.subprocess, "run", side_effect=self.process), \
                self.assertRaises(module.DownloadError):
            module.mirror_image(layout, self.digest, "127.0.0.1:5000/backend:release")

    def test_destination_bytes_must_match_not_just_digest_file(self):
        module = self.load_module()
        layout = self.download(module)
        self.destination_mismatch = True
        with patch.object(module.subprocess, "run", side_effect=self.process), \
                self.assertRaises(module.DownloadError):
            module.mirror_image(layout, self.digest, "127.0.0.1:5000/backend:release")

    def test_distribution_bootstrap_checks_layers_before_adopting_image(self):
        module = self.load_module()
        config = self.add_blob(json.dumps({"os": "linux", "architecture": "amd64",
                                          "rootfs": {"diff_ids": ["sha256:" + "a" * 64]}}).encode(),
                               "application/vnd.oci.image.config.v1+json")
        manifest = json.dumps({"schemaVersion": 2, "mediaType": OCI_MANIFEST,
                               "config": config, "layers": []}).encode()
        child = descriptor(manifest, OCI_MANIFEST)
        child["platform"] = {"os": "linux", "architecture": "amd64"}
        self.resources["manifests/" + child["digest"]] = manifest
        self.index = json.dumps({"schemaVersion": 2, "mediaType": OCI_INDEX,
                                 "manifests": [child]}).encode()
        self.digest = descriptor(self.index, OCI_INDEX)["digest"]
        self.resources["manifests/" + self.digest] = self.index
        def request(request, **kwargs):
            url = request.full_url
            if "/token?" in url:
                return io.BytesIO(b'{"token": "anonymous-token"}')
            return io.BytesIO(self.resources[url.split("/v2/library/registry/")[1]])
        def process(command, **kwargs):
            if command[:2] == ["docker", "inspect"]:
                raise subprocess.CalledProcessError(1, command)
            if command[:2] == ["docker", "image"]:
                payload = json.dumps([{"Id": "sha256:" + "9" * 64, "Os": "linux",
                                       "Architecture": "amd64", "RootFS": {"Layers": ["changed"]}}]).encode()
                return subprocess.CompletedProcess(command, 0, stdout=payload)
            return self.process(command, **kwargs)
        with patch.object(module, "REGISTRY_DIGEST", self.digest), \
                patch.object(module.urllib.request, "urlopen", side_effect=request), \
                patch.object(module.subprocess, "run", side_effect=process), \
                self.assertRaises(module.DownloadError):
            module.bootstrap_registry(self.cache)
        self.assertFalse(any(item[0][0] == "bash" for item in self.processes))

    def test_managed_registry_reuse_does_not_require_docker_hub_connectivity(self):
        module = self.load_module()
        image_id = "sha256:" + "9" * 64
        calls = []
        def process(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=(image_id + "\n").encode())
        with patch.object(module.subprocess, "run", side_effect=process), \
                patch.object(module.urllib.request, "urlopen", side_effect=AssertionError("network not needed")):
            module.bootstrap_registry(self.cache)
        self.assertTrue(any(command[0] == "bash" for command in calls))

    def test_invalid_source_or_digest_never_contacts_registry(self):
        module = self.load_module()
        for source, digest in (("https://evil.invalid/image", self.digest),
                               ("ghcr.io/test/backend", "not-a-digest")):
            with self.subTest(source=source), self.assertRaises(module.DownloadError):
                module.download_image(source, digest, self.cache)
        self.assertFalse(self.requests)


if __name__ == "__main__":
    unittest.main()
