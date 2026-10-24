#!/usr/bin/env python3
"""Read-only HTTP audit of Markdown links. Uses Python's standard library and curl."""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import subprocess
import tempfile
import urllib.parse
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_FILES = ("wordpress-sites-in-switzerland.md", "wordpress-sites-worldwide.md")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
UA = "Mozilla/5.0 (compatible; WordPressDirectoryAudit/1.0)"


def fetch(url):
    with tempfile.TemporaryDirectory(prefix="wp-audit-") as directory:
        headers = pathlib.Path(directory) / "headers"
        body = pathlib.Path(directory) / "body"
        proc = subprocess.run([
            "curl", "--silent", "--show-error", "--location", "--compressed",
            "--max-redirs", "8", "--connect-timeout", "8", "--max-time", "22",
            "--max-filesize", "6000000", "--proto", "=http,https",
            "--proto-redir", "=http,https", "--user-agent", UA,
            "--dump-header", str(headers), "--output", str(body),
            "--write-out", "%{http_code}\n%{url_effective}", url,
        ], capture_output=True, text=True)
        parts = proc.stdout.splitlines()
        return {
            "requested_url": url, "http_status": int(parts[0]) if parts else 0,
            "final_url": parts[1] if len(parts) > 1 else url,
            "error": proc.stderr.strip(), "curl_exit": proc.returncode,
            "headers": headers.read_text(errors="replace") if headers.exists() else "",
            "body": body.read_text(errors="replace") if body.exists() else "",
        }


def signals(response):
    body = response["body"]
    evidence = []
    patterns = [
        ("WordPress asset URL", r'''(?:src|href)\s*=\s*["'][^"']*/wp-(?:content|includes)/[^"']+'''),
        ("WordPress generator", r'''<meta\b(?=[^>]*\bname\s*=\s*["']generator["'])(?=[^>]*\bcontent\s*=\s*["']WordPress\b)[^>]*>'''),
        ("WordPress REST discovery", r'''<link\b(?=[^>]*https://api\.w\.org/)[^>]*>'''),
        ("WordPress.com assets", r'''(?:src|href)\s*=\s*["'][^"']*(?:s[0-9]\.wp\.com|widgets\.wp\.com)/[^"']+'''),
    ]
    for label, pattern in patterns:
        match = re.search(pattern, body, re.I)
        if match:
            evidence.append(label + ": " + match.group(0)[:280])
    if re.search(r'^link:.*https://api\.w\.org/', response["headers"], re.I | re.M):
        evidence.append("WordPress REST discovery in HTTP Link header")
    platforms = []
    for label, pattern in [
        ("Webflow", r'data-wf-(?:site|page)\s*='),
        ("Wix", r'(?:static\.wixstatic\.com|wix-thunderbolt|name=["\']generator["\'][^>]*Wix)'),
        ("Squarespace", r'(?:static[0-9]*\.squarespace\.com|name=["\']generator["\'][^>]*Squarespace)'),
        ("Shopify", r'(?:cdn\.shopify\.com/s/|Shopify\.shop\s*=)'),
        ("TYPO3", r'(?:<meta[^>]+content=["\']TYPO3|/typo3temp/|/typo3conf/)'),
        ("Drupal", r'(?:<meta[^>]+content=["\']Drupal|data-drupal-selector=|/sites/default/files/)'),
        ("Joomla", r'<meta[^>]+content=["\']Joomla'),
        ("Framer", r'(?:name=["\']generator["\'][^>]*Framer|data-framer-generated-page)'),
        ("Ghost", r'<meta[^>]+content=["\']Ghost\b'),
        ("Cloudrexx", r'<meta[^>]+content=["\']cloudrexx'),
        ("Plone", r'(?:<meta[^>]+content=["\']Plone|/\+\+plone\+\+)'),
        ("Weebly", r'(?:cdn[0-9]+\.editmysite\.com/js/|Weebly\.siteName)'),
        ("Statamic", r'/vendor/statamic/frontend/'),
        ("Adobe Experience Manager", r'/etc\.clientlibs/(?:clientlibs/granite|foundation/clientlibs)/'),
        ("Liferay", r'/o/frontend-js-[^/]+/'),
        ("Contentful", r'(?:images|assets|cdn)\.ctfassets\.net/'),
        ("Shopware", r'(?:/themes/Frontend/[^/]+/frontend/|Shopware\.Application)'),
    ]:
        if re.search(pattern, body, re.I):
            platforms.append(label)
    return evidence, platforms


def external_service(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    return any(host == domain or host.endswith("." + domain) for domain in (
        "github.com", "x.com", "twitter.com", "bsky.app", "meetup.com",
        "photos.google.com", "photos.app.goo.gl", "flickr.com", "profiles.wordpress.org",
    ))


def audit(url):
    attempts = []
    response = fetch(url)
    attempts.append(response)
    if url.startswith("http://"):
        secure = "https://" + url[len("http://"):]
        # Retry old HTTP links over HTTPS, including HTTP-only proxy error pages.
        if not (200 <= response["http_status"] < 300 and response["final_url"].startswith("https://")):
            candidate = fetch(secure)
            attempts.append(candidate)
            if candidate["curl_exit"] == 0 and 200 <= candidate["http_status"] < 300:
                response = candidate
    evidence, platforms = signals(response)
    valid = response["curl_exit"] == 0 and 200 <= response["http_status"] < 300
    status = "unclear"
    endpoint = None
    if external_service(url):
        status = "external_service"
    elif not valid:
        status = "unreachable_or_http_error"
    elif evidence:
        status = "wordpress_detected"
    else:
        parsed = urllib.parse.urlsplit(response["final_url"])
        # REST API success requires actual WordPress namespaces, not a generic 200.
        endpoint = fetch(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/wp-json/", "", "")))
        try:
            data = json.loads(endpoint["body"])
            namespaces = data.get("namespaces", []) if isinstance(data, dict) else []
            if (endpoint["curl_exit"] == 0 and endpoint["http_status"] == 200
                    and isinstance(namespaces, list) and "wp/v2" in namespaces):
                evidence.append("WordPress REST API namespace wp/v2: " + endpoint["final_url"])
                status = "wordpress_detected"
        except (ValueError, TypeError):
            pass
        if status == "unclear" and platforms:
            status = "other_platform_detected"
    def metadata(item):
        return {key: value for key, value in item.items() if key not in ("body", "headers")}
    return {
        "url": url, "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status, "http_status": response["http_status"],
        "final_url": response["final_url"], "evidence": evidence,
        "other_platform_signals": platforms, "attempts": [metadata(a) for a in attempts],
        "rest_probe": metadata(endpoint) if endpoint else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Markdown filenames; default: the Swiss and worldwide website lists")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "audits" / "runs",
                        help="Parent directory for a new, unique report directory")
    args = parser.parse_args()
    sources = {}
    paths = [ROOT / name for name in (args.files or DEFAULT_FILES)]
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, url in LINK.findall(line):
                sources.setdefault(url, []).append({"file": path.name, "line": number, "label": label})
    if not sources:
        parser.error("No HTTP(S) Markdown links found in the selected files")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(audit, url): url for url in sources}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            result["sources"] = sources[result["url"]]
            results.append(result)
            print(f'{len(results)}/{len(sources)} {result["status"]} {result["url"]}', flush=True)
    write_report(results, paths, args.output_dir)


def write_report(results, paths, output_dir=None):
    results.sort(key=lambda r: (r["sources"][0]["file"], r["sources"][0]["line"], r["url"]))
    now = datetime.datetime.now(datetime.timezone.utc)
    date = now.date().isoformat()
    parent = pathlib.Path(output_dir) if output_dir is not None else ROOT / "audits" / "runs"
    parent.mkdir(parents=True, exist_ok=True)
    output = pathlib.Path(tempfile.mkdtemp(prefix=now.strftime("%Y-%m-%dT%H-%M-%SZ-"), dir=parent))
    counts = Counter(r["status"] for r in results)
    (output / "report.json").write_text(json.dumps({
        "checked_date_utc": date, "generated_at_utc": now.isoformat(),
        "source_files": [path.name for path in paths],
        "summary": dict(counts), "results": results,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = [
        f"WordPress URL-Prüfung – {date} (UTC)", "",
        f"{len(results)} eindeutige URLs; {sum(len(r['sources']) for r in results)} Verweise.",
        "Geprüfte Quelldateien: " + ", ".join(path.name for path in paths),
        "Originaldateien wurden nicht verändert.", "",
        "Methode: HTTP GET mit Weiterleitungen, gültigem TLS und maximal 22 Sekunden pro Anfrage.",
        "Alte HTTP-Links werden bei Bedarf zusätzlich über HTTPS geprüft.",
        "WordPress-Nachweise: eingebundene WP-Assets, Generator, REST-Discovery oder REST-Namespace wp/v2.",
        "Ohne HTML-Nachweis wird zusätzlich /wp-json/ auf der finalen Domain geprüft.",
        "Andere Plattform: technische Merkmale erkannt, aber kein WordPress-Nachweis. Headless-/Mischbetrieb bleibt möglich.",
        "Unklar bedeutet: kein eindeutiger Nachweis; fehlende Merkmale beweisen keinen Systemwechsel.",
        "Erreichbarkeitsfehler und Sperren sind keine Aussage zum CMS. Keine JavaScript-Ausführung.",
        "Externe Dienste werden aufgerufen, aber nicht als WordPress-Projekte bewertet.",
        "Agentur-/Entwickler-Websites müssen selbst kein WordPress nutzen, um fachlich in die Liste zu passen.",
        "Weiterleitungen, Domainwechsel und REST-Nachweise können auf ein anderes Ziel zeigen; Identität manuell prüfen.",
        "Ein Asset-Nachweis zeigt WordPress-Ressourcen; statische Kopien und fremde Assets sind möglich.", "",
    ]
    titles = {
        "other_platform_detected": "Andere Plattform erkannt – zur Prüfung",
        "unclear": "CMS unklar – manuell prüfen",
        "unreachable_or_http_error": "Nicht erreichbar / HTTP-Fehler / gesperrt",
        "wordpress_detected": "WordPress-Merkmale gefunden",
        "external_service": "Externe Dienste – CMS-Prüfung nicht anwendbar",
    }
    report.extend(["Übersicht", "=" * 72])
    for status, title in titles.items():
        report.append(f"{title}: {counts[status]}")
    for path in paths:
        per_file = Counter(r["status"] for r in results if any(s["file"] == path.name for s in r["sources"]))
        report.extend(["", path.name])
        for status, title in titles.items():
            report.append(f"  {title}: {per_file[status]}")
    report.append("")
    for status, title in titles.items():
        report.extend([f"{title}: {counts[status]}", "=" * 72])
        for result in results:
            if result["status"] != status:
                continue
            refs = "; ".join(f'{s["file"]}:{s["line"]} ({s["label"]})' for s in result["sources"])
            report.extend([refs, f'  URL: {result["url"]}', f'  Ziel: {result["final_url"]} [HTTP {result["http_status"]}]'])
            for item in result["evidence"]:
                report.append("  Nachweis: " + item)
            if result["other_platform_signals"]:
                report.append("  Plattformmerkmale: " + ", ".join(result["other_platform_signals"]))
            for attempt in result["attempts"]:
                if attempt["error"]:
                    report.append("  Abruffehler: " + attempt["error"])
            report.append("")
    (output / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    summary = [
        "## WordPress URL audit", "", f"Checked {len(results)} unique URLs ({now.isoformat()}).", "",
        "| Result | URLs |", "| --- | ---: |",
    ]
    summary.extend(f"| {title} | {counts[status]} |" for status, title in titles.items())
    summary.extend([
        "", "Download the audit artifact for URL details and evidence.",
        "Findings require manual review. Network failures and missing WordPress markers do not prove a CMS change.",
        "The website lists and previous reports were not changed.", "",
    ])
    (output / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    print(json.dumps(dict(counts), ensure_ascii=False), flush=True)
    print(f"Reports: {output}", flush=True)
    return output


if __name__ == "__main__":
    main()
