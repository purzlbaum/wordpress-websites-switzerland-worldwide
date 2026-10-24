# WordPress Websites from Switzerland and around the world

We want to build a great archive of all WordPress projects. Thanks for contributing and adding yours! Please submit changes and additions to this repository via Patch or Pull Request and keep to the formatting and alphabetical order in the existing files.

Don't have a Github account, or you're not sure how to contribute? Just send an email to github@wpswitzerland.ch and we'll take it from there.

## Files
* [WordPress agencies and developers in Switzerland](https://github.com/WPSwitzerland/wordpress-websites-switzerland-worldwide/blob/master/wordpress-developers-and-agencies-switzerland.md)
* [WordPress meetups in Switzerland](https://github.com/WPSwitzerland/wordpress-websites-switzerland-worldwide/blob/master/wordpress-meetups-switzerland.md)
* [Non-agency websites in Switzerland which are powered by WordPress](https://github.com/WPSwitzerland/wordpress-websites-switzerland-worldwide/blob/master/wordpress-sites-in-switzerland.md)
* [Outstanding websites around the world which are powered by WordPress](https://github.com/WPSwitzerland/wordpress-websites-switzerland-worldwide/blob/master/wordpress-sites-worldwide.md)

## Website checks

The **Audit WordPress websites** GitHub Actions workflow checks the Swiss and worldwide website lists on the first day of each month at 07:23 UTC. You can also start it from **Actions → Audit WordPress websites → Run workflow** once the workflow is on the default branch.

Each run provides a summary and a downloadable artifact containing JSON and TXT reports with HTTP status codes, redirect destinations and WordPress evidence. Artifacts are retained for 90 days, subject to repository policy. Download reports you want to keep or annotate. Findings are for manual review; the workflow does not change the lists. GitHub may disable scheduled workflows in public repositories after 60 days without repository activity; re-enable the workflow in Actions if needed. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

To run the checks locally with Python 3.9+ and curl:

```bash
python3 scripts/audit_wordpress.py
```

Each run writes to a new directory in `audits/runs/`, preserving previous reports and annotations. These generated directories are ignored by Git. You can pass other Markdown filenames or choose a report location:

```bash
python3 scripts/audit_wordpress.py wordpress-meetups-switzerland.md --output-dir /tmp/wordpress-audits
```

Annotate individual entries in a downloaded TXT report with `ENTSCHEID: entfernen`, `ENTSCHEID: behalten – …`, `ENTSCHEID: URL ersetzen durch https://…` or `ENTSCHEID: nochmals prüfen – …`. Apply decisions manually using the URL and filename; report line numbers refer to the audited version of each file. Missing WordPress markers and failed requests alone do not establish that a site changed its CMS.

Maintenance and review rules are documented in [AGENTS.md](AGENTS.md).
