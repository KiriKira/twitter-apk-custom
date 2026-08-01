import glob
import os
import re
import shutil
import subprocess
import sys
import urllib.request

import main_manual
from download_bins import download_apkeditor, download_morphe_cli
from main_manual import (
    BASE_APK_DIR,
    BINS_DIR,
    OUTPUT_DIR,
    apply_shim,
    extract_version_from_filename,
    fetch_x_shim,
    get_target_patches,
    is_version_greater_than,
    is_version_less_than,
    run_morphe_and_extract,
)
from utils import merge_apk


def env(name, default=""):
    value = os.environ.get(name, "").strip()
    return value if value else default


def ensure_dirs():
    os.makedirs(BASE_APK_DIR, exist_ok=True)
    os.makedirs(BINS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def download_if_needed(url, out):
    if os.path.exists(out):
        return out
    print(f"Downloading {url} -> {out}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(out, "wb") as handle:
        shutil.copyfileobj(response, handle)
    return out


def prepare_inputs():
    ensure_dirs()

    base_apk_path = env("BASE_APK_PATH")
    base_apk_url = env("BASE_APK_URL")
    if base_apk_url:
        filename = os.path.basename(base_apk_url.split("?")[0]) or "base.apk"
        if not filename.lower().endswith((".apk", ".apkm", ".apks", ".xapk")):
            filename = "base.xapk"
        base_apk_path = download_if_needed(base_apk_url, os.path.join(BASE_APK_DIR, filename))

    if not base_apk_path:
        candidates = glob.glob(os.path.join(BASE_APK_DIR, "*"))
        if candidates:
            base_apk_path = candidates[0]

    if not base_apk_path or not os.path.exists(base_apk_path):
        raise RuntimeError("Set BASE_APK_URL or BASE_APK_PATH, or place a base APK/APKM in .base_apk/")

    piko_mpp_path = env("PIKO_MPP_PATH", os.path.join(BINS_DIR, "patches.mpp"))
    piko_mpp_url = env("PIKO_MPP_URL")
    if piko_mpp_url:
        piko_mpp_path = download_if_needed(piko_mpp_url, os.path.join(BINS_DIR, "patches.mpp"))

    if not os.path.exists(piko_mpp_path):
        raise RuntimeError("Set PIKO_MPP_URL or PIKO_MPP_PATH, or copy patches.mpp to bins/")

    if not os.path.exists(os.path.join(BINS_DIR, "apkeditor.jar")):
        download_apkeditor()
    if not os.path.exists(os.path.join(BINS_DIR, "morphe-cli.jar")):
        download_morphe_cli()

    return base_apk_path, piko_mpp_path


def selected_variants(version):
    all_variants = {
        "x": {
            "output": f"x-piko-v{version}.apk",
            "includes": [],
            "excludes": ["Dynamic color"],
        },
        "x-material": {
            "output": f"x-piko-material-you-v{version}.apk",
            "includes": ["Dynamic color"],
            "excludes": [],
        },
        "twitter": {
            "output": f"twitter-piko-v{version}.apk",
            "includes": ["Bring back twitter"],
            "excludes": ["Dynamic color"],
        },
        "twitter-material": {
            "output": f"twitter-piko-material-you-v{version}.apk",
            "includes": ["Bring back twitter", "Dynamic color"],
            "excludes": [],
        },
    }

    requested = [item.strip() for item in env("BUILD_VARIANTS", "x").split(",") if item.strip()]
    if "all" in requested:
        requested = list(all_variants.keys())

    unknown = [item for item in requested if item not in all_variants]
    if unknown:
        raise RuntimeError(f"Unknown BUILD_VARIANTS: {', '.join(unknown)}")

    return [all_variants[item] for item in requested]


def prepare_base_apk(base_apk_path):
    filename = os.path.basename(base_apk_path).lower()
    version = env("BASE_APK_VERSION") or extract_version_from_filename(filename)
    is_bundle = filename.endswith((".apkm", ".apks", ".xapk"))
    working_file = "big_file.apkm" if is_bundle else "big_file_merged.apk"

    for path in glob.glob("big_file*"):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)

    shutil.copy(base_apk_path, working_file)
    target_merged = "big_file_merged.apk"

    if is_bundle:
        merge_apk(working_file)
        if os.path.exists(working_file):
            os.remove(working_file)
    elif working_file != target_merged:
        shutil.move(working_file, target_merged)

    if not os.path.exists(target_merged):
        raise RuntimeError("Merged base APK was not created")

    return target_merged, version


def build_variants(base_apk_path, patch_mpp_path):
    cli_jar = os.path.join(BINS_DIR, "morphe-cli.jar")
    target_merged, version = prepare_base_apk(base_apk_path)

    if is_version_greater_than(version, "11.88") and is_version_less_than(version, "12.5"):
        shim_mpp = fetch_x_shim()
        if shim_mpp:
            target_merged = apply_shim(cli_jar, shim_mpp, target_merged)

    common_includes = get_target_patches(
        cli_jar,
        patch_mpp_path,
        "com.twitter.android",
        excludes=["Bring back twitter", "Change version code", "Dynamic color"],
    )

    outputs = []
    for variant in selected_variants(version):
        output = run_morphe_and_extract(
            cli_jar,
            patch_mpp_path,
            target_merged,
            variant["output"],
            common_includes + variant["includes"],
            variant["excludes"],
        )
        outputs.append(output)
    return outputs


def find_zipalign():
    found = shutil.which("zipalign")
    if found:
        return found
    apksigner = main_manual.APKSIGNER_PATH
    if apksigner:
        candidate = os.path.join(os.path.dirname(apksigner), "zipalign")
        if os.name == "nt":
            candidate += ".exe"
        if os.path.exists(candidate):
            return candidate
    return None


def sign_outputs(apks):
    if env("SKIP_SIGNING", "false").lower() == "true":
        print("Skipping signing because SKIP_SIGNING=true")
        return apks

    apksigner = main_manual.APKSIGNER_PATH
    if not apksigner:
        raise RuntimeError("apksigner was not found")

    keystore = env("SIGNING_KEYSTORE_PATH", "ks_pkcs12.keystore")
    keystore_password = env("KEYSTORE_PASSWORD", "123456789")
    key_alias = env("KEY_ALIAS", "jhc")
    key_password = env("KEY_PASSWORD", keystore_password)
    if not os.path.exists(keystore):
        raise RuntimeError(f"Keystore not found: {keystore}")

    zipalign = find_zipalign()
    signed = []
    for apk_path in apks:
        if zipalign:
            aligned = apk_path + ".aligned.apk"
            subprocess.run([zipalign, "-p", "-f", "4", apk_path, aligned], check=True)
            os.replace(aligned, apk_path)

        out = apk_path + ".signed.apk"
        subprocess.run(
            [
                apksigner,
                "sign",
                "--ks",
                keystore,
                "--ks-pass",
                f"pass:{keystore_password}",
                "--ks-key-alias",
                key_alias,
                "--key-pass",
                f"pass:{key_password}",
                "--out",
                out,
                apk_path,
            ],
            check=True,
        )
        os.replace(out, apk_path)
        signed.append(apk_path)
    return signed


def apply_version_revision(apks):
    offset_text = env("VERSION_CODE_OFFSET")
    if not offset_text:
        return apks

    try:
        offset = int(offset_text)
    except ValueError as error:
        raise RuntimeError("VERSION_CODE_OFFSET must be a positive integer") from error
    if offset <= 0:
        raise RuntimeError("VERSION_CODE_OFFSET must be a positive integer")

    apkeditor = os.path.join(BINS_DIR, "apkeditor.jar")
    updated = []
    for apk_path in apks:
        decoded_dir = apk_path + ".versioned"
        rebuilt_apk = apk_path + ".versioned.apk"
        if os.path.exists(decoded_dir):
            shutil.rmtree(decoded_dir)
        if os.path.exists(rebuilt_apk):
            os.remove(rebuilt_apk)

        subprocess.run(
            ["java", "-jar", apkeditor, "d", "-dex", "-i", apk_path, "-o", decoded_dir],
            check=True,
        )
        manifest_path = os.path.join(decoded_dir, "AndroidManifest.xml")
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            manifest = manifest_file.read()

        version_code_pattern = r'(android:versionCode\s*=\s*")[^"]+("\s*)'
        version_code_match = re.search(version_code_pattern, manifest)
        if not version_code_match:
            raise RuntimeError(f"Could not find android:versionCode in {apk_path}")
        version_code = int(version_code_match.group(0).split('"')[1], 0) + offset
        if version_code > 2147483647:
            raise RuntimeError("Revised versionCode exceeds Android's maximum value")
        manifest = re.sub(
            version_code_pattern,
            lambda match: match.group(1) + str(version_code) + match.group(2),
            manifest,
            count=1,
        )
        version_code_major_pattern = r'(android:versionCodeMajor\s*=\s*")[^"]+("\s*)'
        if re.search(version_code_major_pattern, manifest):
            manifest = re.sub(
                version_code_major_pattern,
                lambda match: match.group(1) + "1" + match.group(2),
                manifest,
                count=1,
            )
        else:
            manifest, namespace_replacements = re.subn(
                r'(xmlns:android\s*=\s*"[^"]+")',
                lambda match: match.group(1) + ' android:versionCodeMajor="1"',
                manifest,
                count=1,
            )
            if namespace_replacements != 1:
                raise RuntimeError(f"Could not add android:versionCodeMajor to {apk_path}")
        manifest = re.sub(
            r'(android:versionName\s*=\s*")([^"]+)("\s*)',
            lambda match: match.group(1) + match.group(2) + f"-piko.{offset}" + match.group(3),
            manifest,
            count=1,
        )
        with open(manifest_path, "w", encoding="utf-8", newline="") as manifest_file:
            manifest_file.write(manifest)

        subprocess.run(
            ["java", "-jar", apkeditor, "b", "-f", "-i", decoded_dir, "-o", rebuilt_apk],
            check=True,
        )
        os.replace(rebuilt_apk, apk_path)
        shutil.rmtree(decoded_dir)
        print(f"Updated {apk_path}: versionCode={version_code}, versionCodeMajor=1")
        updated.append(apk_path)
    return updated


def main():
    base_apk_path, patch_mpp_path = prepare_inputs()
    outputs = build_variants(base_apk_path, patch_mpp_path)
    signed = sign_outputs(apply_version_revision(outputs))
    print("Built APKs:")
    for apk_path in signed:
        print(f"  {apk_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
