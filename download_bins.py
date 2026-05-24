import os
import re
import requests
from utils import download

# GitHubリポジトリから条件に合致するリリースアセットを検索してダウンロードする
def download_release_asset(repo: str, regex: str, out_dir: str, filename=None, include_prereleases: bool = False, version=None):
    url = f"https://api.github.com/repos/{repo}/releases"
    
    # APIのレートリミット超過を防ぐため、GITHUB_TOKENを用いて認証付きリクエストを行う
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch GitHub releases for {repo}: HTTP {response.status_code} - {response.text}")

    # プレリリースの包含条件に基づくフィルタリング
    releases = [r for r in response.json() if include_prereleases or not r.get("prerelease")]

    if not releases:
        raise Exception(f"No releases found for {repo}")

    # 特定バージョンの指定がある場合の絞り込み
    if version is not None:
        releases = [r for r in releases if r.get("tag_name") == version]

    if len(releases) == 0:
        raise Exception(f"No release found for version {version}")

    latest_release = releases[0]
    assets = latest_release.get("assets", [])

    link = None
    for i in assets:
        if re.search(regex, i["name"]):
            link = i["browser_download_url"]
            if filename is None:
                filename = i["name"]
            break

    if link is None:
        raise Exception(f"No asset matching regex '{regex}' found in release.")

    download(link, f"{out_dir.lstrip('/')}/{filename}")

    return latest_release


# 分割APKのマージに使用するAPKEditorをダウンロードする
def download_apkeditor():
    print("Downloading APKEditor...")
    download_release_asset("REAndroid/APKEditor", "APKEditor", "bins", "apkeditor.jar")


# APKへのパッチ適用に使用するMorphe CLIをダウンロードする
def download_morphe_cli():
    print("Downloading Morphe CLI...")
    download_release_asset(
        "MorpheApp/morphe-cli",
        r".*morphe-cli.*-all\.jar$",
        "bins",
        "morphe-cli.jar",
        include_prereleases=False
    )