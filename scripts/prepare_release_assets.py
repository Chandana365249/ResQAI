"""
scripts/prepare_release_assets.py

Phase 6, Steps 20-22: prepares the versioned MODEL RELEASE ARTIFACTS.

The trained models are git-ignored (84.6 MB + 14.8 MB) and must never be
committed. Instead they are published as GitHub Release assets and the
deployed API downloads and VERIFIES them at startup
(src/api/artifacts.py). This script:

  1. copies the two inference models into ./release-assets/ (git-ignored),
     ready to upload as assets of the GitHub release for VERSION;
  2. writes release-assets/SHA256SUMS.txt;
  3. copies the safe, public metadata/metrics JSON files VERBATIM (bytes
     unchanged, so no number is altered) into the tracked deployment/ tree;
  4. (re)writes deployment/model_artifacts.json -- the tracked manifest that
     pins each artifact's SHA-256 and size.

Run from the project root after (re)training:

    python scripts/prepare_release_assets.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release-assets"
MANIFEST_PATH = ROOT / "deployment" / "model_artifacts.json"

# (asset name shipped in the release, local model file)
MODELS = [
    ("random_forest.joblib", ROOT / "models" / "random_forest.joblib"),
    ("report_compatible_random_forest.joblib", ROOT / "models" / "report_compatible_random_forest.joblib"),
]
# (tracked copy under deployment/, where the running code expects it, original)
BUNDLED = [
    ("deployment/model_metadata/feature_metadata.json", "artifacts/feature_metadata.json"),
    ("deployment/model_metadata/report_compatible_feature_metadata.json", "artifacts/report_compatible_feature_metadata.json"),
    ("deployment/model_metrics/historical_model.json", "artifacts/metrics.json"),
    ("deployment/model_metrics/report_compatible_model.json", "artifacts/report_compatible_metrics.json"),
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_repo() -> str:
    """owner/repo from the git remote (never guessed)."""
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    slug = url.removesuffix(".git").split("github.com/")[-1].split("github.com:")[-1]
    if slug.count("/") != 1:
        sys.exit(f"Cannot derive owner/repo from remote URL {url!r}.")
    return slug


def main() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    release = f"v{version}"
    RELEASE_DIR.mkdir(exist_ok=True)

    downloads, sums = [], []
    for name, source in MODELS:
        if not source.exists():
            sys.exit(f"Missing {source}. Train the models first (see docs/ML_PIPELINE.md).")
        target = RELEASE_DIR / name
        shutil.copyfile(source, target)
        digest = sha256_of(target)
        downloads.append({"name": name, "dest": f"models/{name}", "sha256": digest, "size_bytes": target.stat().st_size})
        sums.append(f"{digest}  {name}")
    (RELEASE_DIR / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")

    bundled = []
    for tracked, original in BUNDLED:
        src, dst = ROOT / original, ROOT / tracked
        if not src.exists():
            sys.exit(f"Missing {src}.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)  # byte-for-byte: no value is altered
        bundled.append({"source": tracked, "dest": original, "sha256": sha256_of(dst), "size_bytes": dst.stat().st_size})

    manifest = {
        "release": release,
        "base_url": f"https://github.com/{github_repo()}/releases/download/{release}",
        "downloads": downloads,
        "bundled": bundled,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Release {release}: wrote {MANIFEST_PATH.relative_to(ROOT)}")
    for d in downloads:
        print(f"  {d['name']}  {d['size_bytes'] / 1e6:6.1f} MB  sha256={d['sha256']}")
    print(f"Upload the files in {RELEASE_DIR.relative_to(ROOT)}/ as assets of the GitHub release '{release}'.")


if __name__ == "__main__":
    main()
