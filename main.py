import os
import re
import time
import json
import urllib.request
import subprocess
import argparse
import apkmirror
import github

from apkmirror import Version, Variant
from build_variants import build_apks
from download_bins import download_apkeditor, download_morphe_cli, download_release_asset
from utils import panic, merge_apk, publish_release, patch_apk

# APKMirrorからUniversal Bundleを含む最新の有効なリリースを探索して取得する
def get_latest_valid_release(versions: list[Version]) -> tuple[Version | None, Variant | None]:
    check_count = 0
    for i in versions:
        if i.version.find("release") >= 0:
            check_count += 1
            print(f"  -> Checking APKMirror ({check_count}/10): {i.version}")
            
            try:
                variants = apkmirror.get_variants(i)
            except Exception as e:
                print(f"  -> Failed to fetch variants: {e}")
                continue

            for variant in variants:
                if variant.is_bundle and variant.architecture == "universal":
                    print(f"  -> [SUCCESS] Universal bundle found in APKMirror: {i.version}")
                    return i, variant
            
            if check_count >= 10:
                print("  -> [WARNING] Checked top 10 releases but found no universal bundles.")
                break
            
            time.sleep(1)
                
    return None, None

# Twitter用のAPKダウンロードからパッチ適用、GitHubリリースまでのパイプラインを実行する
def process(latest_version: Version, pikoRelease, download_link: Variant):
    print("\n[STEP 4] Downloading APK and tools...")
    
    print(f"  -> Downloading {latest_version.version} bundle from APKMirror...")
    apkmirror.download_apk(download_link)
    target_file = "big_file.apkm"

    if not os.path.exists(target_file):
        panic("  -> [ERROR] Failed to download APK from APKMirror.")

    print("  -> Downloading APKEditor...")
    download_apkeditor()
    if not os.path.exists("big_file_merged.apk"):
        print(f"  -> Merging APK ({target_file} -> big_file_merged.apk)...")
        merge_apk(target_file)
    else:
        print("  -> Merged APK already exists. Skipping merge.")

    print("\n[STEP 5] Preparing Morphe CLI...")
    download_morphe_cli()
    
    message: str = f"""
Changelogs:
[piko-{pikoRelease["tag_name"]}]({pikoRelease["html_url"]})
"""

    print(f"\n[STEP 6] Building patched APKs (Target: {latest_version.version})...")
    build_apks(latest_version)

    print("\n[STEP 7] Publishing release to GitHub...")
    publish_release(
        latest_version.version,
        [
            f"x-piko-v{latest_version.version}.apk",
            f"x-piko-material-you-v{latest_version.version}.apk",
            f"twitter-piko-v{latest_version.version}.apk",
            f"twitter-piko-material-you-v{latest_version.version}.apk",
        ],
        message,
        latest_version.version
    )
    print("  -> [DONE] Release successfully published.")

# GitHubリリースの本文から適用されたPikoパッチのバージョンを抽出する
def extract_piko_version(body: str) -> str | None:
    m = re.search(r"piko-(v[\w\.\-]+)", body, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

# バージョン文字列を数値的に比較し、v1がv2より新しい場合にTrueを返す
def version_greater(v1: str, v2: str) -> bool:
    print(f"  -> [DEBUG] Comparing: '{v1}' vs '{v2}'")

    def normalize(v: str):
        v = v.lstrip('v')
        parts = v.split('-', 1)
        main_part = parts[0]
        prerelease_part = parts[1] if len(parts) > 1 else ""

        main_nums = re.findall(r'\d+', main_part)
        main_nums = [int(n) for n in main_nums[:3]]
        while len(main_nums) < 3:
            main_nums.append(0)

        pre_parts = []
        if prerelease_part:
            for part in re.split(r'(\d+)', prerelease_part):
                if part == '': continue
                if part.isdigit(): pre_parts.append(int(part))
                else: pre_parts.append(part)
        return main_nums, pre_parts

    nums1, pre1 = normalize(v1)
    nums2, pre2 = normalize(v2)

    for i in range(3):
        if nums1[i] != nums2[i]: return nums1[i] > nums2[i]

    if not pre1 and pre2: return True
    if pre1 and not pre2: return False

    for p1, p2 in zip(pre1, pre2):
        if p1 != p2:
            if type(p1) == type(p2): return p1 > p2
            else: return str(p1) > str(p2)

    return len(pre1) > len(pre2)

# Instagram用の対象バージョン判定、APK取得、パッチ適用、リリース追記を実行する
def check_and_build_instagram(release_tag: str, pikoRelease: dict, force: bool = False):
    print(f"\n=======================================================")
    print(f"[STEP 8] INITIATING INSTAGRAM BUILD PIPELINE")
    print(f"=======================================================")
    
    print("\n[STEP 8.1] Verifying existing release assets...")
    if not force:
        cmd_check = ["gh", "release", "view", release_tag, "--json", "assets"]
        try:
            res = subprocess.run(cmd_check, capture_output=True, text=True, check=True)
            assets = json.loads(res.stdout).get("assets", [])
            has_insta = any("instagram" in a["name"].lower() for a in assets)
            if has_insta:
                print("  -> [SKIP] Instagram APK is already present in this release.")
                return
        except subprocess.CalledProcessError:
            print(f"  -> [WARNING] Release {release_tag} does not exist yet. It will be created.")
    else:
        print("  -> [FORCE] Instagram build forced by CLI argument or Piko update.")

    print("\n[STEP 8.2] Fetching target Piko patches-list.json...")
    is_pre = pikoRelease.get("prerelease", False)
    branch = "dev" if is_pre else "main"
    print(f"  -> Target Piko branch: {branch}")
    
    url = f"https://raw.githubusercontent.com/crimera/piko/refs/heads/{branch}/patches-list.json"
    print(f"  -> Fetching {url}...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            patches_list = data.get("patches", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"  -> [ERROR] Failed to load patches-list.json: {e}")
        return

    print("\n[STEP 8.3] Resolving supported Instagram versions...")
    versions_set = set()
    for patch in patches_list:
        compat = patch.get("compatiblePackages")
        if isinstance(compat, dict) and "com.instagram.android" in compat:
            if compat["com.instagram.android"]: versions_set.update(compat["com.instagram.android"])
        elif isinstance(compat, list):
            for pkg in compat:
                if isinstance(pkg, dict) and pkg.get("name") == "com.instagram.android":
                    if pkg.get("versions"): versions_set.update(pkg.get("versions"))
    
    if not versions_set:
        print("  -> [ERROR] No supported versions found for Instagram.")
        return
        
    supported_versions = sorted(list(versions_set), key=lambda s: [int(u) for u in s.split('.')])[-5:]
    print(f"  -> Found {len(supported_versions)} recent compatible versions.")
    
    print("\n[STEP 8.4] Downloading base APK from APKMirror (Direct Sniper Mode)...")
    
    final_insta_ver = None
    insta_base_apk_to_patch = None
    
    for version in reversed(supported_versions):
        print(f"\n  -> [FALLBACK ROUTINE] Trying to fetch Instagram v{version}...")
        
        slug = version.replace('.', '-')
        
        # ターゲット
        target_url = f"https://www.apkmirror.com/apk/instagram/instagram-instagram/instagram-{slug}-release/"
        
        variants = []
        print(f"  -> Targeting Exact URL: {target_url}")
        time.sleep(2) # Cloudflareの警戒を避けるため少し待機
        
        try:
            tv = Version(version=version, link=target_url)
            variants = apkmirror.get_variants(tv)
            if variants:
                print(f"  -> [SUCCESS] Hit direct URL and found {len(variants)} variants!")
        except Exception as e:
            print(f"  -> [FAILED] {e}")
            time.sleep(3) # 弾かれたら少し休む
        
        if not variants:
            print(f"  -> [SKIP] No variants found for v{version}.")
            continue
            
        target_variant = None
        # 1. 優先: BUNDLE版 (arm64 または nodpi)
        for v in variants:
            if getattr(v, 'is_bundle', False):
                arch = getattr(v, 'architecture', '').lower()
                dpi = getattr(v, 'screen_dpi', '').lower()
                if "arm64" in arch or "universal" in arch or "nodpi" in arch or "120-640" in dpi:
                    target_variant = v
                    break
        # 2. 次点: 通常のAPK版
        if not target_variant:
            for v in variants:
                if not getattr(v, 'is_bundle', False):
                    arch = getattr(v, 'architecture', '').lower()
                    dpi = getattr(v, 'screen_dpi', '').lower()
                    if "arm64" in arch or "universal" in arch or "nodpi" in arch or "120-640" in dpi:
                        target_variant = v
                        break
        # 3. 妥協: 最初に見つかったもの
        if not target_variant:
            target_variant = variants[0]

        ext = ".apkm" if getattr(target_variant, 'is_bundle', False) else ".apk"
        filepath = f"insta_base{ext}"
        merged_filepath = "insta_base_merged.apk"

        if os.path.exists(filepath): os.remove(filepath)
        if os.path.exists(merged_filepath): os.remove(merged_filepath)

        download_apkeditor()

        try:
            apkmirror.download_apk(target_variant, path=filepath)
            if os.path.exists(filepath):
                print(f"  -> [SUCCESS] Downloaded Instagram base APK for v{version}")
                
                if getattr(target_variant, 'is_bundle', False):
                    print("  -> Merging Instagram APKM bundle...")
                    merge_apk(filepath)
                    insta_base_apk_to_patch = merged_filepath
                else:
                    insta_base_apk_to_patch = filepath
                    
                final_insta_ver = version
                break
        except Exception as e:
            print(f"  -> [BLOCKED] Download failed: {e}")
            if os.path.exists(filepath): os.remove(filepath)
            print("  -> Retrying with an older version...")
            time.sleep(3)

    if not final_insta_ver or not insta_base_apk_to_patch or not os.path.exists(insta_base_apk_to_patch):
        print("  -> [FATAL] All fallback attempts failed for Instagram.")
        return

    print("\n[STEP 8.5] Selecting compatible patches...")
    insta_patches = []
    for patch in patches_list:
        patch_name = patch.get("name")
        compat = patch.get("compatiblePackages")
        supports = False
        if not compat: 
            supports = True
        elif isinstance(compat, dict) and "com.instagram.android" in compat:
            versions = compat["com.instagram.android"]
            if not versions or final_insta_ver in versions: supports = True
        elif isinstance(compat, list):
            for pkg in compat:
                if isinstance(pkg, dict) and pkg.get("name") == "com.instagram.android":
                    versions = pkg.get("versions", [])
                    if not versions or final_insta_ver in versions: supports = True
                    break
        if supports:
            insta_patches.append(patch_name)
            
    print(f"  -> Extracted {len(insta_patches)} applicable patches.")

    print("\n[STEP 8.6] Building patched APK with Morphe CLI...")
    download_morphe_cli()
    cli = "bins/morphe-cli.jar"
    patches_mpp = "bins/patches.mpp"
    output_apk = f"instagram-piko-v{final_insta_ver}.apk"
    
    print(f"  -> Building {output_apk}...")
    patch_apk(cli, patches_mpp, insta_base_apk_to_patch, includes=insta_patches, excludes=[], out=output_apk)
    
    print("\n[STEP 8.7] Uploading Instagram APK to GitHub...")
    if os.path.exists(output_apk):
        print(f"  -> Uploading {output_apk} to release '{release_tag}'...")
        try:
            subprocess.run(["gh", "release", "upload", release_tag, output_apk, "--clobber"], check=True)
            print("  -> [SUCCESS] Instagram APK successfully published.")
        except subprocess.CalledProcessError:
            print(f"  -> [WARNING] Failed to upload. Release might not exist. Creating release '{release_tag}'...")
            message = f"Changelogs:\n[piko-{pikoRelease['tag_name']}]({pikoRelease['html_url']})"
            try:
                subprocess.run(["gh", "release", "create", "--latest", release_tag, output_apk, "--notes", message, "--title", release_tag], check=True)
                print("  -> [SUCCESS] Created release and published Instagram APK.")
            except subprocess.CalledProcessError as e:
                print(f"  -> [ERROR] Failed to create release: {e}")
    else:
        print("  -> [ERROR] Failed to build Instagram APK.")

# 引数を解釈し、更新の有無を確認した上で各アプリのビルド処理を制御する
def main():
    parser = argparse.ArgumentParser(description="Piko Auto Builder")
    parser.add_argument("--app", choices=["twitter", "instagram", "all"], default="all", help="Which app to build")
    args = parser.parse_args()

    url: str = "https://www.apkmirror.com/apk/x-corp/twitter/"
    repo_url: str = "monsivamon/twitter-apk"

    print(f"\n[STEP 1] Scanning APKMirror for the latest release... (Mode: {args.app.upper()})")
    versions = apkmirror.get_versions(url)
    latest_version, bundle_variant = get_latest_valid_release(versions)
    
    if latest_version is None or bundle_variant is None:
        print("\n  -> [EXIT] Critical Failure: No valid universal release found from APKMirror.")
        return

    final_apk = latest_version.version

    print("\n[STEP 2] Fetching the latest Piko patches from GitHub...")
    pikoRelease = download_release_asset(
        "crimera/piko",
        r".*\.mpp$",
        "bins",
        "patches.mpp",
        include_prereleases=True
    )
    final_piko = pikoRelease["tag_name"]
    print(f"  -> Latest Piko patch: {final_piko}")

    print("\n[STEP 3] Verifying build history for updates...")
    last_build_version: github.GithubRelease | None = github.get_last_build_version(repo_url)

    if last_build_version is None:
        print("  -> No previous release found. Treating as initial build.")
        if args.app in ["twitter", "all"]:
            process(latest_version, pikoRelease, bundle_variant)
        if args.app in ["instagram", "all"]:
            check_and_build_instagram(latest_version.version, pikoRelease, force=True)
        return

    last_ver_apk = last_build_version.tag_name
    last_ver_piko = extract_piko_version(last_build_version.body or "")
    
    print(f"  -> Target APK: {final_apk}")
    print(f"  -> Target Piko: {final_piko}")
    print(f"  -> Previous Build APK: {last_ver_apk}")
    print(f"  -> Previous Build Piko: {last_ver_piko}")
    
    apk_is_new = version_greater(final_apk, last_ver_apk)

    if last_ver_piko is None:
        print("  -> Previous Piko version is unknown. Treating as new.")
        piko_is_new = True
    else:
        piko_is_new = version_greater(final_piko, last_ver_piko)

    target_tag = final_apk if apk_is_new else last_ver_apk

    if args.app in ["twitter", "all"]:
        if apk_is_new or piko_is_new:
            print("\n  -> [RESULT] Update detected! Initiating Twitter build sequence.")
            process(latest_version, pikoRelease, bundle_variant)
        else:
            print("\n  -> [SKIP] No updates for APK or Piko. Skipping Twitter build.")
    else:
        print(f"\n  -> [SKIP] Twitter build bypassed by --app {args.app} argument.")
        
    if args.app in ["instagram", "all"]:
        force_insta = piko_is_new or (args.app == "instagram")
        check_and_build_instagram(target_tag, pikoRelease, force=force_insta)

if __name__ == "__main__":
    main()