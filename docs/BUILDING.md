# Building ROMVERSE

## Verified baseline

This guide is derived from the committed source and was exercised from an isolated clone on
2026-08-31 using Ubuntu 26.04.1 LTS.

The migration verification used:

- Python 3.14.4
- OpenJDK 17.0.20
- Gradle Wrapper 8.11.1
- Android compile/target SDK 35

The following gates passed:

- clean desktop bootstrap from `scripts/bootstrap.sh`
- 956 Python tests
- Ruff lint and formatting checks across 309 Python files
- wheel build and source-to-wheel verification
- fresh-environment installed-wheel smoke launch with 21 packaged Device Packs
- Companion JVM tests
- Companion debug APK assembly

Windows is represented by a native host abstraction, PowerShell bootstrap, and an Ubuntu/Windows
CI matrix. Windows runtime verification was not performed during this migration and remains
unverified until the CI run or a Windows development machine confirms it.

## Repository clone

Configure GitHub SSH access for the development computer, then clone:

```bash
git clone git@github.com:SteveTheRad/ROMVERSE.git
cd ROMVERSE
```

The repository is private. Do not copy source, internal documents, or artifacts into public
repositories.

## Desktop prerequisites

Required:

- Git
- Python 3.11, 3.12, 3.13, or 3.14
- internet access for the first dependency installation

Python dependencies are declared in `pyproject.toml`:

- `PySide6>=6.8,<7`
- `cryptography>=46,<47`
- development extras: pytest, pytest-cov, and Ruff

### Ubuntu/Linux setup

```bash
./scripts/bootstrap.sh
source .venv/bin/activate
romverse
```

Equivalent manual setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/romverse
```

Minimal Ubuntu installations and GitHub's Ubuntu runner require EGL for PySide6 imports:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libpulse0
```

These packages provide the EGL and PulseAudio shared libraries required by the current PySide6
bundle on minimal Ubuntu. Other Qt platform packages may still be desktop/distribution-dependent. The committed CI workflow
sets `QT_QPA_PLATFORM=offscreen` for headless tests.

### Windows setup

From PowerShell:

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\Activate.ps1
romverse
```

Windows development is implemented in the host abstraction and CI configuration but was not
runtime-verified during this migration.

## Workspace and local configuration

ROMVERSE stores development/runtime data outside the repository.

- Linux default: `~/.local/share/ROMVERSE/workspace`
- Windows default: `%LOCALAPPDATA%\ROMVERSE\workspace`
- Optional override: `ROMVERSE_HOME`

`ROMVERSE_HOME` is useful for an isolated development or smoke-test workspace. It must not point
at a temporary directory for normal use unless losing that workspace is acceptable.

Optional online-remediation configuration names found in the source are:

- `ROMVERSE_GOOGLE_SEARCH_API_KEY`
- `ROMVERSE_GOOGLE_SEARCH_ENGINE_ID`

These values are optional for offline/local development gates. Store real values in the local
environment or an approved secret manager. Never commit them to `.env`, source, tests, docs, or
shell history.

## Desktop quality gates

Activate the virtual environment, then run:

```bash
pytest
ruff check .
ruff format --check .
```

For headless Linux:

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## Desktop package build

```bash
python -m pip install build
python -m build --wheel
python scripts/verify_wheel.py dist/romverse-0.1.0-py3-none-any.whl
```

The wheel verifier checks required modules/assets, rejects unsafe archive paths and generated
Python caches, verifies source-to-wheel bytes, and validates the Device Pack index and SHA-256
entries.

Installed-package smoke test:

```bash
python -m pip install dist/romverse-0.1.0-py3-none-any.whl
QT_QPA_PLATFORM=offscreen python scripts/smoke_installed_desktop.py /tmp/romverse-smoke
```

Use a disposable workspace for this smoke test.

## Optional Android/ROM host tools

The desktop starts without the full ROM toolchain. It detects tools and reports missing
capabilities rather than silently assuming they exist.

The current verifier recognizes:

- ADB and Fastboot
- Git, 7-Zip, unzip, LZ4, GNU Make, Java, and fakeroot
- simg2img and debugfs
- avbtool and payload-dumper-go
- mkfs.erofs and fsck.erofs
- lpmake, lpunpack, and lpdump/lpdumps
- aapt2 and apksigner
- the appropriate OEM/Google USB driver on Windows

Install only the tools required for the workflow being developed. Managed tool activation is
receipt- and digest-verified; an executable is not trusted merely because it exists.

## Companion prerequisites

Required:

- JDK 17
- Android SDK Platform 35
- Android SDK Build Tools 35.x
- Android SDK Platform Tools

Set `ANDROID_HOME` or `ANDROID_SDK_ROOT` to the SDK location. A global Gradle installation is
not required; the repository commits the Gradle 8.11.1 wrapper.

Linux/macOS:

```bash
./companion/gradlew --no-daemon -p companion testDebugUnitTest :app:assembleDebug
```

Windows:

```powershell
.\companion\gradlew.bat --no-daemon -p companion testDebugUnitTest :app:assembleDebug
```

The debug APK is generated at:

```text
companion/app/build/outputs/apk/debug/app-debug.apk
```

It is a development artifact, not a signed public release.

Additional Android gates:

```bash
./companion/gradlew --no-daemon -p companion :app:lintDebug
./companion/gradlew --no-daemon -p companion :app:connectedDebugAndroidTest
```

`connectedDebugAndroidTest` requires an authorized Android device or emulator. It was not run
during this repository migration and remains unverified here.

## Generated and local-only files

The repository intentionally excludes:

- Python environments, caches, coverage, wheels, and source distributions
- Android SDKs, local Gradle caches, Kotlin state, build directories, APKs, and signing material
- IDE metadata and `local.properties`
- logs, temporary work, screenshots, trailers, and other `work/` output
- ROM/firmware images, archives, extracted workspaces, backups, and device dumps
- credentials, certificates, private/signing keys, and populated environment files

Recreate these from documented tools and source. Do not copy this PC's caches into Git.

## Clean-machine continuation checklist

1. Clone the private repository over SSH.
2. Install a supported Python and run the platform bootstrap.
3. Run the Python test, lint, and format gates.
4. Build and verify the wheel.
5. Install JDK 17 and Android SDK 35 if Companion work is required.
6. Run the wrapper-based Companion JVM/build gate.
7. Restore only required secrets from secure storage.
8. Install optional ROM tools for the workflow under development.
9. Use a new local workspace; do not copy machine caches.
10. Record any platform-specific setup gap discovered on the new machine.

Portability is implemented and verified for the isolated Ubuntu clone used in this migration.
Second-machine Windows, Legion Go 2, connected-device, and physical-ROM validation remain
unverified until performed there.
