from __future__ import annotations

from types import SimpleNamespace

from romverse.ui.ascension_protocol import AscensionHandoffWorker
from romverse.ui.background import CoalescedProgress, measured_percent
from romverse.ui.backup_center import RecoveryEvidenceWorker
from romverse.ui.debloat_sequence import DebloatWorker
from romverse.ui.phone_backup import PhoneMediaBackupWorker


def test_coalesced_progress_bounds_deduplicates_and_never_moves_backwards() -> None:
    published: list[int] = []
    progress = CoalescedProgress(published.append)

    for _ in range(10_000):
        progress(4)
    progress(3)
    progress(-50)
    for _ in range(10_000):
        progress(5.9)
    progress(99)
    progress(80)
    progress(500)

    assert published == [4, 5, 99, 100]


def test_measured_percent_never_rounds_unfinished_work_up_to_completion() -> None:
    assert measured_percent(995, 1_000) == 99
    assert measured_percent(1_000, 1_000) == 100
    assert measured_percent(0, 0) is None


class _NoisyIntegerService:
    @staticmethod
    def _report(progress) -> None:
        for _ in range(10_000):
            progress(4)
        for _ in range(10_000):
            progress(5)
        progress(3)
        progress(100)

    def scan(self, _project_id, progress):
        self._report(progress)
        return "scan-complete"

    def execute(self, _plan, progress):
        self._report(progress)
        return "operation-complete"


def test_direct_weighted_and_ascension_workers_coalesce_noisy_services() -> None:
    cases = (
        (DebloatWorker(_NoisyIntegerService(), "project"), "scan-complete"),
        (AscensionHandoffWorker(_NoisyIntegerService(), object()), "operation-complete"),
    )

    for worker, expected in cases:
        published: list[int] = []
        completed: list[object] = []
        worker.signals.progress.connect(published.append)
        worker.signals.complete.connect(completed.append)

        worker.execute()

        assert published == [4, 5, 100]
        assert completed == [expected]


def test_phone_backup_worker_relays_real_bytes_without_fixed_phase_weights() -> None:
    class NoisyByteBackupService:
        @staticmethod
        def execute(_plan, progress):
            for _ in range(10_000):
                progress(4, 100)
            for _ in range(10_000):
                progress(5, 100)
            progress(3, 100)
            progress(995, 1_000)
            progress(100, 100)
            return "operation-complete"

    worker = PhoneMediaBackupWorker(NoisyByteBackupService(), object())
    published: list[int] = []
    completed: list[object] = []
    worker.signals.progress.connect(published.append)
    worker.signals.complete.connect(completed.append)

    worker.execute()

    assert published == [4, 5, 99, 100]
    assert completed == ["operation-complete"]


def test_phone_backup_worker_withholds_terminal_until_recovery_evidence_is_saved() -> None:
    class ByteBackupService:
        @staticmethod
        def execute(_plan, progress):
            progress(25, 100)
            progress(100, 100)
            return "verified-receipt"

    class RecoveryService:
        registered = False

        def register_phone_media_backup(self, project_id, archive, receipt):
            assert project_id == "project"
            assert archive.name == "backup.zip"
            assert receipt == "verified-receipt"
            self.registered = True

    recovery = RecoveryService()
    worker = PhoneMediaBackupWorker(
        ByteBackupService(),
        SimpleNamespace(archive_path="/tmp/backup.zip"),
        recovery,
        "project",
    )
    published: list[int] = []
    completed: list[object] = []
    worker.signals.progress.connect(published.append)
    worker.signals.complete.connect(completed.append)

    worker.execute()

    assert recovery.registered
    assert published == [25, 100]
    assert 82 not in published
    assert completed == ["verified-receipt"]


def test_done_total_recovery_worker_coalesces_byte_callbacks() -> None:
    class NoisyRecoveryService:
        @staticmethod
        def verify(_project_id, progress):
            for _ in range(10_000):
                progress(4, 100)
            for _ in range(10_000):
                progress(5, 100)
            progress(3, 100)
            progress(995, 1_000)
            progress(100, 100)
            return "evidence-complete"

    worker = RecoveryEvidenceWorker(NoisyRecoveryService(), "verify", "project")
    published: list[int] = []
    completed: list[object] = []
    worker.signals.progress.connect(published.append)
    worker.signals.complete.connect(completed.append)

    worker.execute()

    assert published == [4, 5, 99, 100]
    assert completed == ["evidence-complete"]
