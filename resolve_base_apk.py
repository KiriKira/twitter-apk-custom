#!/usr/bin/env python3
"""Resolve the latest stable X/Twitter base APK download URL.

Primary source: APKPure app page (the versions list page is blocked from
GitHub Actions runners, the app page is not). Falls back to the APKPure
versions page and to APKCombo.

Prints two lines:
  <download_url>
  <version>

Exits non-zero when every source is unreachable or no stable release is found.
"""

import re
import sys
import urllib.request

APP_PAGE_URL = "https://apkpure.com/x-twitter/com.twitter.android"
VERSIONS_URL = "https://apkpure.com/x-twitter/com.twitter.android/versions"
APKPURE_DOWNLOAD_URL = (
    "https://d.apkpure.net/b/XAPK/com.twitter.android?versionCode={version_code}"
)
APKCOMBO_PAGE_URL = "https://apkcombo.com/x-twitter/com.twitter.android/download/apk"
APKCOMBO_DOWNLOAD_URL = (
    "https://download.apkcombo.com/{version_code}/com.twitter.android_{version}.apk"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

VERSION_CODE_RE = re.compile(r"versionCode[^\d]{0,20}(\d{6,12})", re.IGNORECASE)
VERSION_RE = re.compile(r'"version":"([^"]+)"')
STABLE_RE = re.compile(r"(\d+\.\d+\.\d+)(?:-release(?:\.\d+)?)?")
# Matches entries like:
#   data-dt-version="12.16.3-release.0" data-dt-package_name="com.twitter.android" data-dt-version_code="312163000"
DT_VERSION_RE = re.compile(
    r'data-dt-version="([^"]+)"(?:[^>]*?)data-dt-version_code="(\d+)"'
)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def version_key(version: str) -> tuple[int, ...]:
    numeric = re.search(r"\d+(?:\.\d+)*", version)
    if numeric is None:
        return (0,)
    return tuple(int(part) for part in numeric.group(0).split("."))


def is_stable(version: str) -> bool:
    return not re.search(r"(?:^|[-.])(?:alpha|beta)(?:[-.]|$)", version, re.IGNORECASE)


def resolve_apkpure(page: str) -> tuple[str, str] | None:
    # The app page embeds the release list; prefer entries that also carry a
    # versionCode so the download URL is exact.
    pairs = DT_VERSION_RE.findall(page)
    if not pairs:
        return None
    stable = [item for item in pairs if is_stable(item[0])]
    if not stable:
        return None
    version, version_code = max(stable, key=lambda item: version_key(item[0]))
    return APKPURE_DOWNLOAD_URL.format(version_code=version_code), version


def resolve_apkcombo(page: str) -> tuple[str, str] | None:
    versions = re.findall(r"(\d+\.\d+\.\d+)", page)
    if not versions:
        return None
    versions = sorted(set(versions), key=version_key)
    version = versions[-1]
    return APKCOMBO_DOWNLOAD_URL.format(version_code=0, version=version), version


def main() -> int:
    sources = (
        ("APKPure app page", APP_PAGE_URL, resolve_apkpure),
        ("APKPure versions page", VERSIONS_URL, resolve_apkpure),
        ("APKCombo", APKCOMBO_PAGE_URL, resolve_apkcombo),
    )
    for name, url, resolver in sources:
        try:
            page = fetch(url)
        except OSError as exc:
            print(f"[WARN] {name} unreachable: {exc}", file=sys.stderr)
            continue
        result = resolver(page)
        if result is None:
            print(f"[WARN] {name}: no stable release found", file=sys.stderr)
            continue
        download_url, version = result
        print(download_url)
        print(version)
        return 0

    print("[ERROR] No APK source resolved a stable X release", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
