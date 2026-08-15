#!/usr/bin/env python3
"""Resolve the latest stable X/Twitter base APK download URL from APKPure.

Prints two lines:
  <download_url>
  <version>

Exits non-zero when APKPure is unreachable or no stable release is found.
"""

import re
import sys
import urllib.request

VERSIONS_URL = "https://apkpure.com/x-twitter/com.twitter.android/versions"
DOWNLOAD_URL = "https://d.apkpure.net/b/XAPK/com.twitter.android?versionCode={version_code}"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

VERSION_RE = re.compile(
    r'data-dt-version="([^"]+)"\s+data-dt-versioncode="(\d+)"'
)

ALPHA_BETA_RE = re.compile(r"(?:^|[-.])(?:alpha|beta)(?:[-.]|$)", re.IGNORECASE)
STABLE_SUFFIX_RE = re.compile(r"-release(?:\.0)?$", re.IGNORECASE)


def stable_key(version: str) -> tuple[int, ...]:
    numeric = re.search(r"\d+(?:\.\d+)*", version)
    if numeric is None:
        return (0,)
    return tuple(int(part) for part in numeric.group(0).split("."))


def main() -> int:
    request = urllib.request.Request(VERSIONS_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            page = response.read().decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"[ERROR] Failed to fetch {VERSIONS_URL}: {exc}", file=sys.stderr)
        return 1

    entries = VERSION_RE.findall(page)
    if not entries:
        print("[ERROR] No X release found on the APKPure versions page", file=sys.stderr)
        return 1

    stable = [
        item for item in entries
        if not ALPHA_BETA_RE.search(item[0]) or STABLE_SUFFIX_RE.search(item[0])
    ]
    if not stable:
        print("[ERROR] No stable X release found on the APKPure versions page", file=sys.stderr)
        return 1

    version, version_code = max(stable, key=lambda item: stable_key(item[0]))
    print(DOWNLOAD_URL.format(version_code=version_code))
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
