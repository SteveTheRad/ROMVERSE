from __future__ import annotations

import base64
import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtWidgets import QApplication, QMessageBox

from romverse.core.settings import AppSettings
from romverse.release import build_release_manifest, create_signed_release_envelope
from romverse.ui import main_window as main_window_module
from romverse.ui.main_window import SettingsDialog, UpdateStageWorker
from romverse.updates import (
    DesktopUpdateCancelled,
    DesktopUpdateError,
    DesktopUpdateService,
    DesktopUpdateTrust,
    load_desktop_update_trust,
)


class Response(BytesIO):
    def __init__(self, payload: bytes, url: str, *, content_length: int | None = None) -> None:
        super().__init__(payload)
        self._url = url
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def geturl(self) -> str:
        return self._url


class Opener:
    def __init__(self, responses: dict[str, tuple[bytes, str, int | None]]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def __call__(self, request, timeout: int):
        del timeout
        url = request.full_url
        self.requests.append(url)
        payload, final_url, content_length = self.responses[url]
        return Response(payload, final_url, content_length=content_length)


def _trust(private_key: Ed25519PrivateKey) -> DesktopUpdateTrust:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return DesktopUpdateTrust(
        True,
        "Production publisher trust is configured.",
        "romverse-release-2026",
        base64.b64encode(raw).decode("ascii"),
        "https://updates.romverse.app/stable/release.json",
        "https://updates.romverse.app/preview/release.json",
    )


def _release(
    tmp_path: Path,
    private_key: Ed25519PrivateKey,
    *,
    version: str = "0.2.0",
    channel: str = "stable",
) -> tuple[bytes, bytes, str]:
    artifact = tmp_path / "ROMVERSE-Desktop-0.2.0-linux-x86_64.zip"
    artifact_bytes = b"verified portable desktop update"
    artifact.write_bytes(artifact_bytes)
    manifest = build_release_manifest(
        version=version,
        channel=channel,
        release_id="romverse-desktop-0.2.0",
        published_at="2026-09-03T11:00:00Z",
        artifacts=(("linux-portable", "linux-x86_64", "archive", artifact),),
    )
    envelope = create_signed_release_envelope(
        manifest,
        private_key,
        "romverse-release-2026",
    )
    return json.dumps(envelope).encode(), artifact_bytes, artifact.name


def test_packaged_update_trust_is_explicitly_unconfigured() -> None:
    trust_path = (
        Path(__file__).parents[1] / "src" / "romverse" / "assets" / "desktop_update_trust.json"
    )

    trust = load_desktop_update_trust(trust_path)

    assert trust.configured is False
    assert "No production-signed public" in trust.reason
    with pytest.raises(DesktopUpdateError, match="No production-signed public"):
        trust.manifest_url("stable")


def test_signed_update_check_and_staging_remain_confirmation_only(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, artifact_bytes, artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"
    artifact_url = f"https://updates.romverse.app/stable/{artifact_name}"
    opener = Opener(
        {
            manifest_url: (metadata, manifest_url, len(metadata)),
            artifact_url: (artifact_bytes, artifact_url, len(artifact_bytes)),
        }
    )
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=opener,
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    progress: list[tuple[int, int]] = []

    candidate = service.check("stable")
    staged = service.stage(
        candidate,
        tmp_path / "Desktop Updates",
        progress=lambda done, total: progress.append((done, total)),
    )

    assert candidate.available is True
    assert candidate.execution_authority == "none"
    assert candidate.automatic_install is False
    assert candidate.requires_explicit_confirmation is True
    assert candidate.artifact_url == artifact_url
    assert staged.artifact_path.read_bytes() == artifact_bytes
    assert staged.execution_authority == "none"
    assert staged.automatic_install is False
    receipt = json.loads(staged.receipt_path.read_text(encoding="utf-8"))
    assert receipt["requires_explicit_confirmation"] is True
    assert receipt["automatic_install"] is False
    assert receipt["workspace_preserved"] is True
    assert receipt["execution_authority"] == "none"
    assert progress[0] == (0, len(artifact_bytes))
    assert progress[-2] == (len(artifact_bytes), len(artifact_bytes))
    assert progress[-1] == (0, 0)


def test_staged_receipt_is_reloaded_and_cancelled_download_leaves_no_partial_file(
    tmp_path: Path,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, artifact_bytes, artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"
    artifact_url = f"https://updates.romverse.app/stable/{artifact_name}"
    opener = Opener(
        {
            manifest_url: (metadata, manifest_url, len(metadata)),
            artifact_url: (artifact_bytes, artifact_url, len(artifact_bytes)),
        }
    )
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=opener,
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    candidate = service.check("stable")
    staged = service.stage(candidate, tmp_path / "verified-stage")

    assert service.verify_staged(candidate, tmp_path / "verified-stage") == staged
    receipt = json.loads(staged.receipt_path.read_text(encoding="utf-8"))
    receipt["automatic_install"] = True
    digest_payload = dict(receipt)
    del digest_payload["receipt_sha256"]
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    staged.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(DesktopUpdateError, match="automatic_install"):
        service.verify_staged(candidate, tmp_path / "verified-stage")

    cancelled = {"requested": False}

    def request_cancel(_done: int, total: int) -> None:
        if total:
            cancelled["requested"] = True

    with pytest.raises(DesktopUpdateCancelled):
        service.stage(
            candidate,
            tmp_path / "cancelled-stage",
            progress=request_cancel,
            should_cancel=lambda: cancelled["requested"],
        )
    cancelled_root = tmp_path / "cancelled-stage"
    assert not tuple(cancelled_root.rglob("*.part"))
    assert not tuple(cancelled_root.rglob("*.zip"))
    assert not tuple(cancelled_root.rglob("*.romverse"))


def test_update_stage_worker_reserves_completion_for_verified_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, artifact_bytes, artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"
    artifact_url = f"https://updates.romverse.app/stable/{artifact_name}"
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=Opener(
            {
                manifest_url: (metadata, manifest_url, len(metadata)),
                artifact_url: (artifact_bytes, artifact_url, len(artifact_bytes)),
            }
        ),
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    candidate = service.check("stable")
    worker = UpdateStageWorker(service, candidate, tmp_path / "worker-stage")
    verified = {"complete": False}
    events: list[tuple[str, object]] = []
    original_verify = service.verify_staged

    def observed_verify(candidate_to_verify, destination):
        result = original_verify(candidate_to_verify, destination)
        verified["complete"] = True
        return result

    monkeypatch.setattr(service, "verify_staged", observed_verify)
    worker.signals.progress.connect(
        lambda value: events.append(("progress", (value, verified["complete"])))
    )
    worker.signals.completed.connect(lambda result: events.append(("completed", result)))

    worker.execute()

    progress_events = [value for event, value in events if event == "progress"]
    assert progress_events[-2:] == [(99, False), (100, True)]
    assert events[-1][0] == "completed"

    failed_worker = UpdateStageWorker(service, candidate, tmp_path / "failed-stage")
    failed_progress: list[int] = []
    failures: list[str] = []
    monkeypatch.setattr(
        service,
        "verify_staged",
        lambda *_args: (_ for _ in ()).throw(DesktopUpdateError("receipt rejected")),
    )
    failed_worker.signals.progress.connect(failed_progress.append)
    failed_worker.signals.failed.connect(failures.append)

    failed_worker.execute()

    assert 100 not in failed_progress
    assert failures == ["receipt rejected"]


def test_settings_requires_confirmation_before_staging_a_verified_update(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    private_key = Ed25519PrivateKey.generate()
    metadata, artifact_bytes, artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"
    artifact_url = f"https://updates.romverse.app/stable/{artifact_name}"
    opener = Opener(
        {
            manifest_url: (metadata, manifest_url, len(metadata)),
            artifact_url: (artifact_bytes, artifact_url, len(artifact_bytes)),
        }
    )
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=opener,
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dialog = SettingsDialog(workspace, AppSettings(), update_service=service)
    monkeypatch.setattr(main_window_module, "start_background", lambda worker: worker.execute())
    try:
        dialog.check_updates_button.click()
        app.processEvents()

        assert dialog.stage_update_button.isVisibleTo(dialog)
        assert "installation remains a separate manual step" in dialog.update_status.text()
        assert opener.requests == [manifest_url]

        monkeypatch.setattr(
            main_window_module.QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )
        dialog.stage_update_button.click()
        assert opener.requests == [manifest_url]
        assert "cancelled before it started" in dialog.update_status.text()

        candidate = dialog._update_candidate
        assert candidate is not None
        forged_worker = UpdateStageWorker(service, candidate, dialog._update_destination)
        dialog._update_stage_worker = forged_worker
        dialog._update_stage_completed(forged_worker, object())
        assert dialog._staged_update is None
        assert "stopped safely" in dialog.update_status.text()

        monkeypatch.setattr(
            main_window_module.QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        dialog.stage_update_button.click()
        app.processEvents()

        assert dialog._staged_update is not None
        assert dialog.update_progress.value() == 100
        assert dialog.open_staged_update_button.isVisibleTo(dialog)
        assert "Installation has not run" in dialog.update_status.text()
        assert dialog._staged_update.artifact_path.read_bytes() == artifact_bytes

        dialog.update_channel.setCurrentIndex(1)
        assert dialog._update_candidate is None
        assert dialog._staged_update is None
        assert not dialog.stage_update_button.isVisibleTo(dialog)
        assert not dialog.open_staged_update_button.isVisibleTo(dialog)
        assert "Release channel changed" in dialog.update_status.text()
    finally:
        dialog.close()


def test_update_check_rejects_signature_channel_redirect_and_future_time(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, _artifact_bytes, _artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"

    tampered = json.loads(metadata)
    tampered["manifest"]["release_id"] = "romverse-desktop-0.2.0-tampered"
    cases = (
        (json.dumps(tampered).encode(), manifest_url, "digest does not match"),
        (
            _release(tmp_path, private_key, channel="release-candidate")[0],
            manifest_url,
            "selected update channel",
        ),
        (metadata, "https://mirror.example/release.json", "redirected unexpectedly"),
    )
    for payload, final_url, message in cases:
        service = DesktopUpdateService(
            _trust(private_key),
            current_version="0.1.0",
            platform="linux-x86_64",
            opener=Opener({manifest_url: (payload, final_url, len(payload))}),
            now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
        with pytest.raises(DesktopUpdateError, match=message):
            service.check("stable")

    future_metadata = json.loads(metadata)
    future_metadata["manifest"]["published_at"] = "2026-09-04T12:00:00Z"
    future_metadata = create_signed_release_envelope(
        future_metadata["manifest"], private_key, "romverse-release-2026"
    )
    encoded_future = json.dumps(future_metadata).encode()
    future_service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=Opener({manifest_url: (encoded_future, manifest_url, len(encoded_future))}),
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    with pytest.raises(DesktopUpdateError, match="future"):
        future_service.check("stable")


def test_update_staging_rejects_forged_candidate_and_changed_artifact(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, artifact_bytes, artifact_name = _release(tmp_path, private_key)
    manifest_url = "https://updates.romverse.app/stable/release.json"
    artifact_url = f"https://updates.romverse.app/stable/{artifact_name}"
    opener = Opener(
        {
            manifest_url: (metadata, manifest_url, len(metadata)),
            artifact_url: (artifact_bytes + b"changed", artifact_url, None),
        }
    )
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="linux-x86_64",
        opener=opener,
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )
    candidate = service.check("stable")
    forged = deepcopy(candidate)
    object.__setattr__(forged, "manifest_sha256", "0" * 64)

    with pytest.raises(DesktopUpdateError, match="stale or invalid"):
        service.stage(forged, tmp_path / "forged")
    with pytest.raises(DesktopUpdateError, match="exceeds its signed size"):
        service.stage(candidate, tmp_path / "changed")
    assert not tuple((tmp_path / "changed").rglob("*.part"))


def test_current_signed_release_does_not_require_a_platform_artifact(tmp_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    metadata, _artifact_bytes, _artifact_name = _release(
        tmp_path,
        private_key,
        version="0.1.0",
    )
    manifest_url = "https://updates.romverse.app/stable/release.json"
    service = DesktopUpdateService(
        _trust(private_key),
        current_version="0.1.0",
        platform="windows-x86_64",
        opener=Opener({manifest_url: (metadata, manifest_url, len(metadata))}),
        now=lambda: datetime(2026, 9, 3, 12, tzinfo=UTC),
    )

    candidate = service.check("stable")

    assert candidate.available is False
    assert candidate.artifact is None
    assert candidate.artifact_url == ""
