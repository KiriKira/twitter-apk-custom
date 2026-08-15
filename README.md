# Twitter/X & Instagram APK (Piko Patches) - Local Builder

[![Latest Release](https://img.shields.io/github/v/release/KiriKira/twitter-apk-custom?label=Latest&color=success)](https://github.com/KiriKira/twitter-apk-custom/releases/latest)
[![Build workflow](https://img.shields.io/github/actions/workflow/status/KiriKira/twitter-apk-custom/build-twitter-apk.yml?label=Build)](https://github.com/KiriKira/twitter-apk-custom/actions/workflows/build-twitter-apk.yml)

A Python-based build system for applying the private `KiriKira/piko-custom` patch set to X/Twitter.

## Automated upstream builds

`Build Twitter APK` polls `KiriKira/piko-custom` `main` every six hours. When its commit changes, GitHub Actions builds the configured X base APK and publishes one GitHub Release named after that exact upstream commit. Repeated polls do not rebuild an already released revision.

The scheduled build uses the existing repository secrets: `PIKO_REPO_TOKEN`, `ANDROID_KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, and `KEY_PASSWORD`. The base APK is resolved automatically: the workflow queries APKPure for the latest stable X release before every build (`resolve_base_apk.py`). You can still start a manual build from the **Actions** tab to override the source, variants, base APK URL, or release tag.

## 📦 About Releases
APKs on this repository's Releases page are built by GitHub Actions whenever a new `KiriKira/piko-custom` `main` revision is detected. Manual/local building remains available below.

## 🛠️ How to Build Locally (and Upload to Your Repo)

If you want to apply patches and build on your own local machine, and **upload the release to your own repository**, please follow the steps below.

### Prerequisites
* **Windows OS** (This script is intended and optimized for Windows environments).
* **Python 3.x** installed.
* **Java (JDK 17 or 21)** installed and added to your system's `PATH`.
* **GitHub CLI (`gh`)** installed and authenticated (`gh auth login`) with **your own account**.
* A valid **PKCS12 format** keystore file named **`ks_pkcs12.keystore`** placed in the root directory.
* **`apksigner`** (from Android SDK Build-Tools) installed and accessible in your `PATH` (used for reliably signing massive APKs like Instagram).

### ⚠️ Important Note (Script Modification)
Even if you are authenticated with the GitHub CLI, if the repository settings in the script remain as `monsivamon/twitter-apk`, the release upload will fail with a permission error.
**Before running the build, you MUST change the repository name in `main_manual.py` (e.g., `GITHUB_REPO = "monsivamon/twitter-apk"`) to your own repository name.**

### Usage
1. Fork this repository to your own account, or clone it locally.
2. **Modify the repository settings in the script to your own, as described in the "Important Note" above.** *(Change `GITHUB_REPO = "monsivamon/twitter-apk"`)*
3. Create a folder named `.base_apk` in the root directory.
4. Place your unpatched Twitter/X or Instagram APKs (or `.apkm` bundles) inside the `.base_apk` folder.
5. Open Command Prompt or PowerShell and run the builder script:

```cmd
python main_manual.py
```

6. **Choose your desired execution mode from the interactive menu (e.g., `[1] Full Build`, `[4] Upload Only`).**
7. Choose your target branch (Stable/Pre-release) when prompted. The script will automatically handle merging, shim application (if necessary), patching, signing (using `apksigner` and your `ks_pkcs12.keystore`), and creating/uploading the release to your own repository.

## 📥 Download

If you just want the pre-built APKs, choose the version that best suits your needs:

* **[🌟 Stable Version (Recommended)](https://github.com/monsivamon/twitter-apk/releases/latest)**
    * Built with Piko's `main` branch. Safe and stable for daily use.
* **[🧪 Pre-release Version (Beta)](https://github.com/monsivamon/twitter-apk/releases)**
    * Built with Piko's `dev` branch. Try out the newest experimental features! *(Look for the `Pre-release` label in the list).*

## Credits

* [crimera/piko](https://github.com/crimera/piko) - The patch source.
* [inotia00/x-shim](https://gitlab.com/inotia00/x-shim) - Piko compatibility shim for newer X versions.
* [MorpheApp/morphe-cli](https://github.com/MorpheApp/morphe-cli) - Morphe CLI patcher.
* [REAndroid/APKEditor](https://github.com/REAndroid/APKEditor) - APK merging tool.
* [Android SDK build-tools (apksigner)](https://developer.android.com/studio/command-line/apksigner) - Reliable APK signing tool for massive files.