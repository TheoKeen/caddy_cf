#!/usr/bin/env python3
"""Track official stable Caddy 2 releases using only the Python standard library."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API = "https://api.github.com/repos/caddyserver/caddy/releases?per_page=100"
VERSION = re.compile(r"2\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version_tuple(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"Invalid stable Caddy 2 version: {value!r}")
    return tuple(map(int, value.split(".")))


def fetch_releases(token=None, opener=urlopen, sleep=time.sleep):
    releases, visited = [], set()
    url = API
    while url:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.netloc != "api.github.com"
                # GitHub canonicalizes pagination links to the immutable repository ID.
                or parsed.path not in ("/repos/caddyserver/caddy/releases", "/repositories/29207621/releases")
                or url in visited):
            raise ValueError("Unsafe or cyclic GitHub pagination link")
        visited.add(url)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "caddy_cf-updater",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for attempt in range(3):
            try:
                with opener(Request(url, headers=headers), timeout=30) as response:
                    page = json.load(response)
                    links = response.headers.get("Link", "")
                break
            except HTTPError as error:
                error.close()
                if error.code in (403, 429):
                    reset = error.headers.get("X-RateLimit-Reset", "unknown")
                    retry = error.headers.get("Retry-After", "unknown")
                    raise RuntimeError(f"GitHub rate/access limit (HTTP {error.code}); "
                                       f"reset epoch={reset}, retry-after={retry}") from error
                if error.code not in (500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f"GitHub API returned HTTP {error.code}") from error
                sleep(2 ** attempt)
            except (URLError, TimeoutError) as error:
                if attempt == 2:
                    raise RuntimeError("GitHub API unavailable after three attempts") from error
                sleep(2 ** attempt)
        if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
            raise ValueError("Invalid GitHub releases response")
        releases.extend(page)
        next_links = re.findall(r'<([^>]+)>;\s*rel="next"', links)
        if len(next_links) > 1:
            raise ValueError("Ambiguous GitHub pagination")
        url = next_links[0] if next_links else None
    return releases


def stable_releases(releases):
    stable = {}
    for release in releases:
        # Missing flags are not sufficient evidence of a stable release.
        if release.get("draft") is not False or release.get("prerelease") is not False:
            continue
        tag = release.get("tag_name", "")
        if not isinstance(tag, str) or not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
            continue
        version = tag[1:]
        if release.get("html_url") != f"https://github.com/caddyserver/caddy/releases/tag/{tag}":
            raise ValueError(f"Unexpected release URL for {tag}")
        if not release.get("published_at") or not isinstance(release.get("body", ""), (str, type(None))):
            raise ValueError(f"Incomplete release metadata for {tag}")
        stable[version] = release
    if not stable:
        raise ValueError("GitHub returned no stable Caddy 2 releases")
    return stable


def write_if_changed(path, content):
    if path.exists() and path.read_bytes() == content.encode("utf-8"):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return True


def update(root, releases, checked_on, force_rebuild=False):
    stable = stable_releases(releases)
    latest = max(stable, key=version_tuple)
    directory = root / "upstream"
    version_path = directory / "caddy-version.txt"
    state_path = directory / "state.json"
    current = version_path.read_text().strip() if version_path.exists() else None
    state = json.loads(state_path.read_text()) if state_path.exists() else {"history": []}
    if current:
        version_tuple(current)
        if state.get("version") != current:
            raise ValueError("Tracked version and state.json disagree")
        if version_tuple(latest) < version_tuple(current):
            raise ValueError(f"Refusing downgrade from {current} to {latest}")
    elif state.get("history"):
        raise ValueError("Missing tracked version for existing history")
    history = state["history"]
    known = {item["version"] for item in history}
    additions = sorted((version for version in stable if version not in known
                        and (version == latest if current is None
                             else version_tuple(version) > version_tuple(current))), key=version_tuple)
    notes_path = directory / "CADDY_CHANGES.md"
    notes = notes_path.read_text() if notes_path.exists() else "# Upstream Caddy releases\n\nRecorded from the official GitHub releases API.\n"
    for version in additions:
        release = stable[version]
        release_notes = (release.get("body") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        history.append({"version": version, "tag": release["tag_name"],
                        "url": release["html_url"], "published_at": release["published_at"],
                        "recorded_on": checked_on})
        notes += (f"\n## {release['tag_name']}\n\n"
                  f"Published: {release['published_at']}\n\n"
                  f"Source: {release['html_url']}\n\n{release_notes}\n")
    state.update({"schema": 1, "version": latest, "checked_on": checked_on,
                  "source": API, "history": history})
    # Validate everything, including the last publication, before writing any files.
    published_path = directory / "publication.json"
    published = json.loads(published_path.read_text()) if published_path.exists() else {}
    if published.get("version") and version_tuple(published["version"]) > version_tuple(latest):
        raise ValueError("Tracked release is older than the published image")
    rebuild = force_rebuild or latest != current or published.get("version") != latest
    changed = False
    for path, content in ((version_path, latest + "\n"), (notes_path, notes),
                          (state_path, json.dumps(state, indent=2) + "\n")):
        changed = write_if_changed(path, content) or changed
    return {"version": latest, "version_changed": str(latest != current).lower(),
            "changed": str(changed).lower(), "rebuild_required": str(rebuild).lower()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Refresh builder, plugin and dependencies even without a Caddy release")
    args = parser.parse_args()
    try:
        releases = fetch_releases(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        outputs = update(args.root, releases, datetime.now(timezone.utc).date().isoformat(), args.force_rebuild)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                for key, value in outputs.items():
                    output.write(f"{key}={value}\n")
        print(json.dumps(outputs))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(f"Upstream update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
