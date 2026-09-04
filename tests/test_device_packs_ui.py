import json
import zipfile
from importlib.resources import files

from PySide6.QtWidgets import QApplication, QFrame, QLabel

from romverse.device.catalog import GooglePlayDeviceCatalog
from romverse.device.dna import DeviceDnaService
from romverse.device.models import AndroidDevice, DeviceState
from romverse.device_packs.drafts import DevicePackDraftService
from romverse.device_packs.registry import DevicePackRegistry
from romverse.device_packs.requirements import RequirementState
from romverse.infrastructure.tools import ToolStatus
from romverse.rom.projects import RomProjectStore
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from romverse.ui.device_packs_center import DevicePacksCenter
from tests.test_device_catalog import _payload, _sync
from tests.test_device_dna import _device as _dna_device
from tests.test_device_dna import _project as _dna_project
from tests.test_source_intelligence import SourceRunner


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
                android_version="17",
                build_id="OS4.0.0.25.XPBCNXM",
                battery_percent=76,
                bootloader_locked=False,
                slot_suffix="_a",
                virtual_ab=True,
                dynamic_partitions=True,
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
    assert center.passport_name.text() == "Xiaomi 2509FPN0BC"
    assert center.passport_state.text() == "CONNECTED • PASSPORT CURRENT"
    assert center.passport_platform.text().endswith("China")
    assert "Android 17" in center.passport_firmware.text()
    assert "Unlocked" in center.passport_boot.text()
    assert center.passport_history.text().startswith("1 scans • 0 flashes • 0 repairs")
    passport_bytes = center.intelligence_history.path.read_text(encoding="utf-8")
    assert "private-serial" not in passport_bytes
    center._open_private_timeline()
    app.processEvents()
    assert center._timeline_dialog is not None
    assert any(
        "Device DNA scan" in label.text() for label in center._timeline_dialog.findChildren(QLabel)
    )
    center._timeline_dialog.close()
    studio_requests: list[tuple[str, str]] = []
    center.rom_studio_requested.connect(
        lambda report_id, digest: studio_requests.append((report_id, digest))
    )
    center.continue_button.click()
    assert studio_requests == [(center.active_report.report_id, center.active_report.report_digest)]
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


def test_device_passport_unfolds_exact_source_bound_dna_and_remains_scrollable(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    store, registry, project, inspection = _dna_project(tmp_path)
    device = _dna_device()
    profile = DeviceDnaService(store, registry).refresh(
        project.project_id,
        device,
        inspection,
    )
    center = DevicePacksCenter(registry, store.workspace)
    center.resize(1280, 720)
    center.set_devices([device])
    center.set_device_dna(profile)
    center.show()
    app.processEvents()

    assert center.passport_upgrade.text() == (
        "SAME FIRMWARE VERSION • OS4.0.0.23.XPBCNXM → OS4.0.0.23.XPBCNXM"
    )
    assert "1 mapped" in center.passport_partitions.text()
    assert center.body.horizontalScrollBar().maximum() == 0
    assert center.body.verticalScrollBar().maximum() > 0
    fact_cards = [
        card for card in center.findChildren(QFrame) if card.objectName() == "DevicePassportFact"
    ]
    assert len(fact_cards) == 9
    for index, first in enumerate(fact_cards):
        first_rect = first.geometry()
        for second in fact_cards[index + 1 :]:
            if first.parentWidget() is second.parentWidget():
                assert not first_rect.intersects(second.geometry())
    center.close()


def test_studio_handoff_scopes_requirements_to_current_strict_source_blueprint(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Current HyperOS source", "xiaomi.hyperos")
    source = tmp_path / "popsicle-ota_full-OS4.0.0.25.XPBCNXM-user-17.0-test.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("source-marker.txt", b"protected-current-source")
    project = store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"CrAU current payload")
    payload_dumper = tmp_path / "payload-dumper-go"
    payload_dumper.write_bytes(b"verified tool fixture")
    statuses = (
        ToolStatus("Python", True, "/verified/python", "test", "Ready"),
        ToolStatus("Payload Dumper", True, str(payload_dumper), "test", "Ready"),
        ToolStatus("AVBTool", True, "/verified/avbtool", "test", "Ready"),
    )
    source_blueprint = FirmwareSourceIntelligenceService(
        store,
        statuses,
        SourceRunner(),
    ).prepare(project.project_id)
    center = DevicePacksCenter(registry, store.workspace, tool_statuses=statuses)
    device = AndroidDevice(
        "private-current-source",
        DeviceState.DEVICE,
        brand="Xiaomi",
        manufacturer="Xiaomi",
        model="2509FPN0BC",
        product="popsicle_global",
        codename="popsicle",
    )
    center.set_devices([device])

    assert center.open_rom_studio_project(
        project.project_id,
        project.name,
        project.device_pack_id,
        project.original.sha256,
    )
    app.processEvents()

    blueprint = center.current_requirements()
    assert blueprint is not None and blueprint.project_scoped
    assert blueprint.project_id == project.project_id
    assert blueprint.project_source_sha256 == project.original.sha256
    assert blueprint.source_blueprint_digest == source_blueprint.blueprint_digest
    assert blueprint.source_required_tools == ("Python", "Payload Dumper", "AVBTool")
    assert blueprint.lane("build").badge == "PROJECT SOURCE • LOCAL BASELINE READY"
    assert blueprint.lane("compile").badge == "3/3 TOOLS VERIFIED • HOST READY"
    assert blueprint.lane("flash").state is RequirementState.LOCKED
    assert center.dashboard_handoff_badge.text() == "PROJECT SOURCE BOUND"
    assert "OS4.0.0.25" in center.dashboard_handoff_detail.text()
    assert "3 HOST TOOLS" in center.dashboard_handoff_detail.text()
    assert "project source recognized" in center.guidance_title.text().casefold()
    assert not center.continue_button.isHidden()
    assert center.continue_button.isEnabled()
    assert center.pack_name.text().startswith("Phone Pack reference")
    assert "is for a different source" in center.match_reason.text()
    assert center.pack_badge.text() == "REFERENCE ONLY • PROJECT SOURCE ACTIVE"
    assert center.active_next_action is None
    assert center.next_action_title.text() == "Prepare the exact-source Device Pack draft"
    assert center.next_action_badge.text() == "BUILD READY • PACK DRAFT NEXT"
    assert center.next_action_button.isEnabled()
    assert center.next_action_button.text() == "Prepare exact-source Pack draft"
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("Current HyperOS source" in label and "ota-payload" in label for label in labels)

    profile = DeviceDnaService(store, registry).refresh(project.project_id, device)
    center.set_device_dna(profile)
    app.processEvents()
    assert center.next_action_title.text() == "Attach the current sealed Device DNA revision"
    assert center.next_action_badge.text() == "DNA EVIDENCE READY • NEW REVISION"
    assert center.next_action_button.text() == "Attach sealed Device DNA revision"

    center.next_action_button.click()
    assert "EXACT-SOURCE PACK DRAFT READY" in center.next_action_feedback.text()
    assert "sealed privacy-safe Device DNA attached" in center.next_action_feedback.text()
    assert center.active_project_draft is not None
    assert center.active_project_draft.device_dna_attached
    assert center.active_project_draft.device_dna_profile_digest == profile.profile_digest
    assert center.active_foundry_revision is not None
    assert center.active_foundry_revision.device_dna_attached
    assert center.active_foundry_revision.evidenced_lane_count == 3
    assert center.next_action_title.text() == "Exact-source Pack draft prepared"
    assert center.next_action_badge.text() == "DRAFT VERIFIED • FLASH EVIDENCE NEXT"
    assert center.next_action_button.text() == "Review draft and missing evidence"
    drafts = list((store.workspace / "device_pack_drafts").glob("*.draft.json"))
    assert len(drafts) == 1
    draft = json.loads(drafts[0].read_text(encoding="utf-8"))
    assert draft["draft_context"]["source_sha256"] == project.original.sha256
    assert draft["draft_context"]["partition_count"] == len(source_blueprint.partitions)
    assert draft["draft_context"]["phone_action_allowed"] is False
    assert draft["draft_context"]["device_dna_evidence"]["profile_digest"] == profile.profile_digest
    assert draft["draft_context"]["device_dna_evidence"]["region_is_matcher"] is False
    assert "private-current-source" not in json.dumps(draft)

    assert center.open_rom_studio_project(
        project.project_id,
        project.name,
        project.device_pack_id,
        project.original.sha256,
    )
    assert center.active_project_draft is not None
    assert center.next_action_button.text() == "Review draft and missing evidence"
    assert len(list((store.workspace / "device_pack_drafts").glob("*.draft.json"))) == 1

    requests: list[tuple[str, str, str, str]] = []
    center.requirement_requested.connect(lambda *values: requests.append(values))
    center.requirement_buttons["compile"].click()
    assert requests == [("compile", "forge_arsenal_project", "", blueprint.report_digest)]

    (tree / "payload.bin").write_bytes(b"changed payload")
    center.requirement_buttons["build"].click()
    assert requests == [("compile", "forge_arsenal_project", "", blueprint.report_digest)]
    assert "BUILD HANDOFF STOPPED" in center.requirements_feedback.text()
    assert "source blueprint changed" in center.requirements_feedback.text()
    center.close()


def test_generic_ota_internal_identity_reaches_matching_device_atlas_project(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    store = RomProjectStore(tmp_path / "workspace")
    project = store.create("Pixel OTA source", "google.pixel.tensor-gki")
    source = tmp_path / "official-generic-update.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("payload.bin", b"CrAU protected payload")
        archive.writestr(
            "META-INF/com/android/metadata",
            "pre-device=komodo\n"
            "post-build=google/komodo/komodo:16/BP2A.260901.001/456:user/release-keys\n"
            "post-build-incremental=456\n"
            "post-sdk-level=36\n"
            "post-security-patch-level=2026-09-01\n"
            "post-timestamp=1788220800\n",
        )
    project = store.import_original(project.project_id, source)
    tree = store.working_root / project.project_id / "tree"
    tree.mkdir(parents=True)
    (tree / "payload.bin").write_bytes(b"CrAU protected payload")
    payload_dumper = tmp_path / "payload-dumper-go"
    payload_dumper.write_bytes(b"verified tool fixture")
    statuses = (
        ToolStatus("Python", True, "/verified/python", "test", "Ready"),
        ToolStatus("Payload Dumper", True, str(payload_dumper), "test", "Ready"),
        ToolStatus("AVBTool", True, "/verified/avbtool", "test", "Ready"),
    )
    source_blueprint = FirmwareSourceIntelligenceService(
        store,
        statuses,
        SourceRunner(),
    ).prepare(project.project_id)
    center = DevicePacksCenter(registry, store.workspace, tool_statuses=statuses)
    center.set_devices(
        [
            AndroidDevice(
                "private-pixel",
                DeviceState.DEVICE,
                brand="Google",
                manufacturer="Google",
                model="Pixel 9 Pro XL",
                product="komodo",
                codename="komodo",
                build_id="BP1A.260801.001",
            )
        ]
    )

    assert center.open_rom_studio_project(
        project.project_id,
        project.name,
        project.device_pack_id,
        project.original.sha256,
    )
    app.processEvents()

    requirements = center.current_requirements()
    assert source_blueprint.manufacturer == "google"
    assert source_blueprint.codename == "komodo"
    assert source_blueprint.build_id == "BP2A.260901.001"
    assert requirements is not None and requirements.project_scoped
    assert requirements.pack_id == "google.pixel.tensor-gki"
    assert requirements.source_build_id == "BP2A.260901.001"
    assert requirements.source_blueprint_digest == source_blueprint.blueprint_digest
    assert requirements.lane("build").badge == "PROJECT SOURCE • LOCAL BASELINE READY"
    assert requirements.lane("compile").state is RequirementState.VERIFIED
    assert requirements.lane("flash").state is RequirementState.LOCKED
    assert center.dashboard_handoff_badge.text() == "PROJECT SOURCE BOUND"
    assert "BP2A.260901.001" in center.dashboard_handoff_detail.text()
    assert center.next_action_button.text() == "Prepare exact-source Pack draft"
    center.close()


def test_device_atlas_resolves_literal_fastboot_product_without_inventing_oem(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)

    center.set_devices(
        [
            AndroidDevice(
                "private-fastboot",
                DeviceState.BOOTLOADER,
                transport="usb-fastboot",
                model="popsicle",
                product="popsicle",
                codename="popsicle",
                fastboot_capability="Observed bootloader fastboot transport",
            )
        ]
    )
    app.processEvents()

    assert center.active_pack is not None
    assert center.active_pack.pack_id == "xiaomi.popsicle.hyperos4.os4.0.0.23"
    assert center.active_report is not None and center.active_report.build_contract_ready
    assert center.active_requirements is not None
    assert center.active_requirements.lane("identity").state is RequirementState.DECLARED
    assert center.active_requirements.lane("build").state is RequirementState.VERIFIED
    assert not center.active_report.flash_contract_ready
    center.close()


def test_device_atlas_compile_lane_tracks_forge_arsenal_without_starting_work(tmp_path) -> None:
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
    assert center.active_pack is not None and center.active_pack.build_contract is not None
    report = center.active_report
    required = center.active_pack.build_contract.required_tools
    requested: list[tuple[str, str, str, str]] = []
    center.requirement_requested.connect(lambda *values: requested.append(values))

    center.set_tool_statuses(
        tuple(
            ToolStatus(name, True, f"/verified/{index}", "test", "Ready")
            for index, name in enumerate(required)
        )
    )
    app.processEvents()
    assert center.active_report is report
    assert center.active_requirements is not None
    assert center.active_requirements.lane("compile").state is RequirementState.VERIFIED
    assert center.requirement_badges["compile"].text() == "14/14 TOOLS VERIFIED • HOST READY"
    assert center.requirement_buttons["compile"].text() == "Review verified toolchain"
    assert requested == []

    center.set_tool_statuses(
        tuple(
            ToolStatus(name, name != required[-1], f"/verified/{index}", "test", "Ready")
            for index, name in enumerate(required)
        )
    )
    app.processEvents()
    compile_lane = center.active_requirements.lane("compile")
    assert compile_lane is not None and compile_lane.state is RequirementState.NEEDS_EVIDENCE
    assert center.requirement_badges["compile"].text() == "13/14 TOOLS VERIFIED • 1 MISSING"
    assert compile_lane.requirements == (required[-1],)
    assert center.requirement_buttons["compile"].text() == "Resolve missing build tools"
    assert requested == []
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
    assert not center.continue_button.isHidden()
    assert center.continue_button.isEnabled()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("AOSP Pixel kernel compatibility matrix" in label for label in labels)
    assert "SOURCE CURRENT" in labels
    assert center.draft_button.isEnabled()
    assert center.active_foundry_revision is None
    assert any("DEVICE PACK FOUNDRY" in label for label in labels)

    center._export_model_draft()

    drafts = list((tmp_path / "device_pack_drafts").glob("*.draft.json"))
    assert len(drafts) == 1
    payload = drafts[0].read_text(encoding="utf-8")
    document = json.loads(payload)
    assert document["publication_status"] == "draft"
    assert document["match"]["model_patterns"] == ["Pixel 9 Pro"]
    assert "private-serial" not in payload
    assert "execution authority: none" in center.export_status.text()
    assert center.active_foundry_revision is not None
    assert not center.active_foundry_revision.source_bound
    assert center.draft_button.text() == "Model Pack draft recorded"
    assert not center.draft_button.isEnabled()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("1/6 LANES" in label and "EXPERIMENTAL" in label for label in labels)
    assert any("DRAFTS STAY OUTSIDE THE PRODUCTION REGISTRY" in label for label in labels)
    center.close()


def test_device_atlas_searches_catalog_and_reviews_pack_evidence_without_phone(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)

    center.catalog_search.setText("knox")
    app.processEvents()
    matches = center._matching_packs("knox")

    assert {pack.pack_id for pack in matches} == {
        "samsung.galaxy-s24-ultra.sm-s928b",
        "samsung.oneui",
    }
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert any("2 of" in label and "Pack" in label for label in labels)
    assert "Samsung / One UI" in labels
    assert "INTEGRITY VERIFIED" in labels

    family_pack = next(pack for pack in matches if pack.pack_id == "samsung.oneui")
    center._show_pack_knowledge(family_pack)
    app.processEvents()
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "READ-ONLY KNOWLEDGE  •  EXECUTION AUTHORITY: NONE" in labels
    assert any("Samsung Knox hardware-backed security" in label for label in labels)
    assert "No exact local build contract — diagnostics knowledge only" in labels
    center.close()


def test_device_pack_foundry_surfaces_conflicting_experimental_identity_claims(
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    device = AndroidDevice(
        "private-serial",
        DeviceState.DEVICE,
        manufacturer="Google",
        brand="Google",
        model="Pixel 9 Pro",
        product="caiman",
        codename="caiman",
    )
    seed = registry.resolve(device).pack
    assert seed is not None
    service = DevicePackDraftService()
    first = service.request_from_device(seed, device)
    second = json.loads(json.dumps(first))
    first["pack_id"] = "candidate.pixel.first"
    second["pack_id"] = "candidate.pixel.second"
    drafts = tmp_path / "device_pack_drafts"
    service.export(first, drafts, boundary=tmp_path)
    service.export(second, drafts, boundary=tmp_path)

    center = DevicePacksCenter(registry, tmp_path)
    center.set_devices([device])
    app.processEvents()
    try:
        assert center.foundry_inventory is not None
        assert len(center.foundry_inventory.conflicts) == 2
        labels = [label.text() for label in center.findChildren(QLabel)]
        assert any("2 identity conflict(s)" in label for label in labels)
        assert any(
            "candidate.pixel.first" in label and "candidate.pixel.second" in label
            for label in labels
        )
        assert any("PUBLICATION AUTHORITY: NONE" in label for label in labels)
    finally:
        center.close()


def test_device_atlas_exposes_exact_observed_s24_ultra_read_only_evidence(tmp_path) -> None:
    _app = QApplication.instance() or QApplication([])
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path)

    matches = center._matching_packs("SM-S928B e3q")

    assert [pack.pack_id for pack in matches] == ["samsung.galaxy-s24-ultra.sm-s928b"]
    center._show_pack_knowledge(matches[0])
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "READ-ONLY KNOWLEDGE  •  EXECUTION AUTHORITY: NONE" in labels
    assert any("physically observed" in label.casefold() for label in labels)
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


def test_official_identity_without_pack_requests_its_exact_archives_guide(
    tmp_path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GooglePlayDeviceCatalog, "MINIMUM_ENTRIES", 1)
    catalog = GooglePlayDeviceCatalog(tmp_path)
    _sync(catalog, _payload(("Example", "Example Nebula", "nebula", "EX-100")))
    registry = DevicePackRegistry.load(files("romverse.assets").joinpath("device_packs"))
    center = DevicePacksCenter(registry, tmp_path, device_catalog=catalog)
    requested: list[str] = []
    center.knowledge_article_requested.connect(requested.append)

    center.catalog_search.setText("Example Nebula")
    app.processEvents()
    center.official_result_buttons[0].click()
    app.processEvents()

    assert center.official_missing_pack_guide_button is not None
    labels = [label.text() for label in center.findChildren(QLabel)]
    assert "No exact Device Pack is declared for this official identity" in labels
    center.official_missing_pack_guide_button.click()

    assert requested == ["official-device-id-without-pack"]
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
    assert not center.continue_button.isHidden()
    assert center.continue_button.isEnabled()
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
