"""
Phase 6 -- deployment hardening tests: production settings, the model-artifact
bootstrap (verify / download / refuse bad files), require-models readiness,
version consistency and manifest integrity. No network and no real models needed.
"""

import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.artifacts import ensure_model_artifacts, sha256_of
from src.api.config import API_VERSION, Settings, load_settings
from src.api.main import create_app
from src.api.service import ResQAIApplicationService
from src.severity_predictor import SeverityPredictor

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- settings


def test_production_flags_default_to_off_and_parse_booleans():
    s = load_settings({})
    assert (s.require_models, s.bootstrap_models, s.model_artifact_base_url) == (False, False, None)
    s = load_settings({"RESQAI_REQUIRE_MODELS": "TRUE", "RESQAI_BOOTSTRAP_MODELS": "1",
                       "RESQAI_MODEL_ARTIFACT_BASE_URL": "https://example.test/rel/ "})
    assert (s.require_models, s.bootstrap_models) == (True, True)
    assert s.model_artifact_base_url == "https://example.test/rel"


def test_invalid_boolean_setting_is_rejected():
    with pytest.raises(ValueError):
        load_settings({"RESQAI_REQUIRE_MODELS": "maybe"})


def test_origin_trailing_slash_is_stripped():
    assert load_settings({"RESQAI_ALLOWED_ORIGINS": "https://app.example/"}).allowed_origins == ("https://app.example",)


# ---------------------------------------------------------------- version (single source)


def test_version_comes_from_the_version_file_and_matches_the_frontend_package():
    version = (ROOT / "VERSION").read_text().strip()
    assert API_VERSION == version
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert package["version"] == version, "frontend/package.json version must equal VERSION"
    manifest = json.loads((ROOT / "deployment" / "model_artifacts.json").read_text())
    assert manifest["release"] == f"v{version}"


# ---------------------------------------------------------------- manifest integrity (tracked files)


def test_bundled_files_match_their_pinned_checksums():
    manifest = json.loads((ROOT / "deployment" / "model_artifacts.json").read_text())
    for item in manifest["bundled"]:
        path = ROOT / item["source"]
        assert path.stat().st_size == item["size_bytes"], f"{item['source']}: size differs (line endings?)"
        assert sha256_of(path) == item["sha256"], f"{item['source']}: checksum differs"


def test_manifest_lists_only_the_two_inference_models_and_uses_https():
    manifest = json.loads((ROOT / "deployment" / "model_artifacts.json").read_text())
    assert {d["name"] for d in manifest["downloads"]} == {
        "random_forest.joblib", "report_compatible_random_forest.joblib"}
    assert manifest["base_url"].startswith("https://")
    assert all(len(d["sha256"]) == 64 for d in manifest["downloads"])


def test_no_raw_crss_or_model_binaries_are_tracked_by_the_deployment_folder():
    files = [p.name for p in (ROOT / "deployment").rglob("*") if p.is_file()]
    assert not any(n.endswith((".joblib", ".csv", ".zip")) for n in files)


# ---------------------------------------------------------------- bootstrap


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _make_release(tmp_path: Path, payloads: dict):
    """A fake release: a manifest + an opener that serves `payloads` by URL suffix."""
    downloads = [
        {"name": name, "dest": f"models/{name}", "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
        for name, data in payloads.items()
    ]
    bundled_src = tmp_path / "deployment" / "meta.json"
    bundled_src.parent.mkdir(parents=True)
    bundled_src.write_bytes(b'{"k": 1}')
    manifest = {
        "release": "v-test", "base_url": "https://example.test/rel", "downloads": downloads,
        "bundled": [{"source": "deployment/meta.json", "dest": "artifacts/meta.json",
                     "sha256": hashlib.sha256(b'{"k": 1}').hexdigest(), "size_bytes": 8}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def _opener_for(served: dict, calls: list):
    def opener(url, timeout=None):
        calls.append(url)
        return _Response(served[url.rsplit("/", 1)[1]])
    return opener


def test_bootstrap_downloads_verifies_and_installs(tmp_path):
    payloads = {"a.joblib": b"model-a-bytes" * 100}
    manifest = _make_release(tmp_path, payloads)
    calls: list = []
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(payloads, calls))
    assert report.ok
    assert {o.name: o.status for o in report.outcomes} == {"deployment/meta.json": "installed", "a.joblib": "downloaded"}
    assert (tmp_path / "models" / "a.joblib").read_bytes() == payloads["a.joblib"]
    assert (tmp_path / "artifacts" / "meta.json").exists()
    assert calls == ["https://example.test/rel/a.joblib"]
    assert not list(tmp_path.rglob("*.part"))


def test_bootstrap_is_idempotent_and_skips_a_verified_file(tmp_path):
    payloads = {"a.joblib": b"x" * 500}
    manifest = _make_release(tmp_path, payloads)
    ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(payloads, []))
    calls: list = []
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(payloads, calls))
    assert report.ok and calls == []  # nothing re-downloaded
    assert {o.status for o in report.outcomes} == {"verified"}


def test_bootstrap_never_installs_a_file_with_the_wrong_checksum(tmp_path):
    payloads = {"a.joblib": b"good-model" * 50}
    manifest = _make_release(tmp_path, payloads)
    tampered = {"a.joblib": b"EVIL-model" * 50}  # same length, different content
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(tampered, []))
    assert not report.ok
    failed = next(o for o in report.outcomes if o.name == "a.joblib")
    assert failed.status == "failed" and "SHA-256" in failed.detail
    assert not (tmp_path / "models" / "a.joblib").exists()
    assert not list(tmp_path.rglob("*.part"))


def test_bootstrap_replaces_an_existing_wrong_file_with_a_verified_one(tmp_path):
    payloads = {"a.joblib": b"right" * 200}
    manifest = _make_release(tmp_path, payloads)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "a.joblib").write_bytes(b"stale or wrong model")
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(payloads, []))
    assert report.ok
    assert (tmp_path / "models" / "a.joblib").read_bytes() == payloads["a.joblib"]


@pytest.mark.parametrize("served", [b"short", b"way-too-long-" * 100])
def test_bootstrap_rejects_truncated_and_oversized_downloads(tmp_path, served):
    payloads = {"a.joblib": b"expected-content" * 20}
    manifest = _make_release(tmp_path, payloads)
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for({"a.joblib": served}, []))
    assert not report.ok
    assert not (tmp_path / "models" / "a.joblib").exists()


def test_bootstrap_refuses_plain_http_to_a_remote_host_but_allows_localhost(tmp_path):
    payloads = {"a.joblib": b"y" * 100}
    manifest = _make_release(tmp_path, payloads)
    bad = ensure_model_artifacts(manifest, root=tmp_path, base_url_override="http://evil.example/rel",
                                 opener=_opener_for(payloads, []))
    assert not bad.ok and not (tmp_path / "models" / "a.joblib").exists()
    good = ensure_model_artifacts(manifest, root=tmp_path, base_url_override="http://127.0.0.1:9/rel",
                                  opener=_opener_for(payloads, []))
    assert good.ok


def test_bootstrap_reports_a_failed_download_instead_of_raising(tmp_path):
    manifest = _make_release(tmp_path, {"a.joblib": b"z" * 10})

    def broken(url, timeout=None):
        raise OSError("connection reset")

    report = ensure_model_artifacts(manifest, root=tmp_path, opener=broken)
    assert not report.ok


def test_bootstrap_rejects_a_bundled_file_that_does_not_match_its_checksum(tmp_path):
    payloads = {"a.joblib": b"q" * 10}
    manifest = _make_release(tmp_path, payloads)
    (tmp_path / "deployment" / "meta.json").write_bytes(b'{"k": 2}')  # altered
    report = ensure_model_artifacts(manifest, root=tmp_path, opener=_opener_for(payloads, []))
    assert not report.ok
    assert not (tmp_path / "artifacts" / "meta.json").exists()


# ---------------------------------------------------------------- readiness with required models


def _no_models():
    missing = SeverityPredictor(model_path="does/not/exist.joblib", feature_metadata_path="does/not/exist.json")
    return {"phase1_historical_model": missing, "report_compatible_model": missing}


def _client(require_models: bool) -> TestClient:
    settings = Settings(environment="test", log_level="INFO", allowed_origins=("http://localhost:5173",),
                        require_models=require_models)
    service = ResQAIApplicationService(environment="test", require_models=require_models,
                                       predictors_provider=_no_models)
    return TestClient(create_app(settings, service))


def test_ready_is_not_ready_when_models_are_required_but_missing():
    with _client(True) as client:
        ready = client.get("/api/v1/ready")
        health = client.get("/api/v1/health").json()
        analyze = client.post("/api/v1/analyze", json={"raw_text": "A car crashed at an intersection."})
    assert ready.status_code == 503 and ready.json()["status"] == "NOT_READY"
    assert any("historical_model" in r for r in ready.json()["reasons"])
    assert "does/not/exist" not in ready.text and ".joblib" not in ready.text
    assert health["status"] == "degraded"  # analysis itself still works; only readiness is stricter
    assert analyze.status_code == 200 and analyze.json()["ml_prediction"]["available"] is False


def test_ready_stays_ready_without_models_when_they_are_not_required():
    with _client(False) as client:
        assert client.get("/api/v1/ready").json()["status"] == "READY"
