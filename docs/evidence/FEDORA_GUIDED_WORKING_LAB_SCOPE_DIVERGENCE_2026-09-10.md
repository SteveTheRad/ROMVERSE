# Fedora Guided Working Lab copy-only scope divergence — 2026-09-10

## Verdict

The approved **copy-only** acceptance was **not satisfied**. Build invoked the Genesis task-level
**Prepare working lab** control once instead of the narrower ROM Studio Source Lab **Create working
copy** control. Genesis deterministically chained both `working-copy` and `extract`, advanced the
saved mission to task 5 and created automatic local Time Machine checkpoints. Build immediately
stopped further interaction, preserved the exact resulting evidence and performed no retry,
cleanup, reset or source correction.

This is a truthful blocked checkpoint. The baseline copy itself passed, but the run crossed the
explicit no-extraction acceptance boundary. It must not be represented as approval of either the
requested copy-only journey or extraction.

## Starting boundary

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance commit:
  `94b88af69beeb37b9a0f3bce9baaf72d0a45111a`.
- Previously approved checkpoint:
  `052814e3fc5bbe0a75ec39bb4a618437f2077568`.
- Retained corrected package executable: 6,337,072 bytes, SHA-256
  `4fbfed3244d93ba535413151c26f5fe53ef526d402f638a5e81e662f8b562500`.
- Same private disposable root:
  `/tmp/romverse-linux-synthetic-provenance-7pxGvw`, mode `0700`.
- Preflight revalidated the mode-`0400`, 551-byte inert source and mode-`0444`, 551-byte protected
  original as byte-identical SHA-256
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`.
  The mission was saved at `selected_stage: workspace`; `working_roms` and `tools` each contained
  zero files. No ROMVERSE process was running.
- The same Guided profile retained all online/community/download/contribution controls false and
  used the same empty process-local Android-tool `PATH`. Bubblewrap `--unshare-net` exposed only
  zero-byte loopback in an application network namespace distinct from Build's. No phone,
  emulator or simulated Android device was exposed.

## Exact UI sequence and divergence

1. The package reopened on Command Deck with the exact **Synthetic Provenance Boundary** project.
2. Build selected **Resume Mission**. Genesis reopened at task 4 of 15, **Prepare an isolated
   working tree**, with the first three tasks verified.
3. The task description explicitly said ROMVERSE “extracts supported archives or stages a
   recognized single firmware image automatically.” Its next-safe-action button was **Prepare
   working lab**. The narrower **Create working copy** control was not the Genesis CTA.
4. Build incorrectly invoked **Prepare working lab** once. No second click or retry occurred.
5. Genesis automatically completed both the working-copy and ZIP-extraction operations, recorded
   two automatic local Project Vault entries, and advanced to task 5, **Confirm device identity and
   capabilities**.
6. Build used the product-owned **Save & exit** control. ROM Studio truthfully reported:
   **Stage 5/15 • 33% verified • NO BUILD OR PHONE ACTION STARTED**.

Read-only source inspection after the run confirmed that current Genesis `prepare-workspace`
queues `working-copy` whenever the baseline is missing and then queues `extract` whenever the tree
is missing. The observed chain is therefore deterministic current behavior, not a timeout or
ambiguous result. Whether the approved acceptance should use Source Lab directly or Genesis should
expose a copy-only sub-boundary requires Product Assurance direction; Build made neither change.

## Persisted results

### Approved portion that completed

- Writable contained baseline:
  `working_roms/synthetic-provenance-boundary-46fe128b/original-baseline.bin`, mode `0644` inside
  the private workspace, 551 bytes, SHA-256 `c3f5c171…89c8`.
- `working-copy.romverse`: 591 bytes, SHA-256
  `87c2e8172279b66331eaddfda6e21d02e2dbf163e15da599cf875535426ff80a`. It binds project ID,
  relative contained path, size 551, and identical source/current SHA-256 `c3f5c171…89c8`.
- Automatic baseline snapshot: 551 bytes, SHA-256 `c3f5c171…89c8`, plus its 553-byte receipt.
- Automatic Project Vault entry `20260909T212551-0f365450` records **Protected working baseline**,
  zero tree bytes, exact project/source/inspection/Device DNA fingerprints and phone untouched.

### Out-of-scope portion that also completed automatically

- ZIP member `META-INF/com/android/metadata`: mode `0600`, 257 bytes, SHA-256
  `7b21d60b939893071ad4895c3270860ef87cd710eda6c2c203f51d256453d9de`.
- ZIP member `payload.bin`: mode `0600`, 40 inert bytes, SHA-256
  `5db7a969a06334c08958a02c13722f11a343126f781fdcbdbdf9cf05754b4237`.
- `working-tree-index.romverse`: 524 bytes, SHA-256
  `7dec2cfd6c92cdf98b01eb2310536bd33e75d513f922d35b218219efdc20919b`; exactly two files / 297
  bytes under the contained project tree and the exact protected-source digest.
- Automatic Project Vault entry `20260909T212551-fee1a93a` records **Extracted project tree**,
  parented to the baseline entry, with exact hashes for the same two inert members. No external
  Payload Dumper or other tool ran.
- The final Guided mission is task `device`, with build plan false, install requested false,
  root choice undecided and no error. No device scan was started.

The source and protected original remained unchanged at their original modes, sizes and SHA-256.
The project manifest, bounded inspection, Device DNA, Compatibility Matrix and advisory Ascension
route hashes also remained unchanged. `tools` still contains zero files. There is no build plan,
device evidence, Guardian ledger, Recovery incident/result, consent or execution record. The two
Time Machine entries are local reversible project checkpoints; their Activity category does not
make them device Recovery authority.

Activity now has five events: the prior protected-import event plus local successes for the
working copy, its Project Vault checkpoint, extraction and its Project Vault checkpoint. Live
Console now has 18 events: the prior eight plus ten deterministic running/success/save events for
this action. These logs are evidence of the scope divergence and grant no Guardian or device
authority.

## Exit, tests and external actions

The Genesis **Save & exit** action succeeded. Fedora accessibility still exposed no
compositor-owned main-window close action, so after final evidence inspection Build verified the
exact executable and sent only that process `SIGTERM`; the Bubblewrap wrapper returned exact status
143. The runtime guard has two start markers and no clean-close marker. No clean shutdown or
restart-persistence claim is made.

No source/package fix, rebuild or automated test was performed because Build stopped at the
scope divergence. The earlier **56/56** package/knowledge baseline remains prior evidence and is
not counted again. This run provides one failed copy-only acceptance with deterministic local
evidence; it provides no hardware verification and no extraction approval.

External actions were limited to the isolated packaged launch, one **Resume Mission** action, one
incorrect task-level **Prepare working lab** action, the application-created contained baseline,
two extracted inert members and local Project Vault/evidence records, **Save & exit**, exact process
termination, read-only source/Git inspection and this documentation. GNOME toolkit accessibility
was restored to false. No network request, reimport, new fixture, download/install, real firmware,
phone/emulator, ADB/Fastboot, APK/firmware mutation, tool invocation, build plan, build,
Guardian/Recovery execution, flash, wipe, unlock/root, bootloader lock/relock, signing,
publication, release, hosted CI or Forgejo Action occurred.

## Product Assurance decision requested

1. Decide whether the next acceptance should create a fresh disposable project and invoke the
   existing Source Lab **Create working copy** control directly, or whether Genesis must first gain
   a visible copy-only stop within task 4.
2. Decide the disposition of this retained disposable project, which now truthfully contains an
   extracted inert tree and local Time Machine checkpoints. Build will not delete, reset or reuse
   it across another boundary without explicit direction.
3. Keep extraction, build, device/consequential, signing, publication and release gates closed.
