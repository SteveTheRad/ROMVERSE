# ROMVERSE Architecture

## Current implementation

ROMVERSE is a Python/PySide6 desktop application plus a native Kotlin Android Companion. The
desktop package uses a `src/` layout and launches through `romverse.app:main`. The Companion is
an independent Android application under `companion/`.

The implemented architecture separates presentation, evidence collection, domain planning,
Guardian authorization, execution gateways, persistence, and verification. UI code does not grant
itself device-changing authority.

## Desktop startup and host boundary

`src/romverse/app.py` performs:

1. Qt application and single-instance setup.
2. Linux/Windows host selection.
3. settings and workspace resolution.
4. read-only host-tool verification.
5. receipt-verified managed-tool activation.
6. Guardian audit, policy, and execution-gateway construction.
7. Device Pack registry and attestation setup.
8. ADB device engine creation only when ADB is available.
9. main-window launch under runtime crash/thread guards.

`src/romverse/platform/host.py` owns operating-system paths and executable discovery.

- Linux data: `~/.local/share/ROMVERSE`
- Linux config: `$XDG_CONFIG_HOME/ROMVERSE` or `~/.config/ROMVERSE`
- Windows data: `%LOCALAPPDATA%\ROMVERSE`
- optional data/workspace override: `ROMVERSE_HOME`

Repository paths are never the default runtime workspace.

## Desktop layers

### Presentation

`src/romverse/ui/` contains the PySide6 shell and feature centers, including Device Center,
Diagnostics, ROM Studio, Guardian, Nexus, Companion, backup, repair, terminal, history, tooling,
APK, Galaxy, Members, Ascension, and guided workflows.

Long work is routed through bounded background helpers so UI surfaces can display genuine progress
without acquiring independent execution authority.

### Core and platform

- `core/`: settings, workspace initialization, activity/history, privacy, and runtime stability
- `platform/`: Linux/Windows host abstraction
- `infrastructure/`: subprocess isolation, local persistence, tool verification/provisioning, and
  payload-dumper integration

### Device evidence

- `device/`: ADB inventory, parsing, identity, Device DNA, APK installation, root evidence, and
  device engine
- `device_packs/`: pack registry, validation, attestations, publisher trust, drafts, source audit,
  and Companion export
- `diagnostics/`: findings, analyzers, history, and bounded cache optimization

Device facts retain evidence and confidence. Unknown capability remains explicitly
`UNCONFIRMED`.

### ROM workspace and build domains

`rom/` contains project registration, source identity/intelligence, payload and fastboot
inspection, partition/filesystem evidence, ROM DNA, packages, debloat planning, recipes,
recovery evidence, build input preparation, exact-contract build candidates, build/readiness
evidence, signing ceremony policy, and rollback-aware execution records.

These modules operate on contained workspaces and evidence-bound receipts. Their automated tests do
not by themselves certify arbitrary firmware or physical-device compatibility.

### Guardian

`guardian/` owns policy, approval, audit integrity, evidence bindings, manifest review, backup
handoffs, Ascension handoffs, and flash handoff preparation.

The execution flow is:

```text
UI intent
  -> domain plan and evidence
  -> Guardian policy/readiness
  -> explicit authorization where required
  -> ExecutionGateway
  -> bounded subprocess/device action
  -> receipt and audit evidence
  -> post-action verification
```

The current honest boundary leaves real device flashing locked/unverified until exact write
contracts, compatibility evidence, recovery evidence, and independent physical-device validation
exist.

### Intelligence and orchestration

- `nexus/`: deterministic mission planning, events, and compatibility decisions
- `intelligence/`: provider-independent AI gateway, usage governor, local action evidence, online
  remediation, and local Synapse models
- `repair/`: host repair knowledge, templates, and sessions

Local/deterministic components are implemented. Production Nexus/Synapse services, public
synchronization, membership infrastructure, and commercial backend operation remain Planned or In
Progress outside the local repository boundary.

### Backup and continuity

`backup/` contains local media backup plans/receipts and controlled handoff records. Full
app-private phone backup/restore is not claimed as verified.

## Android Companion

The Companion uses:

- application id `com.radforge.romverse.companion`
- Kotlin 2.0.21
- Android Gradle Plugin 8.7.3
- Java/Kotlin target 17
- minimum SDK 26
- compile/target SDK 35

Its application source lives under `companion/app/src/`. It implements the Android UI and local
domains for Link, Device DNA, Vitalis, Lifeline, Live Console, Ascension status, Galaxy, Members,
privacy controls, and local history.

The Link boundary is read-only. Pairing, pinning, bounded telemetry, privacy filtering, and
fail-closed parsing are implemented and covered by automated tests. A JVM/debug build does not
replace connected Activity tests or physical-device pairing validation.

## Packaging and build architecture

- `pyproject.toml`: Python package metadata, runtime dependencies, console entry point, pytest,
  and Ruff configuration
- `.github/workflows/test.yml`: full Ubuntu Python matrix, targeted Windows portability smoke,
  Companion build, and installed desktop package smoke
- `companion/gradlew`: pinned Gradle 8.11.1 portability entry point
- `scripts/verify_wheel.py`: source-to-wheel and Device Pack integrity gate
- `scripts/smoke_installed_desktop.py`: installed package/workspace startup gate

Generated environments, SDKs, caches, APKs, media, firmware, and workspaces remain outside version
control.

## Implementation status boundary

### Implemented and Verified

The isolated Ubuntu migration verified desktop bootstrap, 956 Python tests, lint/format, wheel
integrity, installed-wheel startup, Companion JVM tests, and debug APK assembly.

### Implemented

The source contains Linux and Windows host paths, device/ROM/Guardian domains, Companion Link and UI
domains, build/recovery/signing evidence models, and optional online-remediation integration.
Verification scope varies by feature and is recorded in `FEATURES.md`.

### In Progress

Independent physical-device compatibility, connected Android instrumentation, signed release
production, and end-to-end ROM write/recovery validation.

### Planned

Production membership/accounts, public Galaxy synchronization, hosted Synapse/Nexus services, and
commercial release infrastructure.

### Unverified

Windows runtime behavior in this migration, Legion Go 2 setup, physical-device destructive
operations, public release signing, and production backend operation.
