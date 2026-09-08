# ROMVERSE Product Assurance Sync

## Authoritative checkpoint

- Product Assurance base: `d6930827a3dd679b1a460a7ab6e58975be6ac420`.
- Tested implementation commit: `538992bb5cbd5f54edd828a6116aaf0de8041fe3` —
  `Add read-only external firmware intake`.
- Final handoff checkpoint: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, bounded no-phone packaged Fedora firmware intake.
- Working tree at handoff: clean apart from ignored local build/package output. No protected
  Companion file or Windows launcher draft was edited, staged, discarded, or committed.

## Exact implementation change

The approved packaged build exposed one concrete Stage 1 dead end: its only firmware intake action
required copying a selected package into `Original ROMs`. That could not complete the requested
read-only, select-in-place evidence intake of the existing 11.8 GB firmware.

The minimum correction is:

- `src/romverse/rom/external_intake.py` adds a strict project-bound external-intake receipt and
  service. It opens one external regular file read-only with no-follow semantics, SHA-256 hashes it
  in place, performs the existing bounded container inspection, checks file identity before/during/
  after reading, and durably verifies the sealed receipt.
- `src/romverse/ui/rom_studio.py` adds `Inspect firmware in place…`. ROM Studio presents the exact
  file/hash/container evidence and a useful read-only reinspection action while explicitly showing
  `guardian_flash: UNCONFIRMED`, Compatibility Matrix `Unknown`, protected source `NO`, and
  build/install/flash `LOCKED`.
- `tests/test_external_firmware_intake.py` covers no-copy/no-authority intake, source drift,
  strict hidden-field rejection including a relock command, locked UI state, and durable reload.

The receipt is evidence only. It cannot become a protected original, Device Pack match, build input,
live-target record, Guardian approval, consent, or execution authority. Existing deliberate protected
import remains available as a separate later user action. Bootloader relocking remains `never`.

## Corrective Fedora development artifact

- Artifact:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-fedora44-x86_64-538992b-unsigned-internal.zip`.
- Classification: unsigned internal development build; not signed, published, released, installed,
  or a release candidate.
- Archive: 460 regular members, 360,273,850 expanded bytes, 150,967,232 archive bytes, mode 0644.
- Archive SHA-256:
  `0fbad2926c2671938877024a8149da193cb51d0041c54db4e2da878e28fa3633`.
- Packaged executable SHA-256:
  `531c9858381c1aab8b7de570e5d6eb1d88321c30db3bd62e2589c294f11f33ca`.
- Built once from `538992b` with Python 3.14.7, PyInstaller 6.22.2 and PySide6 6.11.2 on
  Fedora Linux 44 x86-64, kernel 7.1.13.
- The ignored local artifact was not added to Git and is not being uploaded or published.

## Real packaged read-only intake evidence

One disposable root was reused for the entire checkpoint:
`/tmp/romverse-fedora-intake-EjkSzf`. The corrected archive was extracted once beneath that root and
the packaged executable was launched against its existing disposable workspace/configuration.

The exact existing source was selected in place:

- Name: `adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip`.
- Size: 11,797,532,065 bytes.
- SHA-256: `adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a`.
- Source identity before and after: device 66309, inode 94371893, size 11,797,532,065,
  modification epoch 1788490471, mode 0444 — unchanged.
- Actual bounded result: ZIP, 68 entries, 11,797,511,667 expanded metadata bytes; partition
  signals `boot`, `dtbo`, `init_boot`, `recovery`, `super`, `vbmeta`, and `vendor_boot`; zero critical
  and zero warning findings.
- Identity result: `Unclassified ZIP firmware container`, confidence `unknown`; no exact device,
  build, channel, region, Device Pack, compatibility, or upgrade relationship was inferred.
- Durable receipt SHA-256:
  `cc70f4f602d6d3a94156d02c75b0d5a13e1495e17e4bf7eefe112fa19886cfb8`.
- Project manifest remained `original: null`; the disposable workspace contains no copied original.
  The firmware was not copied, extracted, altered, built, signed, executed, or sent to a device.

The packaged UI visibly reported:

- `READ-ONLY SOURCE EVIDENCE • RELATIONSHIP UNCONFIRMED`;
- the full exact source SHA-256 and `no workspace copy`;
- `guardian_flash • UNCONFIRMED` and Compatibility Matrix `Unknown`;
- evidence-only authority, phone changed `NO`, build/install/flash `LOCKED`, and relock `NEVER`;
- `Reinspect external firmware in place` as the next available read-only source action.

The consequential source/build controls `Verify integrity`, `Inspect structure`, `Create working
copy`, `Prepare safe tree`, `Plan build (dry-run)`, `Forge Bundle`, and `New recipe` were all disabled.
The exact packaged executable then closed cleanly, restarted against the same disposable workspace,
reloaded the identical receipt/full SHA/unknown state, kept all seven controls disabled, and closed
cleanly again.

The native GTK chooser could not be deterministically driven to an absolute file under the test
host's accessibility automation: it returned the current Desktop directory and ROMVERSE correctly
failed closed with `External firmware must be a regular file`. For the accepted intake, the harness
passed the exact selected path to the same packaged ROM Studio external-intake worker that the chooser
calls. No source/service/receipt logic was replaced or mocked. This automation limitation and the
expected safe rejection are not counted as a product regression. An earlier debugger probe without
the Python GIL also terminated one pre-intake disposable launch; it created no receipt and did not
touch the firmware. Both harness events remain transparently present in the disposable runtime log.

## Verification and regression evidence

- Focused affected regression: **10/10 unique tests passed**.
- Static check: Ruff passed for all three changed implementation/test files.
- Patch hygiene: `git diff --check` passed.
- Package build: **1/1** corrective build completed.
- Bundle verification: **1/1** archive passed member-boundary, CRC, executable-presence, size, and
  SHA-256 verification.
- Accepted actual packaged intake: **1/1** completed against the real 11.8 GB source.
- Durable restart/reload: **1/1** passed.
- Locked consequential controls after intake and restart: **7/7** disabled each time.
- Source identity/hash preservation: **1/1** exact pre/post match.
- A preliminary test command used two wrong test paths and another omitted current-source
  `PYTHONPATH`; both stopped during collection and exercised no product code. They are corrected and
  excluded from the 10-test non-double-counted result.
- No broad/full suite was run, as the approved verdict required focused regression and at most one
  corrective rebuild.

## Classification

- **Implemented:** strict external read-only firmware evidence receipt/service and locked ROM Studio
  presentation/reinspection path.
- **Simulated/Tested:** unit/UI fixtures plus one actual packaged Fedora intake of the existing real
  firmware package and one durable restart. The firmware contents were observed read-only; no phone
  or firmware execution was simulated.
- **Hardware Verified:** no. ADB and Fastboot both reported no target at the final check.
- **Released:** no. The artifact is unsigned, local, ignored by Git, and unpublished.

## Blockers, friction, and remaining limits

- No product blocker or looping Guided dead end remains inside this bounded external-evidence intake.
- The native file chooser automation limitation described above remains a test-harness limitation;
  normal human selection was not independently accessibility-automated in this checkpoint.
- External evidence deliberately does not unlock import, build, Device DNA matching, compatibility,
  Guardian, consent, Recovery, or execution. A later reviewed workflow must deliberately establish
  each boundary.
- Full Linux regression, another Linux host, Windows, a physical phone, and production Recovery
  execution were not exercised here.
- The v0.2 Golden Foundation gate remains **CLOSED**.

## Guardian, Recovery, and safety impact

- Missing exact source/device execution evidence remains `UNCONFIRMED`/`Unknown`, never falsely
  incompatible and never approved.
- Exact-device authority, Guardian-only execution, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery attribution, independent verification, and permanent no-relock are unchanged.
- This slice creates no Recovery incident, preparation, live target, consent, execution journal, or
  durable device result.

## Platform and freeze status

- Fedora/Linux: genuinely built, packaged, launched, interacted with, closed, and restarted on the
  Fedora 44 x86-64 host.
- Windows: not tested or claimed by this checkpoint.
- Android hardware: no target connected or used.
- Feature freeze: compliant. This is the Product Assurance-authorized minimum Stage 1 correctness
  repair for an observed packaged intake dead end, not new product scope or execution capability.

## External actions

- Physical phone operation, ADB/Fastboot target use, APK installation, firmware copy/extraction/
  mutation/build/sign/execute, system-wide package installation, publication, release, and force-push:
  **none**.
- Network use by the application during this slice: none required or claimed.
- Remote action after verification: one normal push of the scoped commits to the existing
  `linux/stage1-desktop-readiness` branch only.

## Next proposed Build task

Stop at this committed checkpoint for Product Assurance. Do not begin another consequential slice.
After review, continue only the exact Stage 1 direction approved in `docs/sync/PRODUCT-ASSURANCE.md`.

## Product Assurance Review Requested

- Confirm the narrow external-evidence correction is feature-freeze compliant and preserves the
  separation between evidence and authority.
- Review the real package/hash/unknown-state/locked-control/restart evidence.
- Confirm whether the transparent native-chooser automation limitation is acceptable for this
  checkpoint or requires a future human-driven UI acceptance check; it did not alter the verified
  service, receipt, or safety result.
