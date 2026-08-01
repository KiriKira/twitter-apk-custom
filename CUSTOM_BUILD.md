# Custom Piko APK Builder

This private builder keeps `monsivamon/twitter-apk` usable as an upstream while adding a non-interactive GitHub Actions build path.

## GitHub Actions Inputs

Run **Build Twitter APK** manually with:

- `base_apk_url`: direct URL to the unpatched X/Twitter APK, APKM, APKS, or XAPK.
- `base_apk_version`: label used in the output filename.
- `version_code_offset`: optional positive number added to the base APK's Android `versionCode`. It defaults to the Actions run number so a re-patched APK is a direct update when signed with the same keystore.
- `piko_repository`: your private Piko repository, for example `OWNER/piko-custom`.
- `piko_ref`: branch, tag, or SHA to build.
- `build_variants`: `x`, `x-material`, `twitter`, `twitter-material`, or `all`.

If `base_apk_url` is omitted, set a repository secret named `BASE_APK_URL`.

## Required Secrets

- `PIKO_REPO_TOKEN`: PAT with read access to the private Piko repository, if `GITHUB_TOKEN` cannot read it.
- `ANDROID_KEYSTORE_BASE64`: base64-encoded PKCS12 keystore. If omitted, the checked-in `ks_pkcs12.keystore` is used.
- `KEYSTORE_PASSWORD`
- `KEY_ALIAS`
- `KEY_PASSWORD`

## Releases And Updates

Every custom patch build excludes Piko's `Change version code` patch, then rewrites the APK version fields before signing: the Android `versionCode` remains at the legacy Piko maximum (`2147483647`), the positive `version_code_offset` is written to `versionCodeMajor`, and the version name gains a `-piko.<offset>` suffix. Android compares the combined long version code, so each Actions run is newer than the previous one. Keeping the 32-bit value at the legacy maximum also lets installers that only inspect `versionCode` upgrade an older Piko APK instead of rejecting it as a downgrade.

Use a new release tag for every publish. The release action is configured not to overwrite an existing asset.

## Syncing Upstream

Keep the public upstream as a separate remote:

```bash
git remote add upstream https://github.com/monsivamon/twitter-apk.git
git fetch upstream
git rebase upstream/main
```

Expected local-only files:

- `.github/workflows/build-twitter-apk.yml`
- `build_ci.py`
- `CUSTOM_BUILD.md`

The only intentional upstream file change is:

- `main_manual.py`: `GITHUB_REPO` can be overridden by the `GITHUB_REPO` environment variable.
