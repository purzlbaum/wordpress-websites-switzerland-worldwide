import contextlib
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import audit_wordpress as audit


def response(body="", status=200, url="https://example.test/", exit_code=0):
    return {
        "requested_url": url, "http_status": status, "final_url": url,
        "error": "", "curl_exit": exit_code, "headers": "", "body": body,
    }


class AuditTests(unittest.TestCase):
    def test_error_page_with_wordpress_assets_is_not_confirmed(self):
        with mock.patch.object(audit, "fetch", return_value=response(
                '<script src="/wp-includes/script.js"></script>', status=403)) as fetch:
            result = audit.audit("https://example.test/")
        self.assertEqual(result["status"], "unreachable_or_http_error")
        self.assertEqual(fetch.call_count, 1)

    def test_rest_probe_requires_an_actual_wordpress_namespace_list(self):
        for body in ('<html>Generic fallback page</html>', '{"namespaces": "wp/v2"}',
                     '{"namespaces": ["wp/v2-something-else"]}'):
            with self.subTest(body=body), mock.patch.object(audit, "fetch", side_effect=[
                    response(), response(body)]):
                self.assertEqual(audit.audit("https://example.test/")["status"], "unclear")

    def test_headless_wordpress_rest_api_is_detected(self):
        with mock.patch.object(audit, "fetch", side_effect=[
                response(), response('{"namespaces": ["wp/v2"]}')]):
            result = audit.audit("https://example.test/")
        self.assertEqual(result["status"], "wordpress_detected")
        self.assertIn("namespace wp/v2", result["evidence"][0])

    def test_http_failure_can_be_recovered_over_https(self):
        with mock.patch.object(audit, "fetch", side_effect=[
                response(status=403, url="http://example.test/"),
                response('<meta name="generator" content="WordPress 7.0">')]):
            result = audit.audit("http://example.test/")
        self.assertEqual(result["status"], "wordpress_detected")
        self.assertEqual(result["final_url"], "https://example.test/")
        self.assertEqual(len(result["attempts"]), 2)

    def test_other_platform_requires_no_wordpress_evidence(self):
        with mock.patch.object(audit, "fetch", side_effect=[
                response('<html data-wf-site="abc">'), response("{}")]):
            result = audit.audit("https://example.test/")
        self.assertEqual(result["status"], "other_platform_detected")
        self.assertEqual(result["other_platform_signals"], ["Webflow"])
        with mock.patch.object(audit, "fetch", return_value=response(
                '<html data-wf-site="abc"><script src="/wp-includes/a.js"></script>')):
            self.assertEqual(audit.audit("https://example.test/")["status"], "wordpress_detected")

    def test_repeated_runs_preserve_reports_and_human_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            content = '<meta name="generator" content="WordPress 7.0">'
            with mock.patch.object(audit, "fetch", return_value=response(content)):
                result = audit.audit("https://example.test/")
            result["sources"] = [{"file": "sites.md", "line": 1, "label": "Example"}]
            with contextlib.redirect_stdout(io.StringIO()):
                first = audit.write_report([result], [root / "sites.md"], root)
                report = first / "report.txt"
                report.write_text(report.read_text(encoding="utf-8") + "ENTSCHEID: behalten\n", encoding="utf-8")
                preserved = report.read_bytes()
                second = audit.write_report([result], [root / "sites.md"], root)
            self.assertNotEqual(first, second)
            self.assertEqual(report.read_bytes(), preserved)
            data = json.loads((second / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"], {"wordpress_detected": 1})
            self.assertTrue((second / "summary.md").is_file())

    def test_default_cli_scope_deduplicates_urls_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for filename in audit.DEFAULT_FILES:
                (root / filename).write_text("- [Example](https://example.test/)\n", encoding="utf-8")
            (root / "README.md").write_text("[Skip](https://skip.test/)", encoding="utf-8")
            arguments = ["audit_wordpress.py", "--output-dir", str(root / "reports")]
            with mock.patch.object(audit, "ROOT", root), mock.patch.object(sys, "argv", arguments), \
                    mock.patch.object(audit, "fetch", return_value=response(
                        '<meta name="generator" content="WordPress 7.0">')) as fetch, \
                    contextlib.redirect_stdout(io.StringIO()):
                audit.main()
            self.assertEqual(fetch.call_count, 1)
            data = json.loads(next((root / "reports").glob("*/report.json")).read_text(encoding="utf-8"))
            self.assertEqual(len(data["results"]), 1)
            self.assertEqual(len(data["results"][0]["sources"]), 2)


class FetchTests(unittest.TestCase):
    def test_curl_follows_redirects_and_records_http_errors(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/blocked")
                else:
                    self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Test body")

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            result = audit.fetch(base + "/redirect")
            self.assertEqual(result["http_status"], 403)
            self.assertEqual(result["final_url"], base + "/blocked")
            self.assertEqual(result["body"], "Test body")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
