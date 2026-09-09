# Fedora Guided synthetic Provenance boundary — 2026-09-10

## Scope and starting point

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance-approved starting commit:
  `bdcf0fa7479a8f7888ee79ab11bef6d1bb8216ab`.
- Retained corrected Fedora package executable:
  `build/fedora-asset-boundary-v2/ROMVERSE/ROMVERSE`, 6,337,072 bytes, SHA-256
  `4fbfed3244d93ba535413151c26f5fe53ef526d402f638a5e81e662f8b562500`.
- One fresh private disposable root was created at
  `/tmp/romverse-linux-synthetic-provenance-7pxGvw`, mode `0700`. Its process-local
  `PATH` was the empty directory under that root. Guided mode and completed onboarding were
  preselected only to begin at the approved Command Deck boundary. Online intelligence,
  community research, automatic verified-tool acquisition and Synapse contributions were false;
  reduced motion was true. The mode-`0600`, 675-byte settings file has SHA-256
  `363084acf36a0d7388fec95d84cfb57434b6c870270924fe36633b3811583b53`.
- The package ran under Bubblewrap `--unshare-net`. The application network namespace was
  `net:[4026533563]`, distinct from Build's `net:[4026531833]`, and its only interface was
  loopback with zero received and transmitted bytes. No phone, emulator, simulated Android
  device or Android tool was exposed to the application.

## Deterministic harmless source

Build created one inert ZIP fixture solely for this journey. It was stored, not compressed, with
fixed `1980-01-01 00:00` ZIP member timestamps and no extended attributes. The source was mode
`0400`, 551 bytes, SHA-256
`c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`.

| Member | Size | SHA-256 | Purpose |
| --- | ---: | --- | --- |
| `payload.bin` | 40 bytes | `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237` | Inert text beginning with the OTA payload magic; it is not flashable firmware. |
| `META-INF/com/android/metadata` | 257 bytes | `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de` | Bounded synthetic A/B OTA metadata for codename `romverse_synthetic`, Android 17, build 100 and security patch `2026-09-05`. |

The two members total 297 uncompressed bytes. No real firmware, partition image, executable tool,
script or device command was present.

## Genuine Guided journey

The packaged application opened on Command Deck with **DEVICE: NOT CONNECTED • PROJECT: NONE •
MISSION: IDLE • GUARDIAN: VERIFY REQUIRED**. Build then used only the visible application UI:

1. **Build ROM: Create Project** opened the ROM Studio Genesis handoff.
2. **Continue Genesis Sequence** opened task 1 of the normal 15-task route.
3. **Create ROM project** and the normal project dialog created **Synthetic Provenance Boundary**,
   project ID `synthetic-provenance-boundary-46fe128b`.
4. Genesis advanced to **Load the untouched firmware**. **Choose firmware…** opened the native
   chooser and selected only the deterministic fixture.
5. The existing protected-import disclosure stated that ROMVERSE would copy, hash, protect and
   inspect the 551-byte source without modifying or extracting it. Build accepted that exact local
   import.
6. Import and bounded inspection completed. Genesis advanced to task 4, **Prepare an isolated
   working tree**, with 3 of 15 tasks verified. Build did not invoke that action.
7. The product-owned Genesis **Save & exit** control closed the Guided dialog and returned to ROM
   Studio at the exact saved task-4 handoff. No build or phone action started.

This is the authorized stop after protected intake and Provenance and before Working Lab creation
or extraction. There was no circular handoff or dead end in the exercised route.

## Persisted evidence at the stop boundary

- Source after the journey: mode `0400`, 551 bytes, unchanged SHA-256 `c3f5c171…89c8`.
- Protected original:
  `original_roms/c3f5c1711d648a0f-romverse-synthetic-ota.zip`, mode `0444`, 551 bytes,
  byte-identical SHA-256 `c3f5c171…89c8`.
- Project manifest: 690 bytes, SHA-256
  `57a7ac1df8bfb70df24f52c1e659b2d7432c5c9b7ad9eac8bbbd09c889a02b24`; it binds the exact
  original name, size, source digest and protected relative path, with an empty Device Pack ID.
- Inspection record: 822 bytes, SHA-256
  `a492711abd378d7298113a3f851000f732fae5370e14e3a10977f3162f556edd`; complete ZIP inspection,
  exactly two entries / 297 uncompressed bytes, the metadata and OTA-payload signals, and no unsafe
  path, link, encryption or extreme-compression warning.
- Device DNA: 12,922 bytes, SHA-256
  `9551c6ac78cf7525292dfbdc84a6bd1570f68b733f4d75324a027a8dac05d8a0`. No live device identity
  exists. Firmware detection and Payload Atlas inspection planning are supported from bounded
  structure only; ROM build and `guardian_flash` remain `UNCONFIRMED`; bootloader relocking remains
  `UNSUPPORTED`, with `bootloader_relock_permitted: false`.
- Compatibility Matrix: 9,877 bytes, SHA-256
  `d0dbff34afa346673e35cb14a8f7883d5835728967da13ff8f6b3389eb05bff1`. Every decision has
  `proven_compatible: false`; Guardian flash is **Unknown**, relocking is **Known Incompatible**,
  `guardian_advisory_only` is true, community telemetry was not used and relocking is false.
- Guided mission: 439 bytes, SHA-256
  `eafa3f56c01e38ededde0f9bdceca8666dfda399d567c9081bb3e22cc7696018`; selected task is
  `workspace`, `install_requested` and `build_plan_verified` are false, and no error is recorded.
- Advisory Ascension route: 1,537 bytes, SHA-256
  `1f1c68f52e886b691f7a78659960ab0d152dad74385baf8d97aeff24d0d71e96`; state blocked,
  execution authority `none`, empty command manifest, phone unchanged, local preparation false and
  bootloader relocking not allowed. This derived advisory is not consequence authority.
- `working_roms` contained zero files. `tools` contained zero files. There was no install plan,
  device evidence, Guardian ledger, Recovery incident/result, consent or execution record.
- The packaged 880,760-byte offline archive was created locally with SHA-256
  `2384ebb6ce9616af2270991da2c7b594d08b7534e71bf819549c92c091e27764`; it was not refreshed from
  the network. Workspace initialization also generated a local ROMVERSE Link certificate and
  mode-`0600` private key; neither was opened, transmitted or used as authority.

Normal local evidence logging was not hidden: Activity contains one success record for the exact
protected firmware import. Live Console contains eight local status/evidence events covering the
Genesis start/save handoffs, ROM Studio import, Device DNA and Compatibility Matrix; none grants
Guardian or execution authority.

## Exit and limitations

The product-owned Genesis dialog close succeeded, but Fedora accessibility still exposes no
compositor-owned main-window close action. After all evidence was read, Build verified the exact
package executable and sent only that disposable process `SIGTERM`; the application and Bubblewrap
wrapper stopped. Signal 15 corresponds to status 143, and the runtime guard contains only its start
marker. This is not represented as a crash, clean application shutdown or restart-persistence
test. Repetitive Qt AT-SPI and GTK icon-theme diagnostics were visible during accessibility-driven
automation but did not prevent the approved journey; no deterministic Stage 1 application defect
was reproduced.

No source or package bit changed, so the existing non-overlapping **56/56** package/knowledge
baseline was not rerun or double-counted. This checkpoint adds one genuine Fedora packaged runtime
acceptance journey, not Android hardware verification.

## External-action and gate statement

The only writes outside Git documentation were the private disposable fixture/profile/workspace
records described above. GNOME toolkit accessibility was temporarily enabled for UI observation
and restored to false after the exact process stopped. No network request, download, catalog/tool
acquisition, installation, real firmware, phone/emulator access, ADB/Fastboot invocation, APK or
firmware mutation, Working Lab/extraction, build, Guardian/Recovery execution, flash, wipe,
unlock/root, bootloader lock/relock, signing, publication, release, hosted CI or Forgejo Action
occurred. The corrected package remains unsigned and unreleased. v0.2 Golden Foundation and every
physical/consequential/release gate remain closed.
