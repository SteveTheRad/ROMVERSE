# ROMVERSE product vocabulary

ROMVERSE uses a shared product language across Desktop, Companion, guided missions,
documentation, buttons, tooltips, and support instructions.

| Canonical surface | Purpose | Previous display name |
|---|---|---|
| Command Deck | Device overview and safest next action | Dashboard |
| Device Portal | Connected Android device identity and live evidence | Device Center, Device Nexus |
| System Scan | Read-only diagnostics and analysis | Diagnostics |
| Health Timeline | Saved, privacy-safe device history | Health History / Logs |
| Activity Center | Cross-feature workspace and mission outcomes | Activity Ledger / Full Log |
| Guardian Core | Safety policy, approval, and audit boundary | Guardian Center |
| Recovery Bay | Diagnose faults and prepare repair plans | Repair My Phone |
| Device Atlas | OEM compatibility profiles and Device Packs | Device Packs / Mod Manager |
| ROM Studio | Protected ROM projects and creation workflows | Build Manager |
| Genesis Sequence | Guided ROM creation journey | Automatic Guided Setup |
| Architect Mode | Complete advanced ROM workspace | Expert Mode |
| Partition Atlas | Payload, image, partition, and filesystem exploration | Partition Workspace |
| Recipe Forge | Guided, auditable ROM modifications | Guided Recipe Setup |
| Forge Control | Build, signing, recovery, and flash readiness | Build Control Center |
| App Launchpad | Guardian-approved APK installation | APK Installer |
| Time Machine | Backup, snapshots, rollback, and restore | Backup & Recovery |
| Quantum Optimizer | Performance, storage, and health recommendations | System Optimizer |
| Command Console | Guardian-bounded host and ADB commands | Terminal |
| Forge Arsenal | Build tools, dependencies, and drivers | Toolchain Manager |
| ROMVERSE Archives | Offline diagnostic and repair knowledge | Knowledge Base |
| ROMVERSE Link | Desktop-to-phone pairing and telemetry | Companion Center, Companion Link |
| Live Console | Genuine Nexus mission progress, evidence, explanations, and outcomes | Mission Console |
| ROMVERSE Galaxy | Optional connected ecosystem and community | Galaxy |

## Compatibility contract

These are display and navigation names. ROMVERSE deliberately retains existing route IDs,
Python module names, JSON schema fields, receipt operation names, and workspace directory
names such as `original_roms`, `working_roms`, `device_packs`, `diagnostics`, and `backups`.
Renaming those persisted paths would invalidate project provenance or strand existing data.
The central catalog in `src/romverse/ui/vocabulary.py` resolves previous display labels to
their canonical name so older help text and future migrations remain understandable.

## Navigation paths

- Command Deck → ROM Studio → Genesis Sequence
- Command Deck → ROM Studio → Architect Mode → Partition Atlas
- Command Deck → ROM Studio → Architect Mode → Recipe Forge
- Command Deck → ROM Studio → Forge Control
- Command Deck → Device Atlas → compatible Device Pack evidence
- Command Deck → Quantum Optimizer → System Scan → Health Timeline
- Command Deck → Activity Center → canonical source page and authoritative evidence
- Command Deck → Recovery Bay → Guardian Core review
- Command Deck → App Launchpad → Guardian Core approval
- Command Deck → Time Machine → snapshot or recovery plan
- Command Deck → Forge Arsenal → guided tool setup
- Home → ROMVERSE Link → ROMVERSE Companion
- Command Deck → ROMVERSE Galaxy
