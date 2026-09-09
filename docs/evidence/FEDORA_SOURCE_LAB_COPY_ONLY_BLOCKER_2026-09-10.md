# Fedora Source Lab copy-only blocker — 2026-09-10

## Verdict

The exact ROM Studio Source Lab **Create working copy** action created the correct contained
baseline and did not extract the ZIP. It also automatically created a Time Machine snapshot and a
Project Vault checkpoint. Product Assurance explicitly required baseline plus working-copy record
only, with no Time Machine/Project Vault artifacts. The corrected acceptance is therefore
**blocked**, not passed.

Build followed the authorized failure rule: it preserved the exact state, made no retry, cleanup,
reset or source change, and stopped for Product Assurance. This run does not approve the automatic
history side effects or any later Working Lab stage.

## Starting boundary

- Branch: `linux/stage1-desktop-readiness`.
- Product Assurance correction:
  `30305406f9d1573fac1e843cdb26007890e3b0f8`.
- Fresh private root: `/tmp/romverse-linux-source-lab-copy-6mNksR`, mode `0700`.
- Fresh project: **Synthetic Source Lab Copy**, ID
  `synthetic-source-lab-copy-83d60f6b`.
- Retained corrected package executable: 6,337,072 bytes, SHA-256
  `4fbfed3244d93ba535413151c26f5fe53ef526d402f638a5e81e662f8b562500`.
- The mode-`0600`, 670-byte settings file has SHA-256
  `53fea438d793202ebb215aecfa4b4c37b2d97edc80727c61c64231c9a3e1b2c2` and retained Guided
  mode with all online/community/download/contribution controls false. The process-local Android
  tool `PATH` was empty.
- The fixture was a byte-identical copy of the previously approved harmless 551-byte ZIP, mode
  `0400`, SHA-256
  `c3f5c1711d648a0f6c8f2ba2e3c910048c4e81e6f3ee39bb82e9e85888ac89c8`.
- Bubblewrap `--unshare-net` provided a network namespace distinct from Build's, with only
  zero-byte loopback. No phone, emulator or simulated Android device was exposed.
- The earlier advanced scope-divergence project remained untouched. Its eight project-record hashes
  and three working-file hashes were revalidated byte-for-byte before and after this run.

## Exact UI journey

1. From the fresh Command Deck, Build used **Build ROM: Create Project**, the normal Genesis entry,
   and **Create ROM project** to create the new disposable project.
2. Genesis **Choose firmware…** selected only the same harmless fixture. The existing protected
   intake disclosure was accepted. Import and bounded Provenance inspection completed normally.
3. Genesis reached task 4 of 15 with 3 tasks verified. Build invoked **Save & exit** and did not use
   **Resume Mission** or **Prepare working lab**.
4. Pre-action inspection proved the new project's `working_roms`, `time_machine` and `tools`
   locations contained zero files; the mission remained saved at `workspace` and the source and
   protected original matched exactly.
5. From ROM Studio Source Lab, Build located one accessible **Create working copy** button and
   invoked it exactly once.

No second action, extraction control, retry or Genesis advancement occurred.

## Correct copy result

- Contained writable baseline:
  `working_roms/synthetic-source-lab-copy-83d60f6b/original-baseline.bin`, mode `0644` inside the
  private root, 551 bytes, SHA-256 `c3f5c171…89c8`.
- `working-copy.romverse`: 583 bytes, SHA-256
  `50a715de67fc31385e380abf24f1df9861377b66e4ebb0bc8e75a2313942d4fb`. It binds the exact
  project ID, contained relative path, size 551 and identical source/current SHA-256.
- The mode-`0400` fixture and mode-`0444` protected original stayed byte-identical, 551 bytes and
  SHA-256 `c3f5c171…89c8`.
- The project manifest, bounded inspection, Device DNA, Compatibility Matrix and advisory
  Ascension route remained source-derived and execution-authority-free. The mission stayed saved at
  task 4 `workspace`, with no build plan, install request or error.
- The working tree has zero files. `working-tree-index.romverse` is absent. `tools` has zero files.
  No extraction, Payload Dumper, build plan, device scan/evidence, Guardian ledger, Recovery
  incident/result, consent or execution record exists.

## Disallowed automatic history result

The same single Source Lab completion automatically created six Time Machine/Project Vault files:

- snapshot bytes `20260909T214826-a9a671.bin`: 551 bytes, SHA-256 `c3f5c171…89c8`;
- snapshot receipt: 545 bytes, SHA-256
  `a55df861d3bb154d5305c122d9b4c60d2acfd465748eb4e8bbcb1262327af72f`;
- Project Vault entry `20260909T214826-c383526d`: 2,619 bytes, SHA-256
  `fe7c1f9651e66d5d39c295a7f28c4edb050dbf85ee77f4d0d5c7655aab1a964e`;
- three content-addressed Vault context objects matching the project, inspection and Device DNA
  record hashes.

The Vault entry is labelled **Protected working baseline**, has zero tree files/bytes, and states
that it was automatically preserved after ROM Studio reported working-copy completion. Read-only
source inspection confirmed that every completed ROM Studio operation calls the shared automatic
`capture_operation_checkpoint`, and `working-copy` is explicitly mapped to this baseline capture.
The result is deterministic current product behavior, not an ambiguous or delayed write.

Activity contains three records: protected import, working-copy success and automatic Project Vault
success. Live Console contains 12 records: the import/Provenance/Genesis events plus working-copy
and Project Vault running/success events. These are local evidence, not device Recovery or execution
authority.

The visible Source Lab status was also internally inconsistent with retained evidence: it reported
**Working copy ready** and correctly showed **Next: Extract and verify working tree**, but said
**No snapshots yet** despite the automatic snapshot/Vault artifacts. No UI action was taken in
response because the authorization required an immediate stop on extra behavior.

## Exit, tests and external actions

Fedora accessibility still exposed no compositor-owned main-window close action. After evidence
inspection Build verified the exact package process and sent only it `SIGTERM`; Bubblewrap returned
exact status 143. The runtime guard contains one start marker and no clean-close marker. No clean
shutdown or restart-persistence claim is made. GNOME toolkit accessibility was restored to false.

No source/test/package change, rebuild or automated test occurred. The earlier **56/56** focused
package/knowledge baseline remains prior evidence and is not counted again. This run provides one
blocked packaged Fedora Source Lab acceptance, no hardware verification and no release evidence.

External actions were limited to creating the new private profile and byte-identical harmless
fixture copy; one isolated package launch; normal project creation/import/Provenance and Genesis
**Save & exit**; exactly one Source Lab **Create working copy** action; the resulting contained
baseline and automatic local history/evidence writes; exact process termination; read-only
source/Git inspection; and this documentation. No network request, real firmware, extraction,
retry, tool/download/install, phone/emulator, ADB/Fastboot, APK/firmware mutation, build plan/build,
Guardian/Recovery execution, flash, wipe, unlock/root, bootloader lock/relock, signing,
publication, release, hosted CI or Forgejo Action occurred.

## Product Assurance decision requested

1. Decide whether automatic recoverable Time Machine protection is an intentional required part of
   working-copy creation and the acceptance criterion should be corrected, or whether the Source
   Lab action must stop before automatic history capture.
2. Independently review the mismatch between the visible **No snapshots yet** status and the
   retained automatic snapshot/Vault evidence.
3. Keep extraction, build, device/consequential, signing, publication and release gates closed.
