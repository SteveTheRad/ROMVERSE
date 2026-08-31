import json
from importlib.resources import files

from PySide6.QtWidgets import QApplication, QLabel

from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.ui.device_packs_center import DevicePacksCenter


def test_device_atlas_distinguishes_local_build_readiness_from_flash_lock(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                "private-serial",
                DeviceState.DEVICE,
                manufacturer="Xiaomi",
                model="2509FPN0BC",
                product="popsicle_global",
                codename="popsicle",
            )
        ]
    )
    app.processEvents()

    assert center.active_report is not None
    assert center.active_report.build_contract_ready
    assert not center.active_report.flash_contract_ready
    assert "rom build planning is ready" in center.guidance_title.text().casefold()
    assert center.continue_button.isVisibleTo(center)
    exact_model = center.validation_rows["exact-model"]
    assert "Possible fix" in exact_model.toolTip()
    assert "model/product patterns" in exact_model.toolTip()
    assert center.export_button.isEnabled()
    assert center.physical_request_button.isEnabled()
    assert not center.draft_button.isEnabled()
    assert not center.import_attestation_button.isEnabled()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("BUILD READY" in label and "FLASH LOCKED" in label for label in labels)

    center._export_validation_request()

    assert "evidence request only" in center.export_status.text()
    assert list((tmp_path / "device_pack_requests").glob("*.romverse.json"))
    center._export_source_audit()
    assert "execution authority: none" in center.match_reason.text()
    assert list((tmp_path / "device_atlas_audits").glob("*.json"))
    center.close()


def test_device_atlas_renders_exact_pixel_sources_without_build_authority(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)
    center.set_devices(
        [
            AndroidDevice(
                "private-serial",
                DeviceState.DEVICE,
                manufacturer="Google",
                model="Pixel 9 Pro",
                product="caiman",
                codename="caiman",
            )
        ]
    )
    app.processEvents()

    assert center.active_pack is not None
    assert center.active_pack.pack_id == "google.pixel.tensor-gki"
    assert center.active_report is not None
    assert not center.active_report.build_contract_ready
    assert "safe diagnostics are ready" in center.guidance_title.text().casefold()
    assert not center.continue_button.isVisible()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("AOSP Pixel kernel compatibility matrix" in label for label in labels)
    assert "SOURCE CURRENT" in labels
    assert center.draft_button.isEnabled()

    center._export_model_draft()

    drafts = list((tmp_path / "device_pack_drafts").glob("*.draft.json"))
    assert len(drafts) == 1
    payload = drafts[0].read_text(encoding="utf-8")
    document = json.loads(payload)
    assert document["publication_status"] == "draft"
    assert document["match"]["model_patterns"] == ["Pixel 9 Pro"]
    assert "private-serial" not in payload
    assert "execution authority: none" in center.export_status.text()
    center.close()


def test_device_atlas_searches_catalog_and_reviews_pack_evidence_without_phone(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)

    center.catalog_search.setText("knox")
    app.processEvents()
    matches = center._matching_packs("knox")

    assert len(matches) == 1
    assert matches[0].pack_id == "samsung.oneui"
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("1 of" in label and "Pack" in label for label in labels)
    assert "Samsung / One UI" in labels
    assert "INTEGRITY VERIFIED" in labels

    center._show_pack_knowledge(matches[0])
    app.processEvents()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "READ-ONLY KNOWLEDGE  •  EXECUTION AUTHORITY: NONE" in labels
    assert any("Samsung Knox hardware-backed security" in label for label in labels)
    assert "No exact local build contract — diagnostics knowledge only" in labels
    center.close()


def test_device_atlas_search_matches_model_codename_and_capability(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)

    matches = center._matching_packs("caiman kernel")

    assert [pack.pack_id for pack in matches] == ["google.pixel.tensor-gki"]
    center.close()
