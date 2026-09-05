"""Execute a supported source-declared installation with one exact-plan confirmation."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

from romverse.guardian.source_installation import SourceInstallationPlan, SourceInstallationResult
from romverse.ui.background import ManagedRunnable
from romverse.ui.local_flash import LocalFlashDialog, LocalFlashSignals


class SourceInstallationWorker(ManagedRunnable):
    def __init__(self, service, device, recipe, *, plan=None):
        super().__init__()
        self.service = service
        self.device = device
        self.recipe = recipe
        self.plan = plan
        self.cancel_requested = Event()
        self.signals = LocalFlashSignals()

    def execute(self):
        try:
            value = (
                self.service.inspect(self.device, self.recipe)
                if self.plan is None
                else self.service.execute(
                    self.plan,
                    accepted_digest=self.plan.plan_digest,
                    risk_accepted=True,
                    should_cancel=self.cancel_requested.is_set,
                    progress=self.signals.progress.emit,
                )
            )
            self.signals.complete.emit(value)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class SourceInstallationDialog(LocalFlashDialog):
    """Reuse exact-phone transitions/boot monitoring without pretending this is a subset."""

    def __init__(self, service, devices, parent=None, *, recipe, **kwargs):
        self.recipe = recipe
        self.preparation = recipe  # Exact source attribution for the recovery handoff.
        super().__init__(service, devices, parent, **kwargs)
        self.setWindowTitle("ROMVERSE · Source-declared installation")
        self.eyebrow.setText("GUIDED INSTALLATION  •  PACKAGE PROCEDURE")
        self.title.setText("Review the complete declared installation")
        self.introduction.setText(recipe.label)
        self.introduction.setTextFormat(Qt.TextFormat.PlainText)
        self.mapping_hint.setText(
            "This sequence comes from a supported package procedure, not guessed filenames. "
            "It can replace boot-critical firmware and the full super container. Read every action."
        )
        self.add_button.hide()
        self.remove_button.hide()
        self.images.setHorizontalHeaderLabels(("Declared action", "Destination / source member"))
        self.images.setRowCount(len(recipe.steps))
        for index, step in enumerate(recipe.steps):
            target = (
                f"{step.partition} ← {step.image_member}"
                if step.action == "flash"
                else step.slot
                if step.action == "set_active"
                else step.partition
                if step.action == "erase"
                else "Android"
            )
            for column, text in enumerate((step.action.replace("_", " "), target)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.images.setItem(index, column, item)
        self.review_button.setText("Review installation and phone")
        self.flash_button.setText("Run reviewed installation…")
        self.boundary.setText(
            (
                "DATA WILL BE ERASED. "
                if recipe.wipe
                else "User data is kept, but compatibility is unproven. "
            )
            + "Keep an independent backup and recovery route. Boot, readback and subsystem health "
            "are measured separately; procedure recognition is not a safety certificate."
        )
        self.status.setText(
            f"{len(recipe.steps)} declared actions · target slot {recipe.target_slot.upper()}. "
            "Review sends only read-only checks; no installation begins without final confirmation."
        )

    def _inspect(self):
        device = self._selected_device()
        if device is None or self.worker is not None or self.monitoring:
            return
        self._invalidate()
        self.status.setText("Verifying the package, exact phone and every declared write…")
        self.progress.setRange(0, 0)
        self._start(SourceInstallationWorker(self.service, device, self.recipe))

    def _change_mode(self):
        device = self._selected_device()
        if device is not None:
            # Do not copy the original script's 'same super size' identity fallback.
            identity = device.codename or device.product
            if identity.casefold() != self.recipe.expected_product.casefold():
                self.status.setText(
                    "Identify the exact intended device before preparing a mode change."
                )
                return
        super()._change_mode()

    def _complete(self, value):
        if isinstance(value, SourceInstallationPlan):
            self.worker = None
            self.plan = value
            lines = [
                f"TARGET  {value.device_name} · {value.masked_serial}",
                f"PRODUCT  {value.product} · CURRENT SLOT  {value.current_slot}",
                f"PROJECT  {value.recipe.project_id}",
                f"SOURCE SHA-256  {value.recipe.source_sha256}",
                f"DECLARATION SHA-256  {value.recipe.script_sha256}",
                f"PLAN  {value.plan_digest}",
                "",
                "DATA  "
                + (
                    "ERASE metadata and userdata"
                    if value.recipe.wipe
                    else "Keep user data · compatibility unproven"
                ),
                "FINISH  "
                + (
                    "Restart Android and measure boot"
                    if value.recipe.reboot
                    else "Stay in bootloader"
                ),
                "",
            ]
            images = {item.member: item for item in value.recipe.images}
            for index, step in enumerate(value.recipe.steps, 1):
                lines.append(f"{index}. {step.action} {step.partition or step.slot or 'Android'}")
                if step.action == "flash":
                    image = images[step.image_member]
                    lines.extend((f"   {image.member}", f"   SHA-256: {image.sha256}"))
                    if step.chunk_size:
                        lines.append(f"   Transfer chunk limit: {step.chunk_size}")
            lines.extend(("", "WARNINGS", *value.warnings))
            self.review.setPlainText("\n".join(lines))
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.status.setText(
                "Review every action and risk, then explicitly confirm this exact procedure."
            )
            self._set_busy(False)
        elif isinstance(value, SourceInstallationResult):
            finished = self.worker
            stop_requested = (
                isinstance(finished, SourceInstallationWorker)
                and finished.cancel_requested.is_set()
            )
            self.worker = None
            self.plan = None
            self.result = value
            self.review.appendPlainText(
                f"\nRESULT  {value.state}\n{value.summary}\nReceipt: {value.receipt_path}"
            )
            for step in value.results:
                self.review.appendPlainText(
                    f"\n{step.action} {step.partition} · exit {step.returncode}\n{step.output}"
                )
            if value.observed_device is not None:
                self._adopt_device(value.observed_device)
            self.progress.setRange(0, len(self.recipe.steps))
            self.progress.setValue(value.completed_count)
            self.progress.setFormat("%v / %m declared actions completed · boot separate")
            self.status.setText(value.summary)
            self.operation_finished.emit(value)
            if (
                value.state == "completed"
                and value.reboot_requested
                and self.boot_service is not None
                and not stop_requested
            ):
                self._start_boot(value.observed_device or self.last_flash_device)
            else:
                self._set_busy(False)
                if stop_requested and value.state == "completed":
                    self.status.setText(
                        value.summary
                        + " Boot monitoring was not started because you requested Stop. "
                        "Choose Check Android boot when ready."
                    )
                if value.phone_change_attempted and value.state != "completed":
                    self.recovery_requested = True
                    self.accept()
        else:
            super()._complete(value)

    def _confirm_flash(self):
        plan = self.plan
        if (
            not isinstance(plan, SourceInstallationPlan)
            or self.worker is not None
            or self.monitoring
        ):
            return
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setWindowTitle("Confirm source-declared installation")
        question.setText(
            f"Run {len(plan.recipe.steps)} declared actions on {plan.device_name} {plan.masked_serial}?"
        )
        question.setInformativeText(
            (
                "ALL PHONE USER DATA WILL BE ERASED.\n\n"
                if plan.recipe.wipe
                else "User data is kept, but boot/data compatibility is unproven.\n\n"
            )
            + "This changes the active slot and writes boot-critical firmware and the full super container. "
            + (
                "It will restart Android at the end. "
                if plan.recipe.reboot
                else "It will stay in bootloader afterward. "
            )
            + "Keep USB connected. Stop requests take effect between actions, not in the middle of a write. "
            "Proceed only with your own backup and recovery route and after accepting these risks."
        )
        question.setDetailedText(self.review.toPlainText())
        confirm = question.addButton(
            "Erase data and install" if plan.recipe.wipe else "Install reviewed package",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel = question.addButton(QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(cancel)
        question.exec()
        if question.clickedButton() is not confirm:
            self.status.setText("Installation cancelled. No installation command was sent.")
            return
        if self.plan is not plan or self.worker is not None or self.monitoring:
            self.status.setText("The target or plan changed. Review again before confirming.")
            return
        self.result = None
        self.execution_error = ""
        self.last_attempt_device = self._selected_device()
        self.last_flash_device = self.last_attempt_device
        self.boot_report = None
        self.boot_error = ""
        self.status.setText(
            "Preserving the reviewed images, then running the exact confirmed sequence…"
        )
        self._start(
            SourceInstallationWorker(self.service, self.last_attempt_device, self.recipe, plan=plan)
        )

    def _set_busy(self, busy, *, writing=False):
        writing = writing or (
            isinstance(self.worker, SourceInstallationWorker) and self.worker.plan is not None
        )
        super()._set_busy(busy, writing=writing)
        if writing:
            self.cancel_button.setText("Stop after current action")

    def _cancel(self):
        if isinstance(self.worker, SourceInstallationWorker):
            self.worker.cancel_requested.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(
                "Stop requested. The current action will finish; completed changes cannot be undone automatically."
            )
        else:
            super()._cancel()

    def _failed(self, message):
        if isinstance(self.worker, SourceInstallationWorker) and self.worker.plan is not None:
            self.execution_error = message
        super()._failed(message)
