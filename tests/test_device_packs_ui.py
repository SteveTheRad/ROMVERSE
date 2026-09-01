import json
from importlib.resources import files

from PySide6.QtWidgets import QApplication, QLabel

from romverse.device.catalog import GooglePlayDeviceCatalog
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import RequirementState
from romverse.ui.device_packs_center import DevicePacksCenter
from tests.test_device_catalog import _payload, _sync


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
    assert center.active_next_action is not None
    assert center.active_next_action.route == "time_machine"
    assert center.next_action_title.text() == "Prepare the exact stock recovery route"
    assert center.next_action_badge.text() == "FLASH GATE • ZERO AUTHORITY"
    assert center.active_requirements is not None
    assert center.active_requirements.lane("build").state is RequirementState.VERIFIED
    assert center.active_requirements.lane("compile").state is RequirementState.DECLARED
    assert center.active_requirements.lane("flash").state is RequirementState.NEEDS_EVIDENCE
    assert center.requirement_badges["build"].text() == "EXACT BUILD CONTRACT • READY"
    assert "14 TOOLS DECLARED" in center.requirement_badges["compile"].text()
    requirements_requested: list[tuple[str, str, str, str]] = []
    center.requirement_requested.connect(lambda *values: requirements_requested.append(values))
    center.requirement_buttons["compile"].click()
    assert requirements_requested == [
        (
            "compile",
            "forge_arsenal",
            "",
            center.active_report.report_digest,
        )
    ]
    requested: list[tuple[str, str, str, str]] = []
    center.next_action_requested.connect(lambda *values: requested.append(values))
    center.next_action_button.click()
    assert requested == [
        (
            "time_machine",
            "",
            "stock-recovery-route",
            center.active_report.report_digest,
        )
    ]
    assert "rom build planning is ready" in center.guidance_title.text().casefold()
    assert center.continue_button.isVisibleTo(center)
    studio_requests: list[tuple[str, str]] = []
    center.rom_studio_requested.connect(
        lambda report_id, digest: studio_requests.append((report_id, digest))
    )
    center.continue_button.click()
    assert studio_requests == [
        (center.active_report.report_id, center.active_report.report_digest)
    ]
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


def test_device_atlas_search_connects_official_identity_to_exact_local_pack_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(("Xiaomi", "Xiaomi 17 Pro Max", "popsicle", "2509FPN0BC")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path, device_catalog=catalog)

    center.catalog_search.setText("2509FPN0BC")
    app.processEvents()

    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "Official Android identities  •  1 verified result(s) shown" in labels
    assert "Xiaomi 17 Pro Max" in labels
    assert "OFFICIAL ID • BUILD LOCKED" in labels
    assert len(center.official_result_buttons) == 1
    assert center.active_device is None
    assert center.active_report is None

    center.official_result_buttons[0].click()
    app.processEvents()

    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "GOOGLE PLAY DEVICE ID  •  VERIFIED LOCAL MIRROR" in labels
    assert "RETAIL IDENTITY ONLY  •  BUILD / FLASH / EXECUTION AUTHORITY: NONE" in labels
    assert "Exact local Pack evidence  •  1 candidate(s)" in labels
    assert "Xiaomi 17 Pro Max / HyperOS 4.0.0.23" in labels
    assert center.active_device is None
    assert center.active_report is None
    center.close()


def test_device_atlas_refuses_a_search_result_after_catalog_evidence_changes(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(catalog, _payload(("Example", "Example Nebula", "nebula", "EX-100")))
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path, device_catalog=catalog)
    center.catalog_search.setText("Example Nebula")
    app.processEvents()
    review = center.official_result_buttons[0]

    catalog.catalog_path.write_bytes(catalog.catalog_path.read_bytes() + b"changed")
    review.click()
    app.processEvents()

    assert center.identity_catalog_title.text() == "Official identity review stopped safely"
    assert center.identity_catalog_badge.text() == "STALE RESULT • ZERO AUTHORITY"
    assert "No Device Pack, project, build, flash, approval, or phone state changed" in (
        center.identity_catalog_detail.text()
    )
    assert center.active_device is None
    assert center.active_report is None
    center.close()


def test_device_atlas_shows_exact_official_identity_without_inventing_build_support(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(
        catalog,
        _payload(("Example", "Example Nebula", "nebula", "EX-100")),
    )
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path, device_catalog=catalog)
    requested = []
    center.catalog_refresh_requested.connect(lambda: requested.append(True))

    center.set_devices(
        [
            AndroidDevice(
                "private-serial",
                DeviceState.DEVICE,
                brand="Example",
                manufacturer="Example Industries",
                model="EX-100",
                codename="nebula",
            )
        ]
    )
    app.processEvents()

    assert center.identity_catalog_title.text() == ("Official identity recognized • Example Nebula")
    assert center.identity_catalog_badge.text() == "EXACT ID • READ ONLY"
    assert "Build.BRAND / Build.DEVICE: Example / nebula" in (center.identity_catalog_detail.text())
    assert "exact build support is still locked" in center.guidance_title.text().casefold()
    assert center.active_pack is not None and center.active_pack.pack_id == "android.generic"
    assert not center.continue_button.isVisible()
    assert center.active_next_action is not None
    assert center.active_next_action.article_key == "android-device-identity-catalog"
    assert center.next_action_badge.text() == "BUILD GATE • ZERO AUTHORITY"
    assert center.active_requirements is not None
    identity = center.active_requirements.lane("identity")
    compile_lane = center.active_requirements.lane("compile")
    assert identity is not None and identity.state is RequirementState.VERIFIED
    assert compile_lane is not None and compile_lane.state is RequirementState.LOCKED
    assert center.requirement_badges["identity"].text() == "OFFICIAL ID • READ ONLY"
    assert center.requirement_badges["compile"].text() == ("TOOLCHAIN UNKNOWN • NO GENERIC GUESS")
    requested_requirements = []
    center.requirement_requested.connect(lambda *values: requested_requirements.append(values))
    center.requirement_buttons["compile"].click()
    assert requested_requirements == [
        (
            "compile",
            "archives",
            "device-build-requirements-blueprint",
            center.active_report.report_digest,
        )
    ]

    center.identity_catalog_button.click()
    app.processEvents()
    assert requested == [True]
    center.close()


def test_official_id_refresh_recomputes_the_current_requirements_without_phone_action(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path, device_catalog=catalog)
    center.set_devices(
        [
            AndroidDevice(
                "private-refresh",
                DeviceState.DEVICE,
                brand="Example",
                manufacturer="Example Industries",
                model="EX-100",
                codename="nebula",
            )
        ]
    )
    initial_report = center.active_report
    assert initial_report is not None and center.active_requirements is not None
    assert center.active_requirements.lane("identity").state is RequirementState.NEEDS_EVIDENCE

    _sync(catalog, _payload(("Example", "Example Nebula", "nebula", "EX-100")))
    center.set_catalog_status(catalog.status())
    app.processEvents()

    assert center.active_report is initial_report
    assert center.active_requirements is not None
    assert center.active_requirements.lane("identity").state is RequirementState.VERIFIED
    assert center.requirement_badges["identity"].text() == "OFFICIAL ID • READ ONLY"
    assert center.active_requirements.lane("compile").state is RequirementState.LOCKED
    center.close()
