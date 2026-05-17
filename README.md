# Twitter/X APK (Piko Patches) - Enhanced Builder

[![Build Status](https://github.com/monsivamon/twitter-apk/actions/workflows/build.yaml/badge.svg)](https://github.com/monsivamon/twitter-apk/actions)
[![Stable Release](https://img.shields.io/github/v/release/monsivamon/twitter-apk?label=Stable&color=success)](https://github.com/monsivamon/twitter-apk/releases/latest)
[![Pre-Release](https://img.shields.io/github/v/release/monsivamon/twitter-apk?include_prereleases&label=Pre-Release&color=orange)](https://github.com/monsivamon/twitter-apk/releases)

Automated build system for applying [Piko](https://github.com/crimera/piko) patches to Twitter/X .
This repository is an enhanced fork optimized for faster updates, dynamic version targeting, and modern tooling.

## ✨ Key Features & Improvements

### 1. Always Latest Patches
Even if the base APK version hasn't changed, the system detects updates to **Piko patches** and rebuilds automatically.

### 2. Stable & Pre-release Support
Fully tracks and supports both stable (`main`) and pre-release (`dev`) branches of Piko patches simultaneously.

### 3. Powered by Morphe CLI & Sniper Mode
The build pipeline has been fully migrated to **Morphe CLI**. It dynamically extracts supported versions from the patch configuration JSON and fetches the exact base APK automatically.

### 4. Daily Automation
Checks for updates every day at **16:00 JST**.

## 📥 Download

Choose the version that best suits your needs:

* **[🌟 Stable Version (Recommended)](https://github.com/monsivamon/twitter-apk/releases/latest)**
    * Built with Piko's `main` branch. Safe and stable for daily use.
* **[🧪 Pre-release Version (Beta)](https://github.com/monsivamon/twitter-apk/releases)**
    * Built with Piko's `dev` branch. Try out the newest experimental features! *(Look for the `Pre-release` label in the list).*

## Credits

* [crimera/piko](https://github.com/crimera/piko) - The patch source.
* [MorpheApp/morphe-cli](https://github.com/MorpheApp/morphe-cli) - Morphe CLI.
* [REAndroid/APKEditor](https://github.com/REAndroid/APKEditor) - APK merging tool.