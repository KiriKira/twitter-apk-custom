import os
import re
import json
import urllib.request
import argparse
import shutil
import glob
import subprocess
import sys

# =====================================================================
#  Githubリポジトリの設定 (成果物のアップロード先)
# =====================================================================
GITHUB_REPO = "monsivamon/twitter-apk" 

# =====================================================================
#  実行環境のパッチ処理
# =====================================================================

# Windows環境でJavaにパスが通っていない場合、自動で探索してPATHに動的追加する
def ensure_java_in_path():
    if shutil.which("java"):
        return
    if os.name == 'nt':
        search_patterns = [
            r"C:\Program Files\Eclipse Adoptium\jdk-17*\bin",
            r"C:\Program Files\Eclipse Adoptium\jdk-21*\bin",
            r"C:\Program Files\Java\jdk-17*\bin",
            r"C:\Program Files\Java\jdk-21*\bin",
            r"C:\Program Files\Amazon Corretto\jdk17*\bin"
        ]
        for pattern in search_patterns:
            matches = glob.glob(pattern)
            if matches:
                os.environ["PATH"] = matches[0] + os.pathsep + os.environ["PATH"]
                print(f"  -> [INFO] Dynamically injected Java into PATH: {matches[0]}")
                return

ensure_java_in_path()

# subprocess.run を上書きし、Windows特有のエンコーディングエラー（文字化けによるクラッシュ）を防ぐ
original_run = subprocess.run
def patched_run(*args, **kwargs):
    if kwargs.get("text") is True or kwargs.get("capture_output") is True:
        kwargs["encoding"] = "utf-8"
        kwargs["errors"] = "replace"
        kwargs["text"] = True
    return original_run(*args, **kwargs)

subprocess.run = patched_run

# =====================================================================

# utils.py内の依存を切り離すためのインポートおよび定数定義
from download_bins import download_apkeditor, download_morphe_cli, download_release_asset
from utils import merge_apk

BASE_APK_DIR = ".base_apk"
OUTPUT_DIR = "output_apks"
BINS_DIR = "bins"

# バージョン情報を保持するための簡易クラス
class LocalVersion:
    def __init__(self, version_str):
        self.version = version_str

# GitHub APIを使用して、Pikoパッチの最新リリース(StableまたはBeta)のタグ名を取得する
def get_latest_piko_tag(is_pre: bool) -> str:
    print("  -> Fetching latest Piko release info from GitHub...")
    url = "https://api.github.com/repos/crimera/piko/releases"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            releases = json.loads(response.read().decode('utf-8'))
            for r in releases:
                if is_pre and r.get("prerelease"): return r["tag_name"]
                elif not is_pre and not r.get("prerelease"): return r["tag_name"]
            return releases[0]["tag_name"]
    except Exception as e:
        return "v1.0.0"

# PikoのGitHubリポジトリからパッチの互換性リスト(JSON)を取得・解析する
def fetch_patches_json(is_pre: bool) -> list:
    branch = "dev" if is_pre else "main"
    url = f"https://raw.githubusercontent.com/crimera/piko/refs/heads/{branch}/patches-list.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("patches", []) if isinstance(data, dict) else data
    except Exception:
        return []

# アプリのパッケージ名とバージョンを基に、適用可能なパッチ名のリストを抽出する
def get_patches_for_version(patches_list: list, package_name: str, target_version: str) -> list:
    patches = []
    # バージョン比較を正確に行うため、不要な文字列を除外 (例: "11.93.0-release" -> "11.93.0")
    clean_version_match = re.search(r'^(\d+\.\d+\.\d+)', target_version)
    clean_version = clean_version_match.group(1) if clean_version_match else target_version

    for patch in patches_list:
        patch_name = patch.get("name")
        compat = patch.get("compatiblePackages")
        supports_version = False

        if not compat: 
            supports_version = True
        elif isinstance(compat, list):
            for pkg in compat:
                if isinstance(pkg, dict) and pkg.get("packageName") == package_name:
                    extracted_versions = set()
                    if pkg.get("versions"): extracted_versions.update(pkg.get("versions"))
                    if pkg.get("targets"):
                        for t in pkg.get("targets"):
                            ver = t.get("version")
                            if ver and not t.get("isExperimental", False): extracted_versions.add(ver)
                    if not extracted_versions or clean_version in extracted_versions:
                        supports_version = True
                    break
        elif isinstance(compat, dict) and package_name in compat:
            versions = compat[package_name]
            if not versions or clean_version in versions:
                supports_version = True

        if supports_version:
            patches.append(patch_name)
    return patches

# ベースAPKのファイル名からアプリのバージョン文字列を自動抽出する
def extract_version_from_filename(filename: str) -> str:
    match = re.search(r'(\d+\.\d+\.\d+[-a-zA-Z0-9.]*)', filename)
    if match:
        ver = match.group(1)
        for ext in [".apk", ".apkm", ".apks", "_pairip", "_bypassed", "_ripped"]:
            if ext in ver:
                ver = ver.split(ext)[0]
        return ver.strip("-")
    return "local"

# 処理中に生成された一時ファイルやディレクトリを安全かつ確実に削除する
def cleanup_intermediate_files():
    print("\n[CLEANUP] Sweeping intermediate and temporary files...")
    
    # 明示的に削除するディレクトリ群
    dirs_to_clean = [
        "morphe-temporary-files", 
        "__pycache__", 
        "bins", 
        "big_file_merged", 
        "insta_base_merged"
    ]
    
    for d in dirs_to_clean:
        if os.path.exists(d) and os.path.isdir(d): 
            shutil.rmtree(d, ignore_errors=True)
            print(f"  -> Trashed directory: {d}")
            
    # パターンマッチで拾う一時ファイルの残骸
    temp_files = glob.glob("big_file*") + glob.glob("insta_base*")
    for f in temp_files:
        if os.path.exists(f):
            try: 
                if os.path.isdir(f):
                    shutil.rmtree(f, ignore_errors=True)
                    print(f"  -> Trashed temporary directory: {f}")
                else:
                    os.remove(f)
                    print(f"  -> Trashed temporary file: {f}")
            except: 
                pass
                
    print("  -> Workspace is completely clean.")

# GitHub CLI (gh) を利用して、対象リポジトリへのプッシュ権限があるかを検証する
def check_github_repo_access(repo_name):
    print("\n[PRE-CHECK] Verifying GitHub repository access...")
    if not repo_name or "ここ" in repo_name:
        print("  -> [ERROR] GITHUB_REPO is not configured correctly.")
        return False
    if not shutil.which("gh"):
        print("  -> [WARNING] GitHub CLI ('gh') is not installed. Uploading will be skipped.")
        return True 
    print(f"  -> Pinging repository: {repo_name} ...")
    res = subprocess.run(["gh", "repo", "view", repo_name], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  -> [ERROR] Cannot access GitHub repository ({repo_name}).")
        print(f"     Make sure the repository exists and you have authenticated via 'gh auth login'.")
        return False
    print("  -> [SUCCESS] Repository access confirmed.")
    return True

# GitHubリポジトリへ成果物(APK)を含むリリースを作成、または既存のリリースに追記する
def upload_to_github_release(piko_tag, file_paths, is_pre):
    if not file_paths:
        print("  -> [INFO] No built files found for upload.")
        return
    if not shutil.which("gh"):
        return

    print("\n=======================================================")
    print(" GITHUB AUTO RELEASE PIPELINE")
    print("=======================================================")
    
    tag = f"piko-{piko_tag}"
    title = f"piko {piko_tag}"
    notes = f"Changelogs:\n[{tag}](https://github.com/crimera/piko/releases/tag/{piko_tag})\n\nThis version was built manually."
    
    print(f"  -> Attempting to create GitHub Release ({tag})...")
    create_cmd = ["gh", "release", "create", tag] + file_paths + ["--title", title, "--notes", notes]
    if is_pre:
        create_cmd.append("--prerelease")
    if GITHUB_REPO:
        create_cmd.extend(["--repo", GITHUB_REPO])
    
    res = subprocess.run(create_cmd, capture_output=True, text=True)
    
    if res.returncode != 0:
        if "already exists" in res.stderr.lower():
            print("  -> [INFO] Release target already exists. Switching to file upload mode...")
            upload_cmd = ["gh", "release", "upload", tag] + file_paths + ["--clobber"]
            if GITHUB_REPO:
                upload_cmd.extend(["--repo", GITHUB_REPO])
            res_upload = subprocess.run(upload_cmd, capture_output=True, text=True)
            if res_upload.returncode == 0:
                print(f"  -> [SUCCESS] Successfully uploaded assets to existing Release {tag}.")
            else:
                print(f"  -> [ERROR] GitHub upload failed:\n{res_upload.stderr}")
        else:
            print(f"  -> [ERROR] GitHub release creation failed:\n{res.stderr}")
    else:
        print(f"  -> [SUCCESS] Created new GitHub Release {tag} and uploaded assets.")

# utils.pyの不具合を回避するため、Morpheの実行ログから絶対パスを直接抽出し確実にファイルを移動する
def run_morphe_and_extract(cli_jar, patch_mpp, input_apk, output_apk_name, includes, excludes):
    cmd = [
        "java", "-jar", cli_jar, "patch",
        "-p", patch_mpp,
        "--continue-on-error",
        "--keystore", "ks.keystore",
        "--keystore-entry-password", "123456789",
        "--keystore-password", "123456789",
        "--signer", "jhc",
        "--keystore-entry-alias", "jhc"
    ]
    for i in includes: cmd.extend(["-e", i])
    for e in excludes: cmd.extend(["-d", e])
    cmd.append(input_apk)
    
    print(f"\n  -> Executing Morphe CLI for {output_apk_name}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    if res.stdout: print(res.stdout)
    if res.returncode != 0:
        print("--- CLI Error Output ---", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        res.check_returncode()
    
    # 実行ログのテキストから「Saved to ...」の記述を探し出し、生成されたAPKの絶対パスを取得する
    output_text = (res.stdout or "") + "\n" + (res.stderr or "")
    match = re.search(r"Saved to\s+([^\r\n]+)", output_text)
    
    if not match:
        print(f"  -> [FATAL ERROR] Failed to parse output path from CLI log.")
        sys.exit(1)
        
    cli_output = match.group(1).strip()
    print(f"  -> [DEBUG] Extracted output path: {cli_output}")
    
    # Windowsのファイルシステム同期（アンチウイルスのスキャン等）を待機する
    import time
    time.sleep(1) 
    
    if os.path.exists(cli_output):
        dest_path = os.path.join(OUTPUT_DIR, output_apk_name)
        if os.path.exists(dest_path):
            os.unlink(dest_path)
        shutil.move(cli_output, dest_path)
        return dest_path
    else:
        print(f"  -> [FATAL ERROR] Generated file could not be found: {cli_output}")
        sys.exit(1)

# メイン処理
def main():
    print("\n=======================================================")
    print(" PIKO MANUAL LOCAL BUILDER")
    print("=======================================================\n")

    if not check_github_repo_access(GITHUB_REPO):
        print("\n[!] Pre-check failed. Aborting build process.")
        return

    # パッチのバージョン選択
    print("Select target Piko branch:")
    print("  [1] Stable (Default)")
    print("  [2] Pre-release (Beta)")
    choice = input("Enter your choice (1 or 2): ").strip()
    is_pre = (choice == "2")

    print("\n[STEP 0] Cleaning up workspace...")
    dirs_to_clean = [BINS_DIR, OUTPUT_DIR, "morphe-temporary-files", "__pycache__", "big_file_merged", "insta_base_merged"]
    for d in dirs_to_clean:
        if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
    os.makedirs(BINS_DIR)
    os.makedirs(OUTPUT_DIR)

    if not os.path.exists(BASE_APK_DIR):
        os.makedirs(BASE_APK_DIR)
        print(f"\n[!] Created directory: {BASE_APK_DIR}. Please place your base APK(s) here and run again.")
        return

    base_files = glob.glob(os.path.join(BASE_APK_DIR, "*"))
    if not base_files:
        print(f"\n[!] No base APK files found in '{BASE_APK_DIR}'.")
        return

    print("\n[STEP 1] Fetching Piko resources...")
    piko_tag = get_latest_piko_tag(is_pre)
    print(f"  -> Tag: {piko_tag}")
    download_release_asset("crimera/piko", r".*\.mpp$", "bins", "patches.mpp", include_prereleases=is_pre, version=piko_tag)
    patches_list = fetch_patches_json(is_pre)
    
    print("\n[STEP 2] Preparing build tools...")
    download_apkeditor()
    download_morphe_cli()

    all_generated_assets = []

    # ベースAPKのディレクトリ内を順番に処理する
    for file_path in base_files:
        filename = os.path.basename(file_path).lower()
        version_str = extract_version_from_filename(filename)
        
        # ==========================================
        # 🐦 Twitter / X 向けビルド処理
        # ==========================================
        if "twitter" in filename or "x-" in filename or "x_" in filename:
            print(f"\n[STEP 3] Processing Twitter/X: {filename} (Detected v{version_str})")
            
            is_apkm = filename.endswith(".apkm") or filename.endswith(".apks")
            working_file = "big_file.apkm" if is_apkm else "big_file_merged.apk"
            
            for f in glob.glob("big_file*"): os.remove(f)
            shutil.copy(file_path, working_file)

            target_merged = "big_file_merged.apk"
            if is_apkm:
                print("  -> Merging App Bundle (APKM/APKS)...")
                merge_apk(working_file)
                if os.path.exists(working_file): os.remove(working_file)
            else:
                if working_file != target_merged: shutil.move(working_file, target_merged)
            
            if os.path.exists(target_merged):
                print("  -> Building Twitter/X variants...")
                
                cli_jar = "bins/morphe-cli.jar"
                patch_mpp = "bins/patches.mpp"
                
                # 4つのバリエーション共通で適用するパッチ設定
                common_includes = [
                    "Enable app downgrading",
                    "Hide FAB",
                    "Disable chirp font",
                    "Add ability to copy media link",
                    "Hide Banner",
                    "Hide promote button",
                    "Hide Community Notes",
                    "Delete from database",
                    "Customize Navigation Bar items",
                    "Remove premium upsell",
                    "Control video auto scroll",
                    "Force enable translate",
                ]
                common_excludes = []
                
                # バリアント1: X (Material You 適用)
                out1 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"x-piko-material-you-v{version_str}.apk", 
                    ["Dynamic color"] + common_includes, 
                    common_excludes
                )
                all_generated_assets.append(out1)
                
                # バリアント2: X (通常カラー)
                out2 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"x-piko-v{version_str}.apk", 
                    common_includes, 
                    ["Dynamic color"] + common_excludes
                )
                all_generated_assets.append(out2)
                
                # バリアント3: Twitter (青い鳥アイコン復活 + Material You 適用)
                out3 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"twitter-piko-material-you-v{version_str}.apk", 
                    ["Bring back twitter", "Dynamic color"] + common_includes, 
                    common_excludes
                )
                all_generated_assets.append(out3)
                
                # バリアント4: Twitter (青い鳥アイコン復活 + 通常カラー)
                out4 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"twitter-piko-v{version_str}.apk", 
                    ["Bring back twitter"] + common_includes, 
                    ["Dynamic color"] + common_excludes
                )
                all_generated_assets.append(out4)
                
                print(f"  -> [SUCCESS] Twitter/X variants saved to '{OUTPUT_DIR}'.")

        # ==========================================
        # 📸 Instagram 向けビルド処理
        # ==========================================
        elif "insta" in filename:
            print(f"\n[STEP 3] Processing Instagram: {filename} (Detected v{version_str})")
            
            insta_merged = "insta_base_merged.apk"
            for f in glob.glob("insta_base*"): os.remove(f)

            is_apkm = filename.endswith(".apkm") or filename.endswith(".apks")
            working_file = "insta_base.apkm" if is_apkm else "insta_base_merged.apk"
            shutil.copy(file_path, working_file)

            if is_apkm:
                print("  -> Merging App Bundle (APKM/APKS)...")
                merge_apk(working_file)
                if os.path.exists(working_file): os.remove(working_file)
            else:
                if working_file != insta_merged: shutil.move(working_file, insta_merged)
            
            if os.path.exists(insta_merged):
                insta_patches = get_patches_for_version(patches_list, "com.instagram.android", version_str)
                print(f"  -> Extracted {len(insta_patches)} applicable patches.")
                
                out_path = run_morphe_and_extract(
                    "bins/morphe-cli.jar", "bins/patches.mpp", insta_merged, 
                    f"instagram-piko-{version_str}.apk", insta_patches, []
                )
                all_generated_assets.append(out_path)
                print(f"  -> [SUCCESS] Instagram variant saved to '{OUTPUT_DIR}'.")

    # 中間ファイルのクリーンアップ
    cleanup_intermediate_files()

    # 生成されたすべてのAPKをGitHub Releaseへ公開
    if all_generated_assets:
        upload_to_github_release(piko_tag, all_generated_assets, is_pre)

    print("\n=======================================================")
    print(" ALL PROCESSES COMPLETED SUCCESSFULLY")
    print("=======================================================\n")

if __name__ == "__main__":
    main()