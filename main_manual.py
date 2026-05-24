import os
import re
import json
import urllib.request
import shutil
import glob
import subprocess
import sys
import time

# =====================================================================
#  Githubリポジトリの設定 (成果物のアップロード先)
# =====================================================================
GITHUB_REPO = "monsivamon/twitter-apk"

# =====================================================================
#  apksigner の絶対パスを保持するグローバル変数
# =====================================================================
APKSIGNER_PATH = None

# =====================================================================
#  実行環境のパッチ処理（Java と apksigner のパスを確保）
# =====================================================================

# Java がシステム PATH に存在するか確認し、なければ自動検索して追加する
def ensure_java_in_path():
    if shutil.which("java"):
        print("  -> [DEBUG] Java is already in system PATH.")
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
                print(f"  -> [INFO] Injected Java into PATH: {matches[0]}")
                return
        print("  -> [WARNING] Could not automatically find Java in standard directories. Ensure Java is installed and in PATH.")

ensure_java_in_path()

# apksigner が利用可能か確認し、なければ Android SDK から探す
def ensure_apksigner_in_path():
    global APKSIGNER_PATH
    existing = shutil.which("apksigner")
    if existing:
        APKSIGNER_PATH = existing
        print(f"  -> [DEBUG] apksigner found in system PATH: {existing}")
        return
    if os.name == 'nt':
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        sdk_path = os.path.join(local_appdata, "Android", "Sdk", "build-tools")
        if os.path.isdir(sdk_path):
            versions = sorted(os.listdir(sdk_path), reverse=True)
            for ver in versions:
                apk_path = os.path.join(sdk_path, ver, "apksigner.bat")
                if os.path.exists(apk_path):
                    APKSIGNER_PATH = apk_path
                    print(f"  -> [INFO] Found apksigner at {apk_path}")
                    return
    print("  -> [ERROR] 'apksigner' not found. Please install Android SDK Build Tools and add it to PATH.")
    sys.exit(1)

ensure_apksigner_in_path()

# subprocess.run をパッチしてエンコーディング問題を回避
original_run = subprocess.run
def patched_run(*args, **kwargs):
    if kwargs.get("text") is True or kwargs.get("capture_output") is True:
        kwargs["encoding"] = "utf-8"
        kwargs["errors"] = "replace"
        kwargs["text"] = True
    return original_run(*args, **kwargs)

subprocess.run = patched_run

# =====================================================================
#  外部ユーティリティのインポート
# =====================================================================
from download_bins import download_apkeditor, download_morphe_cli, download_release_asset
from utils import merge_apk

BASE_APK_DIR = ".base_apk"
OUTPUT_DIR = "output_apks"
BINS_DIR = "bins"

# Piko リポジトリから最新のリリースタグを取得する
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
        print(f"  -> [WARNING] Failed to fetch latest release tag: {e}. Falling back to v1.0.0.")
        return "v1.0.0"

# Piko のブランチからパッチ定義 JSON をダウンロードする
def fetch_patches_json(is_pre: bool) -> list:
    branch = "dev" if is_pre else "main"
    url = f"https://raw.githubusercontent.com/crimera/piko/refs/heads/{branch}/patches-list.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            patches = data.get("patches", []) if isinstance(data, dict) else data
            print(f"  -> [DEBUG] Loaded {len(patches)} patch definitions.")
            return patches
    except Exception as e:
        print(f"  -> [WARNING] Failed to load patches JSON: {e}")
        return []

# 指定されたパッケージとバージョンに互換性のあるパッチだけを抽出する
def get_patches_for_version(patches_list: list, package_name: str, target_version: str) -> list:
    patches = []
    clean_version_match = re.search(r'^([\d.]+)', target_version)
    clean_version = clean_version_match.group(1).strip('.') if clean_version_match else target_version
    
    print(f"  -> [DEBUG] Filtering patches for Package: '{package_name}', Version: '{clean_version}'")

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
                            if ver: extracted_versions.add(ver)
                    if not extracted_versions or clean_version in extracted_versions:
                        supports_version = True
                    break
        elif isinstance(compat, dict) and package_name in compat:
            versions = compat[package_name]
            if not versions or clean_version in versions:
                supports_version = True

        if supports_version:
            patches.append(patch_name)
            
    print(f"  -> [DEBUG] Found {len(patches)} compatible patches.")
    return patches

# ファイル名からバージョン文字列を抽出する
def extract_version_from_filename(filename: str) -> str:
    match = re.search(r'(\d+\.\d+\.\d+[-a-zA-Z0-9.]*)', filename)
    if match:
        ver = match.group(1)
        for ext in [".apk", ".apkm", ".apks", "_pairip", "_bypassed", "_ripped"]:
            if ext in ver:
                ver = ver.split(ext)[0]
        parsed = ver.strip("-")
        print(f"  -> [DEBUG] Parsed version '{parsed}' from '{filename}'.")
        return parsed
    print(f"  -> [DEBUG] Could not extract version from '{filename}'. Using 'local'.")
    return "local"

# 作業ディレクトリを掃除し、一時ファイルやビルド中間生成物を削除する
def cleanup_workspace(is_initial=False):
    step_name = "[STEP 0] Resetting workspace..." if is_initial else "[CLEANUP] Removing temporary files..."
    print(f"\n{step_name}")

    # 削除対象（ディレクトリ固定 or ワイルドカードパターン）
    targets = [
        "morphe-temporary-files",
        "__pycache__",
        BINS_DIR,
        "big_file_merged",
        "insta_base_merged",
        ".idea",
        "big_file*",
        "insta_base*",
        "temp.jks",
    ]
    if is_initial:
        targets.append(OUTPUT_DIR)

    for target in targets:
        # ワイルドカードがあれば展開、なければそのままリスト
        paths = glob.glob(target) if any(c in target for c in "*?[") else [target]
        for path in paths:
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        if not is_initial: print(f"  -> [DEBUG] Removed directory: {path}")
                    else:
                        os.remove(path)
                        if not is_initial: print(f"  -> [DEBUG] Removed temporary file: {path}")
                except Exception:
                    pass

    if is_initial:
        os.makedirs(BINS_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        print("  -> Workspace ready.")
    else:
        print("  -> Workspace clean.")

# 設定された GitHub リポジトリにアクセス可能か確認する
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
        return False
    print("  -> [SUCCESS] Repository access confirmed.")
    return True

# GitHub にリリースを作成し、生成した APK をアップロードする
def upload_to_github_release(piko_tag, file_paths, is_pre):
    if not file_paths:
        print("  -> [INFO] No built files to upload.")
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
            print("  -> [INFO] Release already exists. Uploading files to existing release...")
            upload_cmd = ["gh", "release", "upload", tag] + file_paths + ["--clobber"]
            if GITHUB_REPO:
                upload_cmd.extend(["--repo", GITHUB_REPO])
            res_upload = subprocess.run(upload_cmd, capture_output=True, text=True)
            if res_upload.returncode == 0:
                print(f"  -> [SUCCESS] Assets uploaded to existing Release {tag}.")
            else:
                print(f"  -> [ERROR] Failed to upload assets:\n{res_upload.stderr}")
        else:
            print(f"  -> [ERROR] Failed to create GitHub release:\n{res.stderr}")
    else:
        print(f"  -> [SUCCESS] Created new GitHub Release {tag} and uploaded assets.")

# Morphe CLI を実行してパッチを適用し、出力 APK を所定の場所に移動する（署名は行わない）
def run_morphe_and_extract(cli_jar, patch_mpp, input_apk, output_apk_name, includes, excludes):
    cmd = [
        "java", "-jar", cli_jar, "patch",
        "-p", patch_mpp,
        "--continue-on-error",
        "--unsigned"
    ]
    for i in includes: cmd.extend(["-e", i])
    for e in excludes: cmd.extend(["-d", e])
    cmd.append(input_apk)
    
    print(f"\n  -> Patching APK to create {output_apk_name}...")
    print(f"  -> [DEBUG] Full Command: {' '.join(cmd)}")
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    
    if res.stdout: print(res.stdout)
    if res.returncode != 0:
        print("--- CLI Error Output ---", file=sys.stderr)
        print(res.stderr, file=sys.stderr)
        res.check_returncode()
    
    output_text = (res.stdout or "") + "\n" + (res.stderr or "")
    match = re.search(r"Saved to\s+([^\r\n]+)", output_text)
    
    if not match:
        print(f"  -> [FATAL ERROR] Could not parse output path from CLI log.")
        sys.exit(1)
        
    cli_output = match.group(1).strip()
    
    time.sleep(1) 
    
    if os.path.exists(cli_output):
        dest_path = os.path.join(OUTPUT_DIR, output_apk_name)
        print(f"  -> Moving patched APK to '{dest_path}'")
        if os.path.exists(dest_path):
            os.unlink(dest_path)
        shutil.move(cli_output, dest_path)
        return dest_path
    else:
        print(f"  -> [FATAL ERROR] Patched file not found at expected location: {cli_output}")
        sys.exit(1)

def main():
    print("\n=======================================================")
    print(" PIKO AUTOMATED LOCAL BUILDER")
    print("=======================================================\n")

    # GitHub リポジトリのアクセス権を事前確認
    if not check_github_repo_access(GITHUB_REPO):
        print("\n[!] Pre-check failed. Aborting build process.")
        return

    # 使用する Piko ブランチ（安定版 or プレリリース版）を選択
    print("Select target Piko branch:")
    print("  [1] Stable (Default)")
    print("  [2] Pre-release (Beta)")
    choice = input("Enter your choice (1 or 2): ").strip()
    is_pre = (choice == "2")

    # 作業ディレクトリの初期化（初回のみ output_apks も削除）
    cleanup_workspace(is_initial=True)

    # ベース APK の存在確認
    if not os.path.exists(BASE_APK_DIR):
        os.makedirs(BASE_APK_DIR)
        print(f"\n[!] Directory '{BASE_APK_DIR}' not found. It has been created. Please place your base APK(s) inside it and run the script again.")
        return

    base_files = glob.glob(os.path.join(BASE_APK_DIR, "*"))
    print(f"  -> [DEBUG] Found {len(base_files)} file(s) in {BASE_APK_DIR}.")
    if not base_files:
        print(f"\n[!] No base APK files found in '{BASE_APK_DIR}'.")
        return

    # ステップ1: Piko のリソース（パッチファイル）を取得
    print("\n[STEP 1] Fetching Piko resources...")
    piko_tag = get_latest_piko_tag(is_pre)
    print(f"  -> Target Piko Tag: {piko_tag}")
    download_release_asset("crimera/piko", r".*\.mpp$", "bins", "patches.mpp", include_prereleases=is_pre, version=piko_tag)
    
    patches_list = fetch_patches_json(is_pre)
    
    # ステップ2: ビルドツールを準備
    print("\n[STEP 2] Preparing build tools...")
    download_apkeditor()
    download_morphe_cli()

    all_generated_assets = []

    # ベース APK ごとにパッチを適用
    for file_path in base_files:
        filename = os.path.basename(file_path).lower()
        print(f"\n  -> [DEBUG] Inspecting file: {filename}")
        version_str = extract_version_from_filename(filename)
        
        # ==========================================
        # Twitter / X 向けビルド処理
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
                if working_file != target_merged: 
                    shutil.move(working_file, target_merged)
            
            if os.path.exists(target_merged):
                print("  -> Building Twitter/X variants...")
                
                cli_jar = "bins/morphe-cli.jar"
                patch_mpp = "bins/patches.mpp"
                
                # 共通パッチリスト
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
                
                # バリアント1: X (Material You)
                print("  -> Building Variant 1: X (Material You)")
                out1 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"x-piko-material-you-v{version_str}.apk", 
                    ["Dynamic color"] + common_includes, 
                    common_excludes
                )
                all_generated_assets.append(out1)
                
                # バリアント2: X (Standard)
                print("  -> Building Variant 2: X (Standard)")
                out2 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"x-piko-v{version_str}.apk", 
                    common_includes, 
                    ["Dynamic color"] + common_excludes
                )
                all_generated_assets.append(out2)
                
                # バリアント3: Twitter (Material You)
                print("  -> Building Variant 3: Twitter (Material You)")
                out3 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"twitter-piko-material-you-v{version_str}.apk", 
                    ["Bring back twitter", "Dynamic color"] + common_includes, 
                    common_excludes
                )
                all_generated_assets.append(out3)
                
                # バリアント4: Twitter (Standard)
                print("  -> Building Variant 4: Twitter (Standard)")
                out4 = run_morphe_and_extract(
                    cli_jar, patch_mpp, target_merged, 
                    f"twitter-piko-v{version_str}.apk", 
                    ["Bring back twitter"] + common_includes, 
                    ["Dynamic color"] + common_excludes
                )
                all_generated_assets.append(out4)
                
                print(f"  -> [SUCCESS] Twitter/X variants saved to '{OUTPUT_DIR}'.")

        # ==========================================
        # Instagram 向けビルド処理
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
                if working_file != insta_merged: 
                    shutil.move(working_file, insta_merged)
            
            if os.path.exists(insta_merged):
                # バージョン互換性のあるパッチを自動抽出
                insta_patches = get_patches_for_version(patches_list, "com.instagram.android", version_str)
                print(f"  -> Found {len(insta_patches)} applicable patches.")
                if insta_patches:
                    print(f"  -> [DEBUG] Patch List: {', '.join(insta_patches)}")
                
                out_path = run_morphe_and_extract(
                    "bins/morphe-cli.jar", "bins/patches.mpp", insta_merged, 
                    f"instagram-piko-{version_str}.apk", insta_patches, []
                )
                all_generated_assets.append(out_path)
                print(f"  -> [SUCCESS] Instagram variant saved to '{OUTPUT_DIR}'.")

    # ==========================================================================
    # ステップ4: apksigner で全 APK に署名
    # ==========================================================================
    if all_generated_assets:
        print("\n[STEP 4] Signing APKs with apksigner...")
        
        # 署名には PKCS12 キーストアを使う（BKS だと Windows の標準 JDK では読めないため）
        keystore_path = os.path.abspath("ks_pkcs12.keystore")
        if not os.path.exists(keystore_path):
            print(f"  -> [ERROR] Keystore file not found at {keystore_path}")
            sys.exit(1)
        
        signed_assets = []
        for apk_path in all_generated_assets:
            if not os.path.exists(apk_path):
                print(f"  -> [WARNING] {apk_path} is missing, skipping.")
                continue
            
            temp_signed = apk_path + ".signed"
            cmd = [
                APKSIGNER_PATH, "sign",
                "--ks", keystore_path,
                "--ks-pass", "pass:123456789",
                "--ks-key-alias", "jhc",
                "--key-pass", "pass:123456789",
                "--out", temp_signed,
                apk_path
            ]
            print(f"  -> Signing {os.path.basename(apk_path)} ...")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"  -> [ERROR] apksigner failed for {apk_path}:\n{res.stderr}")
                sys.exit(1)
            
            # 未署名のファイルを署名済みに置き換え
            os.replace(temp_signed, apk_path)
            signed_assets.append(apk_path)
            print(f"  -> Signed: {os.path.basename(apk_path)}")
        
        all_generated_assets = signed_assets
        print("  -> All APKs signed successfully.")

    # 最終クリーンアップ
    cleanup_workspace(is_initial=False)

    # GitHub へリリース
    if all_generated_assets:
        print(f"  -> [DEBUG] Assets to upload: {all_generated_assets}")
        upload_to_github_release(piko_tag, all_generated_assets, is_pre)

    print("\n=======================================================")
    print(" BUILD PIPELINE COMPLETED SUCCESSFULLY")
    print("=======================================================\n")

if __name__ == "__main__":
    main()