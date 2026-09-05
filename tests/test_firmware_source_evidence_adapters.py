from __future__ import annotations

from dataclasses import dataclass
from inspect import signature

import pytest

from romverse.rom.models import ProjectError
from romverse.rom.source_evidence_adapters import (
    BoundedFirmwareSourceEvidenceAdapter,
    FirmwareAdapter,
    FirmwareSourceAnalysis,
    FirmwareSourceEvidenceAdapter,
    FirmwareSourceEvidenceAdapterRegistry,
    FirmwareSourceSnapshot,
)
from romverse.rom.source_intelligence import FirmwareSourceIntelligenceService
from tests.test_source_intelligence import SourceRunner, _project


@dataclass(frozen=True, slots=True)
class _Evidence:
    project_id: str
    source_kind: str
    authority: str
    phone_changed: bool = False
    baseline_candidate_ready: bool = True


def _no_match(_snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis | None:
    return None


def _not_prepared(
    _project_id: str,
    _analysis: FirmwareSourceAnalysis,
    _progress,
) -> object:
    raise AssertionError("prepare must not be reached")


def _nothing_loaded(_project_id: str) -> object | None:
    return None


def _adapter(
    identity: FirmwareAdapter,
    *,
    matcher=_no_match,
    loader=_nothing_loaded,
) -> BoundedFirmwareSourceEvidenceAdapter:
    authority = (
        "project-local-inventory-evidence-only"
        if identity is FirmwareAdapter.PARTITION_BUNDLE
        else "project-local-build-evidence-only"
    )
    return BoundedFirmwareSourceEvidenceAdapter(
        identity,
        authority,
        matcher,
        _not_prepared,
        loader,
    )


def _registry(
    adapters: tuple[BoundedFirmwareSourceEvidenceAdapter, ...] | None = None,
) -> FirmwareSourceEvidenceAdapterRegistry:
    return FirmwareSourceEvidenceAdapterRegistry(
        adapters
        or (
            _adapter(FirmwareAdapter.OTA_PAYLOAD),
            _adapter(FirmwareAdapter.FASTBOOT_SUPER),
            _adapter(FirmwareAdapter.PARTITION_BUNDLE),
        )
    )


def _claim(identity: FirmwareAdapter):
    def match(snapshot: FirmwareSourceSnapshot) -> FirmwareSourceAnalysis:
        return FirmwareSourceAnalysis(identity, "", "", snapshot.partition_images, "test claim")

    return match


def _load(evidence: _Evidence):
    def load(_project_id: str) -> object:
        return evidence

    return load


def test_registry_is_closed_deterministic_and_exposes_no_authority_or_execution_surface():
    registry = _registry()

    assert registry.adapter_ids == (
        FirmwareAdapter.FASTBOOT_SUPER,
        FirmwareAdapter.OTA_PAYLOAD,
        FirmwareAdapter.PARTITION_BUNDLE,
    )
    assert set(signature(FirmwareSourceIntelligenceService).parameters) == {
        "store",
        "tool_statuses",
        "runner",
    }
    forbidden = {
        "authorize",
        "build",
        "command",
        "device",
        "dispatch",
        "execute",
        "flash",
        "install",
        "relock",
        "retry",
    }
    assert forbidden.isdisjoint(dir(FirmwareSourceEvidenceAdapter))
    assert forbidden.isdisjoint(dir(FirmwareSourceEvidenceAdapterRegistry))


def test_registry_rejects_duplicate_missing_and_unknown_adapter_identities():
    duplicate = (
        _adapter(FirmwareAdapter.OTA_PAYLOAD),
        _adapter(FirmwareAdapter.OTA_PAYLOAD),
        _adapter(FirmwareAdapter.PARTITION_BUNDLE),
    )
    with pytest.raises(ProjectError, match="duplicate adapter identity"):
        _registry(duplicate)

    missing = (
        _adapter(FirmwareAdapter.OTA_PAYLOAD),
        _adapter(FirmwareAdapter.FASTBOOT_SUPER),
    )
    with pytest.raises(ProjectError, match="exactly the frozen adapters"):
        FirmwareSourceEvidenceAdapterRegistry(missing)

    hostile = object.__new__(BoundedFirmwareSourceEvidenceAdapter)
    object.__setattr__(hostile, "adapter_id", "vendor-plugin")
    object.__setattr__(hostile, "evidence_authority", "none")
    object.__setattr__(hostile, "_matcher", _no_match)
    object.__setattr__(hostile, "_preparer", _not_prepared)
    object.__setattr__(hostile, "_loader", _nothing_loaded)
    with pytest.raises(ProjectError, match="unknown adapter identity"):
        FirmwareSourceEvidenceAdapterRegistry(
            (
                hostile,
                _adapter(FirmwareAdapter.FASTBOOT_SUPER),
                _adapter(FirmwareAdapter.PARTITION_BUNDLE),
            )
        )


def test_registry_rejects_multiple_matches_identically_regardless_of_registration_order():
    snapshot = FirmwareSourceSnapshot((), (), ("working/p/boot.img",))
    adapters = (
        _adapter(FirmwareAdapter.OTA_PAYLOAD, matcher=_claim(FirmwareAdapter.OTA_PAYLOAD)),
        _adapter(
            FirmwareAdapter.FASTBOOT_SUPER,
            matcher=_claim(FirmwareAdapter.FASTBOOT_SUPER),
        ),
        _adapter(FirmwareAdapter.PARTITION_BUNDLE),
    )

    messages = []
    for ordered in (adapters, tuple(reversed(adapters))):
        with pytest.raises(ProjectError, match="matches multiple evidence adapters") as error:
            _registry(ordered).analyze(snapshot)
        messages.append(str(error.value))

    assert messages[0] == messages[1]
    assert "fastboot-super, ota-payload" in messages[0]


def test_real_source_with_payload_and_super_fails_closed_as_cross_adapter_ambiguity(tmp_path):
    store, project, tree = _project(tmp_path, "Mixed source", "popsicle-mixed.zip")
    (tree / "payload.bin").write_bytes(b"CrAU-payload")
    (tree / "super.img").write_bytes(b"super")
    service = FirmwareSourceIntelligenceService(store, (), SourceRunner())

    with pytest.raises(ProjectError, match="fastboot-super, ota-payload.*ambiguous"):
        service.analyze(project.project_id)


def test_registry_rejects_multiple_valid_durable_blueprints_instead_of_using_priority():
    project_id = "project-1"
    adapters = (
        _adapter(
            FirmwareAdapter.OTA_PAYLOAD,
            loader=_load(
                _Evidence(
                    project_id,
                    FirmwareAdapter.OTA_PAYLOAD.value,
                    "project-local-build-evidence-only",
                )
            ),
        ),
        _adapter(
            FirmwareAdapter.FASTBOOT_SUPER,
            loader=_load(
                _Evidence(
                    project_id,
                    FirmwareAdapter.FASTBOOT_SUPER.value,
                    "project-local-build-evidence-only",
                )
            ),
        ),
        _adapter(FirmwareAdapter.PARTITION_BUNDLE),
    )

    with pytest.raises(ProjectError, match="Multiple valid firmware evidence blueprints"):
        _registry(adapters).load(project_id)


@pytest.mark.parametrize(
    ("evidence", "reason"),
    (
        (
            _Evidence("wrong-project", "fastboot-super", "project-local-build-evidence-only"),
            "project binding",
        ),
        (
            _Evidence("project-1", "ota-payload", "project-local-build-evidence-only"),
            "adapter binding",
        ),
        (
            _Evidence("project-1", "fastboot-super", "guardian-execution-authority"),
            "authority",
        ),
        (
            _Evidence(
                "project-1",
                "fastboot-super",
                "project-local-build-evidence-only",
                phone_changed=True,
            ),
            "device mutation",
        ),
        (
            _Evidence(
                "project-1",
                "fastboot-super",
                "project-local-build-evidence-only",
                baseline_candidate_ready=False,
            ),
            "unready evidence",
        ),
    ),
)
def test_registry_rejects_invalid_or_authority_bearing_adapter_evidence(evidence, reason):
    adapters = (
        _adapter(FirmwareAdapter.OTA_PAYLOAD),
        _adapter(FirmwareAdapter.FASTBOOT_SUPER, loader=_load(evidence)),
        _adapter(FirmwareAdapter.PARTITION_BUNDLE),
    )

    with pytest.raises(ProjectError, match="invalid or authority-bearing evidence"):
        _registry(adapters).load("project-1")
    assert reason


def test_source_snapshot_rejects_nondeterministic_or_escaping_evidence_paths():
    with pytest.raises(ProjectError, match="unique and deterministic"):
        FirmwareSourceSnapshot(
            ("working/p/b/payload.bin", "working/p/a/payload.bin"),
            (),
            (),
        )
    with pytest.raises(ProjectError, match="escaped the workspace"):
        FirmwareSourceSnapshot(("../payload.bin",), (), ())
    with pytest.raises(ProjectError, match="unexpected file name"):
        FirmwareSourceSnapshot(("working/p/not-payload.bin",), (), ())
