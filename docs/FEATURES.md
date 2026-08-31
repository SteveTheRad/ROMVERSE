# ROMVERSE Features and Status

## Status rules

- **Planned**: approved direction without an implementation claim.
- **In Progress**: implementation or validation is actively incomplete.
- **Implemented**: source exists, but proportionate verification is incomplete.
- **Implemented and Verified**: source exists and the stated automated/build/runtime evidence passed.
- **Unverified**: the stated environment or real-world integration has not been demonstrated.

Verification scope is part of the status. Automated fixtures do not prove physical-device safety or
commercial release readiness.

## Verified repository baseline

On 2026-08-31, an isolated Ubuntu clone passed:

- 956 Python tests
- Ruff lint and formatting checks
- desktop wheel build, integrity verification, clean install, and offscreen startup smoke
- packaged validation of 21 Device Packs
- Companion JVM tests and debug APK assembly through Gradle Wrapper 8.11.1

## Desktop and host

| Capability | Status | Verification scope |
| --- | --- | --- |
| PySide6 desktop shell and feature navigation | Implemented and Verified | Python UI tests and installed-wheel offscreen smoke |
| Workspace/settings initialization | Implemented and Verified | automated tests and fresh smoke workspace |
| Linux host paths and tool discovery | Implemented and Verified | current Ubuntu run plus automated tests |
| Windows host paths and bootstrap | Implemented | targeted CI smoke is required; the initial full run exposed 70 POSIX-assumption failures, so full runtime remains Unverified |
| Optional ROM tool inventory/provisioning receipts | Implemented and Verified | automated tool/provisioning tests; not every external binary was installed in the isolated clone |

## Device, diagnostics, and APK

| Capability | Status | Verification scope |
| --- | --- | --- |
| ADB parsing, inventory, and Device Engine | Implemented and Verified | automated tests and fixtures |
| Device identity, Device DNA, and Capability Map | Implemented and Verified | automated evidence/identity tests |
| Diagnostics, history, comparison, and safe cache optimization | Implemented and Verified | automated tests |
| Guarded APK inspection/install receipts | Implemented | automated tests pass; physical-device installation was not run during migration |
| Live physical-device coverage across supported OEMs | Unverified | requires representative authorized hardware |

Capability Map states are exactly `SUPPORTED`, `CAUTION`, `UNSUPPORTED`, and
`UNCONFIRMED`.

## ROM workspace

| Capability | Status | Verification scope |
| --- | --- | --- |
| ROM project/workspace registration | Implemented and Verified | automated workspace/project tests |
| Source identity and firmware inspection | Implemented and Verified | automated archive/folder/fixture tests |
| Payload, fastboot, partition, AVB, filesystem, and recovery evidence models | Implemented and Verified | automated fixture tests |
| Debloat discovery/planning with protected/caution boundaries | Implemented and Verified | automated tests |
| Recipe preview, approval, execution receipts, snapshots, and rollback | Implemented and Verified | contained-workspace automated tests |
| Exact-contract local build candidates and readiness evidence | Implemented and Verified | automated build/readiness tests |
| Arbitrary-device production ROM build compatibility | Unverified | requires independent firmware/device matrix evidence |
| Genesis Sequence end-to-end production workflow | In Progress | component code exists; full real-device route is not release-verified |

## Guardian, backup, signing, and flashing

| Capability | Status | Verification scope |
| --- | --- | --- |
| Guardian policy, approval, audit chain, manifests, and evidence bindings | Implemented and Verified | automated safety and hostile-input tests |
| Local media backup plans/receipts and recovery snapshots | Implemented and Verified | automated tests |
| Offline signing ceremony policy | Implemented | limited to explicitly flash-validated Device Pack policy; no Pack is production-certified by this fact |
| Full app-private phone backup/restore | Planned | locked pending an exact tested contract |
| Controlled physical-device flashing | Unverified | handoff/readiness code exists; real write and recovery contracts remain locked |
| Bootloader relock | Planned: never | permanent safety boundary; ROMVERSE must never relock |

## Android Companion

| Capability | Status | Verification scope |
| --- | --- | --- |
| Native Android application and responsive UI | Implemented and Verified | JVM tests and debug APK assembly |
| Local Device DNA, Vitalis, Lifeline, Live Console, Ascension, Galaxy, Members, and privacy domains | Implemented and Verified | JVM/domain tests |
| ROMVERSE Link parsing, TLS pinning model, pairing state, and bounded read-only telemetry | Implemented and Verified | automated desktop/Companion protocol tests |
| Connected Activity instrumentation | Unverified | `connectedDebugAndroidTest` not run during migration |
| Physical-device Link recovery and OEM behavior | Unverified | requires authorized representative devices |
| Companion device-changing authority | Planned: none | current Link remains read-only |

## Intelligence and online systems

| Capability | Status | Verification scope |
| --- | --- | --- |
| Nexus planning/events and Compatibility Matrix | Implemented and Verified | automated deterministic tests |
| Provider-independent AI Gateway and usage governor | Implemented and Verified | automated provider/privacy/fallback tests |
| Optional Google programmable search remediation | Implemented | requires local API configuration and live service validation |
| Local Synapse evidence models | Implemented and Verified | automated tests |
| Hosted Synapse/Nexus services | Planned | production infrastructure is outside this source baseline |
| Public Galaxy synchronization | Planned | local/offline Galaxy is implemented; public service is not |
| Membership, accounts, billing, and commercial backend | Planned | product direction only, not a local implementation claim |

## Release status

The codebase is an active private development baseline, not a production-certified ROM flashing
release.

### In Progress

- connected Android Activity validation
- representative physical-device compatibility and recovery evidence
- signed release artifact process
- Windows and Legion Go 2 clean-machine validation
- end-to-end build/write/recovery certification

### Unverified

- physical-device flashing or rooting
- full private-app backup/restore
- production signing keys and public update continuity
- hosted service operation and commercial scale
- second-machine portability beyond the verified isolated Ubuntu clone

## Documentation rule

Update this file whenever implementation or verification scope changes. A roadmap, test name,
design document, or UI label is not sufficient evidence by itself.
