# Fedora development build

ROMVERSE can be run directly from a Fedora source checkout or assembled as a
portable one-folder development build. These instructions do not install anything
system-wide and do not enable production Recovery execution.

## Run from source

From the repository root, use the project environment:

```bash
python -m romverse --workspace "$PWD/.romverse-development" --skip-onboarding
```

Use a separate workspace path for development so personal ROMVERSE projects are
not mixed with disposable build evidence. Closing the window shuts down the app;
removing the chosen development workspace later is optional and is not part of the
launcher.

For a display-free startup/shutdown check:

```bash
QT_QPA_PLATFORM=offscreen python -m romverse \
  --workspace /tmp/romverse-release-smoke \
  --skip-onboarding --release-smoke
```

## Build the Fedora desktop bundle

```bash
python -m build --wheel --outdir build/wheel
python scripts/verify_wheel.py build/wheel/romverse-0.1.0-py3-none-any.whl
python scripts/build_desktop_executable.py --clean --output build/frozen
QT_QPA_PLATFORM=offscreen python scripts/smoke_frozen_desktop.py \
  build/frozen/ROMVERSE/ROMVERSE
python scripts/package_desktop_bundle.py \
  --source build/frozen/ROMVERSE \
  --output dist/ROMVERSE-Desktop-0.1.0-linux-x86_64.zip
```

The runnable binary is `build/frozen/ROMVERSE/ROMVERSE`. The ZIP is a local
development artifact, not a signed or released package. It can be extracted to a
user-writable directory and launched without a system-wide install.

## Complete inert Guided Recovery journey

This exercises the production Recovery boundaries with synthetic evidence and an
in-memory phone model. It never invokes ADB, Fastboot, a subprocess adapter, or a
physical phone:

```bash
python scripts/simulate_guided_recovery.py /tmp/romverse-guided-recovery
```

The destination must not already exist. The report at
`/tmp/romverse-guided-recovery/guided-recovery-report.json` records the demonstrated
Scan → Match → Prepare → Consent → Result → Reassessment → Verification chain.
All adapter trust is ephemeral and explicitly test-only; no production execution
authority is created.
