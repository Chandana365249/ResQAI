"""
api/artifacts.py

Model-artifact bootstrap for deployment (Phase 6, Steps 20-22).

The trained models are git-ignored, so a fresh clone (e.g. on the hosting
platform) has no models/*.joblib. When RESQAI_BOOTSTRAP_MODELS=true this
module, at startup:

  1. reads the tracked manifest deployment/model_artifacts.json
     (release version, artifact base URL, pinned SHA-256 + size for each file);
  2. installs the tracked, safe metadata/metrics JSON files to where the core
     expects them (artifacts/...), verifying each checksum;
  3. for each model file: keeps it if it already matches the pinned SHA-256,
     otherwise downloads it, verifies size AND SHA-256, and only then moves it
     into place.

A file that fails verification is NEVER installed: the temporary download is
deleted, the artifact is reported as failed, and the API then reports the
model as unavailable (and /ready NOT_READY when RESQAI_REQUIRE_MODELS=true).
A wrong or corrupted model is never silently used.

Only manifest-defined names are ever fetched (no user input reaches a URL or
path), and plain http is accepted only for localhost (used to rehearse the
download locally).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("resqai.api")

DEFAULT_MANIFEST_PATH = Path("deployment/model_artifacts.json")
DOWNLOAD_TIMEOUT_SECONDS = 120
_CHUNK = 1 << 20
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


@dataclass
class ArtifactOutcome:
    name: str
    status: str  # "verified" | "downloaded" | "installed" | "failed"
    detail: str = ""


@dataclass
class BootstrapReport:
    release: str = ""
    outcomes: List[ArtifactOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.outcomes) and all(o.status != "failed" for o in self.outcomes)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches(path: Path, sha256: str, size_bytes: int) -> bool:
    return path.is_file() and path.stat().st_size == size_bytes and sha256_of(path) == sha256


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS:
        return
    raise ValueError("Artifact URLs must use https (http is allowed only for localhost).")


def _download(url: str, target: Path, sha256: str, size_bytes: int, opener: Callable) -> None:
    """Stream to a temporary file, verify, then atomically move into place."""
    _check_url(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with opener(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, open(temp, "wb") as out:
            for chunk in iter(lambda: response.read(_CHUNK), b""):
                received += len(chunk)
                if received > size_bytes:  # more data than the manifest allows: stop early
                    raise ValueError("Downloaded file is larger than the pinned size.")
                digest.update(chunk)
                out.write(chunk)
        if received != size_bytes:
            raise ValueError(f"Downloaded size {received} does not match the pinned size {size_bytes}.")
        if digest.hexdigest() != sha256:
            raise ValueError("Downloaded file's SHA-256 does not match the pinned checksum.")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def ensure_model_artifacts(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    root: Path = Path("."),
    base_url_override: Optional[str] = None,
    opener: Callable = urllib.request.urlopen,
) -> BootstrapReport:
    """Verify (and download if needed) every artifact in the manifest. Never raises for a
    verification/download problem; those are recorded as failed outcomes."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    base_url = (base_url_override or manifest["base_url"]).rstrip("/")
    report = BootstrapReport(release=manifest["release"])

    for item in manifest.get("bundled", []):
        name, source, dest = item["source"], root / item["source"], root / item["dest"]
        try:
            if not _matches(source, item["sha256"], item["size_bytes"]):
                raise ValueError("Bundled file is missing or does not match its pinned checksum.")
            if _matches(dest, item["sha256"], item["size_bytes"]):
                report.outcomes.append(ArtifactOutcome(name, "verified"))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            report.outcomes.append(ArtifactOutcome(name, "installed"))
        except Exception as exc:  # noqa: BLE001 -- recorded, never raised
            logger.warning("Artifact %s failed: %s", name, exc)
            report.outcomes.append(ArtifactOutcome(name, "failed", str(exc)))

    for item in manifest.get("downloads", []):
        name, dest = item["name"], root / item["dest"]
        try:
            if _matches(dest, item["sha256"], item["size_bytes"]):
                report.outcomes.append(ArtifactOutcome(name, "verified"))
                continue
            _download(f"{base_url}/{name}", dest, item["sha256"], item["size_bytes"], opener)
            report.outcomes.append(ArtifactOutcome(name, "downloaded"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Artifact %s failed: %s", name, exc)
            report.outcomes.append(ArtifactOutcome(name, "failed", str(exc)))
    return report
