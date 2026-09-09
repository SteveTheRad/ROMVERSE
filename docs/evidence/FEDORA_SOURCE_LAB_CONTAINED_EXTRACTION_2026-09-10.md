# Fedora Source Lab contained synthetic extraction — 2026-09-10

## Scope and preflight

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance authorization:
  `3bddd502bb9a4057d0c6e0426c58012f85963aa5`.
- Application/test/package bits were unchanged. Build reused the approved unsigned package at
  `build/fedora-readiness-wording-f069610/ROMVERSE`; its mode-`0755`, 6,337,408-byte executable
  remained SHA-256 `d110771c730b45695413c0606de072f9c560550c88ae223913ca1fd1e5e670e4`.
- Fresh private disposable root: `/tmp/romverse-linux-contained-extract-KY85ku`, mode `0700`, copied
  from the retained approved **History Refresh Acceptance** profile/project. Only the copied
  settings workspace path changed; Guided/offline/community/download/contribution controls stayed
  in their approved state.
- Before launch, the 551-byte protected original, working baseline and automatic snapshot were
  byte-identical at SHA-256
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`. The original
  551-byte external fixture was independently rechecked at the same digest before the copy.
- The project working tree contained zero files. Its strict tree index and build plan were absent;
  Guided state was `workspace`, `install_requested` and `build_plan_verified` were false, and
  `last_error` was empty. Tools contained zero files.
- Independent ZIP inspection permitted exactly two inert members: `META-INF/com/android/metadata`,
  257 bytes, SHA-256 `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de`;
  and `payload.bin`, a 40-byte non-flashable marker, SHA-256
  `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237`.

## One contained extraction

- The existing package launched once under Bubblewrap `--unshare-net`, a private minimal `/dev`,
  read-only host root, writable disposable profile, private temporary directory and empty
  process-local Android-tool `PATH`.
- Host network namespace was `net:[4026531833]`; package namespace was distinct at
  `net:[4026533562]`. Its only interface was loopback with zero receive/transmit bytes and packets.
- The exact accessible **Open ROM Studio** action produced a genuinely visible/showing ROM Studio
  page. Pre-action Source Lab showed 6/8 steps complete, the tree and plan explicitly missing, and
  **Next: Extract and verify working tree**.
- Build invoked exactly one visible/showing existing Source Lab `Prepare safe tree` button—the UI
  control implementing that named extraction action. No other project action was invoked.
- The action completed once with **Safe extraction complete in the isolated working tree.** No
  retry, repeat, cleanup or reset occurred.

## Exact durable result

- The contained tree resolves beneath
  `working_roms/history-refresh-acceptance-7b4eca34/tree`; no tree member is a symlink.
- Exactly two files exist, totaling 297 bytes:
  - `META-INF/com/android/metadata`: mode `0600`, 257 bytes, SHA-256
    `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de`;
  - `payload.bin`: mode `0600`, 40 bytes, SHA-256
    `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237`.
- Strict `working-tree-index.romverse` is 518 bytes at SHA-256
  `8aab1ce6c83ba64774086b289e03c55ada45d138f12e8e1883cb0f7d1480b557`. It binds schema 1,
  exact project ID, contained relative tree path, exact source SHA-256, file count 2, total bytes
  297 and only `payload.bin` as a notable image. Its internal record digest is
  `d13819dc4f8b357031032bdf9831f698bc4ea16457446d8847f463663c3ec548`.
- Source/baseline/snapshot remained immutable and byte-identical at SHA-256 `c3f5c171…89c8`.
  Project manifest `56026d52…4adf6c`, working-copy record `96c478c6…4cb4a` and inspection
  `2158422a…dddf2` also remained byte-identical to approved pre-action evidence.
- Automatic Project Vault entry `20260909T225219-25c1c708` is 3,289 bytes at SHA-256
  `aeeeaf773237e8ed118f5a961810feaa7abd19d4dcdc60d7687b0c600263465b`. It is labelled
  **Extracted project tree**, has parent baseline entry `20260909T221648-94757d12`, binds the exact
  project/source/context evidence, and stores only the two exact member objects totaling 297 bytes.
  It grants no device or execution authority.
- Activity now contains five retained records: the previous three plus one firmware-extraction
  success and one automatic Project Vault success. Live Console contains 16 records: the previous
  12 plus running/succeeded extraction and Vault events. No result was inferred from progress.
- Guided state remains `workspace`; `install_requested` and `build_plan_verified` remain false and
  `last_error` remains empty. No build plan exists and tools remain empty.
- The visible Source Lab state became 7/8 steps complete with **Next: Create and verify build plan**.
  It truthfully shows the working tree, 2-file/297-byte inventory and only the Guardian-assessed
  build plan as missing. Build stopped without invoking that next action.

Fedora accessibility exposed no compositor-owned application close action. Build verified and sent
`SIGTERM` only to the exact disposable ROMVERSE process; Bubblewrap returned exact status 143.
No clean-shutdown or restart-persistence claim is made. GNOME toolkit accessibility was restored
to false and no ROMVERSE process remained.

## Classification, gates and external actions

- **Implemented:** no new application behavior; this is runtime evidence and handoff only.
- **Simulated/Tested:** one genuine Fedora no-network/no-phone package acceptance of the exact
  synthetic contained-extraction boundary. Per authorization, no unchanged automated test rerun
  and no package rebuild occurred.
- **Hardware Verified:** no phone, emulator or Android simulation was used.
- **Released:** no. The existing development package remains unsigned, uninstalled and unpublished.
- Guardian/Recovery/safety: exact-source containment and automatic local history are verified; all
  evidence remains local and authority-free. Guardian-only authority, durable `UNKNOWN`, no blind
  retry, independent verification and permanent bootloader no-relock are unchanged.
- Feature freeze: compliant. No source/test/feature change occurred.
- Version gate: contained synthetic extraction is ready for Product Assurance review. Build
  planning and every device/consequence/signing/publication/release gate remain **CLOSED**.
- External actions were limited to read-only preflight; a fresh private retained-state copy; one
  no-network package launch; exact ROM Studio navigation; exactly one inert Source Lab extraction;
  expected strict index/local activity/history writes; exact process termination; scoped evidence
  and handoff commits; and planned Forgejo-first/GitHub branch synchronization. No import,
  working-copy repeat, build planning/build, network/tool acquisition, phone/emulator, real
  firmware, ADB/Fastboot, firmware/APK mutation, Guardian/Recovery execution, flash, wipe,
  unlock/root, lock/relock, signing, installation, publication, release or hosted CI occurred.

## Product Assurance review requested

Approve the exact contained synthetic extraction and its automatic evidence. Keep build planning
and every later Stage 1/release boundary closed until separately authorized.
