# Twitter APK (Piko Patches) - Enhanced Builder

[![Build Status](https://github.com/monsivamon/twitter-apk/actions/workflows/build.yaml/badge.svg)](https://github.com/monsivamon/twitter-apk/actions)
[![Latest Release](https://img.shields.io/github/v/release/monsivamon/twitter-apk)](https://github.com/monsivamon/twitter-apk/releases/latest)

Automated build system for applying [Piko](https://github.com/crimera/piko) patches to the Twitter/X Android app.
This repository is an enhanced fork optimized for faster updates and modern tooling.

## ✨ Key Features & Improvements

### 1. Always Latest Patches
Even if the Twitter APK version hasn't changed, the system detects updates to **Piko patches** and rebuilds automatically.

### 2. Pre-release Patch Support
Includes support for Piko `pre-release` patches to get the latest features faster.

### 3. Powered by Morphe CLI
The build pipeline has been fully migrated to **Morphe CLI**. Legacy ReVanced CLI is no longer used.

### 4. Daily Automation
Checks for updates every day at **16:00 JST**.

## 📥 Download

Get the latest pre-built APK from the **[Releases Page](https://github.com/monsivamon/twitter-apk/releases)**.

## Credits

* [crimera/piko](https://github.com/crimera/piko) - The patch source.
* [MorpheApp/morphe-cli](https://github.com/MorpheApp/morphe-cli) - Morphe CLI.
* [REAndroid/APKEditor](https://github.com/REAndroid/APKEditor) - APK merging tool.
