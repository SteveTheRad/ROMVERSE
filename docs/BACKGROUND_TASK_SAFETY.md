# Background task safety

ROMVERSE performs device scans, APK inspection/installation, ROM project operations, Time
Machine verification/restoration, toolchain downloads, and Command Console probes away from the
Qt UI thread.

All Qt background work must use `ManagedRunnable` and `start_background` from
`romverse.ui.background`. Direct use of `QRunnable` or `QThreadPool` elsewhere in the UI is a
release-gate failure.

The supervisor provides these invariants:

- Qt auto-delete is disabled for every runnable.
- The application owns a worker independently of the page or dialog that launched it.
- Result callbacks may finish without destroying a runnable whose Python/Shiboken stack is still
  unwinding.
- Completed workers receive a UI-thread retention period before their final reference is released.
- Thread-pool concurrency is bounded to reduce resource contention.
- Application shutdown stops new work, disconnects page callbacks, clears queued work, and waits
  for active bounded tasks before Python exits.
- Worker signal bridges are retired explicitly on the GUI thread before Python/Shiboken teardown.
- Companion HTTPS, request, and discovery threads are stopped and joined independently of whether
  the Companion page itself receives a close event.
- Repeated shutdown calls are harmless and cannot double-retire a Qt object.

This policy was introduced after a captured Python 3.14/PySide6 crash showed a pooled Qt callback
segfaulting during Python/Shiboken lifetime handling. It fixes the ROMVERSE process-lifetime race;
it does not claim to repair host kernel, GPU, Wi-Fi, firmware, or PCIe faults.

Native and unhandled Python faults are appended to
`<workspace>/logs/crash/runtime-fault.log`. Verification includes repeated 300-worker callback
stress, shutdown-drain tests, repeated full-window close cycles, and a source-policy test that
rejects unsupervised Qt thread-pool use.
