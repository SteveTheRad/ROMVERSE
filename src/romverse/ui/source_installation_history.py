"""Historical source-installation evidence with an explicitly read-only boot check."""

from __future__ import annotations

from PySide6.QtCore import Qt

from romverse.guardian.source_installation import (
    SourceInstallationResult,
    validate_source_installation_boot_binding,
)
from romverse.ui.local_flash import (
    LocalBootWorker,
    LocalFlashDialog,
    LocalFlashDiscoveryWorker,
)


class SourceInstallationHistoryDialog(LocalFlashDialog):
    """Reuse managed observation lifecycle, never the image/mode execution surface."""

    def __init__(self, local, devices, parent=None, *, outcome, boot_service, discover=None):
        self.outcome = outcome
        self.preparation = outcome
        super().__init__(
            local,
            devices,
            parent,
            discover=discover,
            transition_service=None,
            boot_service=boot_service,
        )
        self.result = (
            outcome.result if isinstance(outcome.result, SourceInstallationResult) else None
        )
        self.setWindowTitle("ROMVERSE · Installation history and boot check")
        self.eyebrow.setText("INSTALLATION HISTORY  •  READ-ONLY FOLLOW-UP")
        self.title.setText("Check the phone without reinstalling")
        self.introduction.setText(
            "Review the saved installation record. You can explicitly check Android boot "
            "on the same phone or open diagnosis and recovery. No flashing or rebooting occurs here."
        )
        self.introduction.setTextFormat(Qt.TextFormat.PlainText)
        self.target.setAccessibleName("Exact phone for read-only boot observation")
        self.review.setAccessibleName(
            "Historical installation evidence and current boot observations"
        )
        self.boot_button.setText("Check this phone's Android boot")
        self.boundary.setText(
            "Historical records are not fresh image verification. A boot check reads the phone only; "
            "it does not reinstall, reboot, repair, verify image readback or certify subsystem health."
        )
        self._hide_execution_controls()
        for index, device in enumerate(self.devices):
            if self._matches(device):
                self.target.setCurrentIndex(index)
                break
        self._render_history()
        self._set_busy(False)

    def _matches(self, device):
        if device is None:
            return False
        aliases = {value.strip().casefold() for value in (device.product, device.codename) if value}
        return bool(
            self.service.privacy.pseudonym(device.serial) == self.outcome.device_key
            and self.outcome.product.casefold() in aliases
            and (
                not device.codename
                or device.codename.strip().casefold() == self.outcome.product.casefold()
            )
            and (not device.manufacturer or device.manufacturer.strip().casefold() == "xiaomi")
        )

    def _render_history(self):
        action_ledger = self.outcome.recovery_summary()
        self.review.setPlainText(
            f"HISTORICAL INSTALLATION  ·  {self.outcome.state}\n{self.outcome.summary}\n\n"
            f"Recorded completed actions: {self.outcome.completed_count} / {self.outcome.expected_count}\n"
            f"{action_ledger}\n"
            f"Saved boot evidence: {self.outcome.boot_status}\n\n"
            f"Project: {self.outcome.project_id}\nSource SHA-256: {self.outcome.source_sha256}\n"
            f"Installation receipt: {self.outcome.receipt_path}\n\n"
            "These are historical records, not new observations or a production certificate. "
            "No image bytes are rehashed by opening this history view."
        )
        self.progress.setRange(0, max(1, self.outcome.expected_count))
        self.progress.setValue(self.outcome.completed_count)
        self.progress.setFormat("%v / %m historical actions · boot separate")
        if self._matches(self._selected_device()):
            self.status.setText(
                "The recorded phone is selected. Start a read-only boot check when ready."
            )
        else:
            self.status.setText(
                "Connect and select the same recorded phone to check boot. Other phones cannot inherit this installation."
            )
        if not isinstance(self.outcome.result, SourceInstallationResult):
            self.status.setText(
                "This history has no complete valid transport receipt to link. Open diagnosis and recovery; no boot success will be attached."
            )

    def _hide_execution_controls(self):
        for widget in (
            self.images,
            self.mapping_hint,
            self.add_button,
            self.remove_button,
            self.review_button,
            self.flash_button,
            self.mode_target,
            self.mode_button,
        ):
            widget.setEnabled(False)
            widget.hide()

    def _set_busy(self, busy, *, writing=False):
        super()._set_busy(busy, writing=False)
        self._hide_execution_controls()
        idle = not busy and self.worker is None and not self.monitoring
        self.boot_button.setEnabled(
            idle
            and self.boot_service is not None
            and isinstance(self.outcome.result, SourceInstallationResult)
            and self._matches(self._selected_device())
        )
        self.recovery_button.setVisible(idle)
        self.recovery_button.setEnabled(idle)

    def _invalidate(self, *_args):
        self.plan = None
        if self.worker is None and not self.monitoring:
            self._render_history()
        self._set_busy(self.worker is not None)

    def _start_boot(self, device):
        if self.worker is not None or self.monitoring or self.boot_service is None:
            return
        if not self._matches(device) or not isinstance(
            self.outcome.result, SourceInstallationResult
        ):
            self.status.setText(
                "A valid installation receipt and the same recorded phone are required. No unlinked boot check was started."
            )
            return
        try:
            validate_source_installation_boot_binding(self.service, device, self.outcome.result)
        except Exception:
            self.status.setText(
                "The saved installation record no longer validates for this phone. No boot check was started; open diagnosis and recovery."
            )
            self._set_busy(False)
            return
        self.result = self.outcome.result
        self.last_attempt_device = device
        self.last_flash_device = device
        self.boot_device = device
        self.monitoring = True
        self._boot_stop_requested = False
        self._close_after_boot = False
        self.boot_session = None
        self.boot_report = None
        self.boot_error = ""
        self.status.setText(
            "Reading this exact phone's Android boot state. No write or reboot will be sent…"
        )
        self.progress.setRange(0, 0)
        self._start(LocalBootWorker(self.boot_service, device, flash_result=self.outcome.result))

    def _start(self, worker):
        if not isinstance(worker, (LocalBootWorker, LocalFlashDiscoveryWorker)):
            self._execution_unavailable()
            return
        super()._start(worker)

    def _complete(self, value):
        if not isinstance(self.worker, (LocalBootWorker, LocalFlashDiscoveryWorker)):
            self._execution_unavailable()
            return
        super()._complete(value)

    def _open_recovery(self):
        device = self._selected_device()
        if self.worker is None and not self.monitoring:
            self.last_attempt_device = device if self._matches(device) else None
            self.last_flash_device = self.last_attempt_device
        super()._open_recovery()

    def _execution_unavailable(self, *_args, **_kwargs):
        self.status.setText(
            "This history view is read-only. It cannot install images, change slots or reboot a phone."
        )

    # Hide AND disable the inherited method entry points: callbacks and tests must
    # not turn a historical review into a fresh device-changing authorization.
    add_image = _execution_unavailable
    _choose_image = _execution_unavailable
    _remove_image = _execution_unavailable
    _inspect = _execution_unavailable
    _confirm_flash = _execution_unavailable
    _change_mode = _execution_unavailable
    _confirm_transition = _execution_unavailable
