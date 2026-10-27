import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_upstream as upstream


def release(version, **changes):
    value = {"tag_name": f"v{version}", "draft": False, "prerelease": False,
             "html_url": f"https://github.com/caddyserver/caddy/releases/tag/v{version}",
             "published_at": "2026-01-01T00:00:00Z", "body": f"Notes for {version}"}
    value.update(changes)
    return value


class Response(io.BytesIO):
    def __init__(self, payload, link=""):
        super().__init__(json.dumps(payload).encode())
        self.headers = {"Link": link}


class ReleaseTests(unittest.TestCase):
    def test_semantic_order(self):
        versions = upstream.stable_releases([release("2.9.9"), release("2.10.1"), release("2.10.10")])
        self.assertEqual(max(versions, key=upstream.version_tuple), "2.10.10")

    def test_excludes_unstable_and_other_majors(self):
        releases = [release("2.1.0"), release("2.99.0", draft=True),
                    release("2.98.0", prerelease=True), release("2.20.0-rc.1"),
                    release("2.21.0-beta.1"), release("2.22.0+dev"), release("3.0.0"),
                    release("1.0.0"), release("2.01.0"), release("2.30.0", prerelease=None)]
        self.assertEqual(list(upstream.stable_releases(releases)), ["2.1.0"])

    def test_empty_and_bad_metadata_fail(self):
        for values in ([], [release("2.0.0-rc.1")], [release("2.1.0", html_url="https://evil.example/")],
                       [release("2.1.0", published_at=None)]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                upstream.stable_releases(values)

    def test_pagination_and_authentication(self):
        requests = []
        def opener(request, **kwargs):
            requests.append(request)
            if len(requests) == 1:
                return Response([release("2.9.0")], '<https://api.github.com/repositories/29207621/releases?per_page=100&page=2>; rel="next"')
            return Response([release("2.10.0")])
        values = upstream.fetch_releases("test-token", opener)
        self.assertEqual(len(values), 2)
        self.assertTrue(requests[1].full_url.endswith("page=2"))
        self.assertEqual(requests[1].get_header("Authorization"), "Bearer test-token")

    def test_no_authentication_when_missing(self):
        def opener(request, **kwargs):
            self.assertIsNone(request.get_header("Authorization"))
            return Response([])
        self.assertEqual(upstream.fetch_releases(opener=opener), [])

    def test_unsafe_and_cyclic_pagination(self):
        for link in ("https://evil.example/", upstream.API,
                     "https://api.github.com/repos/other/project/releases"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                upstream.fetch_releases("token", lambda *a, **kw: Response([], f'<{link}>; rel="next"'))

    def test_rate_limit_fails_without_sleeping(self):
        for code in (403, 429):
            def opener(*args, **kwargs):
                raise HTTPError(upstream.API, code, "limit", {"X-RateLimit-Reset": "123"}, None)
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, "reset epoch=123"):
                upstream.fetch_releases(opener=opener, sleep=lambda _: self.fail("unexpected retry"))

    def test_transient_errors_are_retried(self):
        attempts = []
        def opener(*args, **kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise HTTPError(upstream.API, 503, "unavailable", {}, None)
            return Response([release("2.1.0")])
        self.assertEqual(len(upstream.fetch_releases(opener=opener, sleep=lambda _: None)), 1)
        self.assertEqual(len(attempts), 3)

    def test_api_failures(self):
        for error in (URLError("offline"), HTTPError(upstream.API, 404, "missing", {}, None)):
            def opener(*args, **kwargs):
                raise error
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                upstream.fetch_releases(opener=opener, sleep=lambda _: None)

    def test_invalid_json_and_schema(self):
        with self.assertRaises(ValueError):
            upstream.fetch_releases(opener=lambda *a, **kw: io.BytesIO(b"not JSON"))
        for payload in ({"message": "error"}, ["invalid"]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                upstream.fetch_releases(opener=lambda *a, **kw: Response(payload))


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.releases = [release("2.9.0"), release("2.10.1")]

    def update(self, values=None, day="2026-10-26", force=False):
        return upstream.update(self.root, values if values is not None else self.releases, day, force)

    def snapshot(self):
        return {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_bootstrap_and_idempotence(self):
        self.assertEqual(self.update()["version"], "2.10.1")
        before = self.snapshot()
        self.assertEqual(self.update()["changed"], "false")
        self.assertEqual(before, self.snapshot())
        history = json.loads((self.root / "upstream/state.json").read_text())["history"]
        self.assertEqual([item["version"] for item in history], ["2.10.1"])

    def test_api_release_notes_line_endings_are_normalized(self):
        values = [release("2.10.1", body="First line\r\n\r\nSecond line\r\n")]
        self.update(values)
        notes = (self.root / "upstream/CADDY_CHANGES.md").read_bytes()
        self.assertNotIn(b"\r", notes)
        self.assertIn(b"First line\n\nSecond line\n", notes)
        self.assertEqual(self.update(values)["changed"], "false")

    def test_new_versions_preserve_notes_and_history(self):
        self.update()
        result = self.update(self.releases + [release("2.11.1"), release("2.11.2")])
        self.assertEqual(result["version_changed"], "true")
        notes = (self.root / "upstream/CADDY_CHANGES.md").read_text()
        for version in ("2.10.1", "2.11.1", "2.11.2"):
            self.assertEqual(notes.count(f"## v{version}\n"), 1)
        self.assertEqual(self.update(self.releases + [release("2.11.1"), release("2.11.2")])["changed"], "false")

    def test_no_downgrade_or_partial_mutation(self):
        self.update()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "downgrade"):
            self.update([release("2.9.0")])
        self.assertEqual(before, self.snapshot())

    def test_unavailable_api_does_not_write_files_or_outputs(self):
        self.update()
        before = self.snapshot()
        output = self.root / "outputs"
        with patch.object(sys, "argv", ["update_upstream.py", "--root", str(self.root)]), \
                patch.object(upstream, "fetch_releases", side_effect=RuntimeError("offline")), \
                patch.dict(upstream.os.environ, {"GITHUB_OUTPUT": str(output)}):
            self.assertEqual(upstream.main(), 1)
        self.assertFalse(output.exists())
        self.assertEqual(before, self.snapshot())

    def test_check_date_is_recorded_without_forcing_rebuild(self):
        self.update()
        (self.root / "upstream/publication.json").write_text(json.dumps({"version": "2.10.1"}))
        result = self.update(day="2026-11-02")
        self.assertEqual(result["changed"], "true")
        self.assertEqual(result["rebuild_required"], "false")
        self.assertEqual(self.update(force=True)["rebuild_required"], "true")

    def test_failed_publication_is_retried(self):
        self.update()
        self.assertEqual(self.update()["rebuild_required"], "true")

    def test_inconsistent_tracking_fails(self):
        self.update()
        (self.root / "upstream/caddy-version.txt").write_text("2.0.0\n")
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.update()

    def test_newer_publication_blocks_downgrade_before_writes(self):
        self.update()
        (self.root / "upstream/publication.json").write_text(json.dumps({"version": "2.99.0"}))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "older than"):
            self.update(day="2026-11-02")
        self.assertEqual(before, self.snapshot())

    def test_github_outputs(self):
        output = self.root / "outputs"
        with patch.object(sys, "argv", ["update_upstream.py", "--root", str(self.root)]), \
                patch.object(upstream, "fetch_releases", return_value=self.releases), \
                patch.dict(upstream.os.environ, {"GITHUB_OUTPUT": str(output)}):
            self.assertEqual(upstream.main(), 0)
        self.assertIn("version=2.10.1\n", output.read_text())
        self.assertIn("rebuild_required=true\n", output.read_text())


if __name__ == "__main__":
    unittest.main()
