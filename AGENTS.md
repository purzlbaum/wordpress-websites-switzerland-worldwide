# Repository maintenance

Keep the existing Markdown format, category structure and alphabetical ordering when editing the lists. Remove empty categories after removing their final entry.

## Website audits

- Run `python3 scripts/audit_wordpress.py` to check `wordpress-sites-in-switzerland.md` and `wordpress-sites-worldwide.md`. Other Markdown files can be passed explicitly as positional arguments.
- The script requires Python 3.9+ and curl, with no third-party Python packages. Run `python3 -m unittest discover -s tests -v` and `git diff --check` after changing audit behavior.
- Every run creates a unique directory inside `audits/runs/`, containing `report.json`, `report.txt` and `summary.md`. Use `--output-dir /path/to/reports` to select a different parent directory.
- Preserve existing reports and human annotations. Never regenerate or overwrite a report containing review decisions. The historical reports in `audits/` refer to the files at the time of that audit; their line numbers can become outdated.
- Only change list entries after a human decision or an explicit instruction to clean up the lists. When applying annotated decisions, match the URL and source file rather than relying on old line numbers. Leave entries without decisions unchanged.
- WordPress asset references, generator tags and REST API discovery are evidence, not guarantees about the current backend. Static copies and third-party assets can retain these markers.
- Missing WordPress markers do not prove that a website stopped using WordPress. Other platforms can coexist with WordPress, especially in headless setups. Review the listed path and redirect destination as well as the domain.
- DNS errors, timeouts, TLS errors, HTTP errors and bot protection are reachability findings, not CMS classifications. Retry or review them manually before deciding whether to remove an entry.
- External profiles, social links, event platforms and photo galleries are not expected to run WordPress. An agency or developer can offer WordPress services while using another platform for their own website.
- The GitHub Actions workflow runs monthly and can be started manually. It uploads reports and writes a run summary. It must not automatically edit lists, commit changes, open issues or create pull requests.

## Commit messages

When asked for a commit message, always inspect the actual changes with `git diff`. Do not modify files while preparing the message.

Use an appropriate Conventional Commits type (`feat`, `fix`, `refactor`, `style`, `docs`, `chore` or `perf`). The first line must concisely describe the primary purpose in the imperative, without unnecessary implementation details. Follow it with a concise list of meaningful changes.

Return only one fenced code block containing the commit message, with no introduction, status update or explanation before or after it:

```text
chore: audit and maintain WordPress website lists
- remove manually reviewed outdated entries and empty categories
- add scheduled URL checks and reports for manual review
```
