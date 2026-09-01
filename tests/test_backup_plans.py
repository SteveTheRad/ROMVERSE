import hashlib
import json

from romverse.backup.plans import GuardianBackupPlanStore
from romverse.device.models import AndroidDevice, DeviceState, StorageInfo


def _device() -> AndroidDevice:
    return AndroidDevice(
        serial="private-device-serial",
        state=DeviceState.DEVICE,
        manufacturer="Xiaomi",
        model="Test Phone",
        build_id="BUILD.1",
        battery_percent=88,
        storage=StorageInfo(percent_used=41),
        bootloader_locked=True,
        verified_boot="green",
    )


def test_recovery_readiness_plan_is_atomic_private_and_integrity_verified(tmp_path) -> None:
    store = GuardianBackupPlanStore(tmp_path)

    record = store.create(_device())
    loaded = store.load_latest()
    rendered = record.latest_path.read_text(encoding="utf-8")

    assert loaded.valid
    assert loaded.integrity_verified
    assert loaded.data is not None
    assert loaded.data["phone_data_copied"] is False
    assert loaded.data["execution_authority"] == "none"
    assert loaded.data["scope"] == ["recovery readiness evidence only"]
    assert loaded.data["readiness"]["verified_boot"] == "green"
    assert "private-device-serial" not in rendered
    assert record.history_path.is_file()
    assert store.history_count() == 1
    assert not list(store.root.glob("*.tmp"))


def test_tampered_recovery_readiness_plan_is_rejected(tmp_path) -> None:
    store = GuardianBackupPlanStore(tmp_path)
    store.create(_device())
    data = json.loads(store.latest_path.read_text(encoding="utf-8"))
    data["execution_locked"] = False
    store.latest_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = store.load_latest()

    assert not loaded.valid
    assert not loaded.integrity_verified
    assert "integrity mismatch" in loaded.reason


def test_legacy_plan_remains_reviewable_but_is_not_called_integrity_verified(tmp_path) -> None:
    store = GuardianBackupPlanStore(tmp_path)
    store.root.mkdir(parents=True)
    store.latest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "review_required",
                "readiness": {"verified_boot": "green"},
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load_latest()

    assert loaded.valid
    assert not loaded.integrity_verified
    assert "Legacy" in loaded.reason


def test_redigested_recovery_plan_schema_and_type_mutations_fail_closed(tmp_path) -> None:
    store = GuardianBackupPlanStore(tmp_path)
    store.create(_device())
    original = json.loads(store.latest_path.read_text(encoding="utf-8"))

    mutations = (
        lambda data: data.update({"unexpected": "field"}),
        lambda data: data.update({"plan_id": "not-a-plan"}),
        lambda data: data.update({"device_name": "unsafe\x00name"}),
        lambda data: data["readiness"].update({"battery_percent": True}),
        lambda data: data["readiness"].update({"unexpected": "field"}),
    )
    for mutate in mutations:
        data = json.loads(json.dumps(original))
        mutate(data)
        unsigned = dict(data)
        unsigned.pop("plan_digest", None)
        data["plan_digest"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        store.latest_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = store.load_latest()

        assert not loaded.valid
        assert not loaded.integrity_verified
        assert "schema or typed evidence" in loaded.reason
