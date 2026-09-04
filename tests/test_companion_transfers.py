from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from romverse.companion.transfers import (
    CompanionTransferError,
    CompanionTransferKind,
    CompanionTransferService,
)


def test_transfer_requires_exact_preview_before_private_content_staging(tmp_path: Path) -> None:
    source = tmp_path / "ROMVERSE-Companion.apk"
    source.write_bytes(b"verified companion apk")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = CompanionTransferService(workspace, clock=lambda: 1_800_000_000.0)

    preview = service.inspect(source, CompanionTransferKind.APK)

    assert preview.display_name == "ROMVERSE-Companion.apk"
    assert preview.size_bytes == len(b"verified companion apk")
    assert len(preview.sha256) == 64
    assert not service.root.exists() or not [
        path for path in service.root.rglob("*") if path.is_file()
    ]

    offer = service.stage(preview)
    stored = service.list_active()

    assert stored == (offer,)
    assert offer.to_wire_mapping() == {
        "schema_version": 1,
        "transfer_id": offer.transfer_id,
        "kind": "apk",
        "display_name": "ROMVERSE-Companion.apk",
        "media_type": "application/vnd.android.package-archive",
        "size_bytes": len(b"verified companion apk"),
        "sha256": preview.sha256,
        "created_at_epoch_ms": 1_800_000_000_000,
        "expires_at_epoch_ms": 1_800_086_400_000,
        "requires_phone_confirmation": True,
        "install_authority": "none",
        "execution_authority": "none",
        "download_path": f"/companion/transfers/{offer.transfer_id}/content",
    }
    manifest = (service.offer_root / f"{offer.transfer_id}.json").read_text()
    assert str(source) not in manifest
    assert str(tmp_path) not in manifest
    verified_offer, content = service.verified_content_path(offer.transfer_id)
    assert verified_offer == offer
    assert content.read_bytes() == b"verified companion apk"


@pytest.mark.parametrize(
    ("filename", "kind"),
    [
        ("tester-report.json", CompanionTransferKind.REPORT),
        ("lifeline.recovery.zip", CompanionTransferKind.RECOVERY_CAPSULE),
        ("signed-package.romverse", CompanionTransferKind.APPROVED_PACKAGE),
        ("emergency-guide.txt", CompanionTransferKind.EMERGENCY_GUIDE),
    ],
)
def test_transfer_supports_each_bounded_handoff_kind(
    tmp_path: Path,
    filename: str,
    kind: CompanionTransferKind,
) -> None:
    source = tmp_path / filename
    source.write_bytes(b"bounded handoff")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = CompanionTransferService(workspace)

    offer = service.stage(service.inspect(source, kind))

    assert offer.kind is kind
    assert offer.to_wire_mapping()["execution_authority"] == "none"
    assert offer.to_wire_mapping()["install_authority"] == "none"


def test_transfer_rejects_links_wrong_types_and_post_review_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = CompanionTransferService(workspace)
    report = tmp_path / "report.json"
    report.write_text('{"state":"verified"}')

    with pytest.raises(CompanionTransferError, match="must end"):
        service.inspect(report, CompanionTransferKind.APK)

    linked = tmp_path / "linked.json"
    linked.symlink_to(report)
    with pytest.raises(CompanionTransferError, match="regular file"):
        service.inspect(linked, CompanionTransferKind.REPORT)

    preview = service.inspect(report, CompanionTransferKind.REPORT)
    report.write_text('{"state":"changed-after-review"}')
    with pytest.raises(CompanionTransferError, match="changed after its review"):
        service.stage(preview)
    assert not tuple(service.offer_root.glob("*.json"))


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"display_name": "../report.json"}, "filename is invalid"),
        ({"media_type": "text/html"}, "preview is invalid"),
        ({"size_bytes": True}, "preview is invalid"),
        ({"sha256": "0" * 64}, "changed while it was staged"),
    ],
)
def test_transfer_rejects_forged_preview_metadata(
    tmp_path: Path,
    replacement: dict[str, object],
    message: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "report.json"
    source.write_text('{"result":"verified"}')
    service = CompanionTransferService(workspace)
    preview = service.inspect(source, CompanionTransferKind.REPORT)

    with pytest.raises(CompanionTransferError, match=message):
        service.stage(replace(preview, **replacement))

    assert not service.root.exists() or not [
        path for path in service.root.rglob("*") if path.is_file()
    ]


def test_transfer_rejects_symlinked_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    linked_workspace = tmp_path / "linked-workspace"
    linked_workspace.symlink_to(workspace, target_is_directory=True)

    with pytest.raises(CompanionTransferError, match="boundary is unsafe"):
        CompanionTransferService(linked_workspace)


def test_transfer_offer_limit_fails_before_another_payload_is_staged(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "report.json"
    source.write_text('{"result":"verified"}')
    service = CompanionTransferService(workspace)
    preview = service.inspect(source, CompanionTransferKind.REPORT)
    service.MAX_OFFERS = 2

    service.stage(preview)
    service.stage(preview)
    before = set(service.content_root.iterdir())

    with pytest.raises(CompanionTransferError, match="offer limit is reached"):
        service.stage(preview)

    assert set(service.content_root.iterdir()) == before


def test_expired_offers_are_not_advertised_or_downloadable(tmp_path: Path) -> None:
    now = [1_800_000_000.0]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "recovery.txt"
    source.write_text("Use the verified stock recovery route.")
    service = CompanionTransferService(workspace, clock=lambda: now[0])
    offer = service.stage(
        service.inspect(source, CompanionTransferKind.EMERGENCY_GUIDE),
        ttl_seconds=60,
    )

    now[0] += 61

    assert service.list_active() == ()
    with pytest.raises(CompanionTransferError, match="expired"):
        service.verified_content_path(offer.transfer_id)


def test_manifest_and_content_tampering_fail_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "report.json"
    source.write_text('{"result":"verified"}')
    service = CompanionTransferService(workspace)
    first = service.stage(service.inspect(source, CompanionTransferKind.REPORT))
    manifest_path = service.offer_root / f"{first.transfer_id}.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["transfer"]["execution_authority"] = "flash"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(CompanionTransferError, match="integrity"):
        service.list_active()

    manifest_path.unlink()
    second = service.stage(service.inspect(source, CompanionTransferKind.REPORT))
    content = service.content_root / second.content_file
    content.write_bytes(b"tampered")
    with pytest.raises(CompanionTransferError, match="changed after approval"):
        service.get_active(second.transfer_id)


def test_redigested_manifest_still_rejects_json_type_confusion(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "report.json"
    source.write_text('{"result":"verified"}')
    service = CompanionTransferService(workspace)
    offer = service.stage(service.inspect(source, CompanionTransferKind.REPORT))
    manifest_path = service.offer_root / f"{offer.transfer_id}.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = True
    unsigned = dict(manifest)
    unsigned.pop("record_digest")
    manifest["record_digest"] = service._digest(unsigned)
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(CompanionTransferError, match="manifest is invalid"):
        service.list_active()


def test_reset_revokes_offers_without_deleting_source_or_private_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "report.pdf"
    source.write_bytes(b"report bytes")
    service = CompanionTransferService(workspace)
    offer = service.stage(service.inspect(source, CompanionTransferKind.REPORT))
    content = service.content_root / offer.content_file

    assert service.revoke_all() == 1
    assert service.list_active() == ()
    assert source.read_bytes() == b"report bytes"
    assert content.read_bytes() == b"report bytes"
