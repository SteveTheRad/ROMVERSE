# Rebuilt ROM installation checkpoint — 2026-09-05

This increment connects an exact local ROM build to the complete understood
installation procedure, retaining the rebuilt images instead of silently
installing the protected original. It is development/simulation evidence, not
physical flashing compatibility, OEM trust, universal support or release approval.

## Implemented path

1. Select the rebuilt OTA project and its base installation package. An existing
   package can be selected in place, or a user-selected ZIP can be protected in
   the background. An identical already-imported source is reused. Importing is
   not a compatibility verdict and does not execute package scripts.
2. `BaseImageCompatibilityService` freshly hashes the complete protected OTA,
   payload and source procedure and compares all 48 unchanged image identities.
   Bounded full-payload metadata parsing rejects ambiguous, malformed, partial
   and unsupported delta evidence. Saved metadata carries no execution authority.
3. `CandidateAvbService` binds the current build/tree/Recipe/pack/toolchain to
   actual root signatures, child descriptors, source image footers, partition
   content and stored Merkle trees. Existing build-pinned AVBTool versions can
   be inspected read-only even after the active tool changes. Self-consistent
   embedded signatures are not independently established publisher trust.
4. `CandidateInstallationService` composes exactly **2 rebuilt + 48 base images**.
   Rebuilt `super` and `vbmeta_system` replace those two source roles. Rebuilt
   `product` is already inside super, not an extra physical write. Source-declared
   order, slot actions and explicit wipe/reboot choices are preserved.
5. The shared installation executor privately stages and verifies both origins
   before the first changing command. Missing or changed rebuilt bytes never
   fall back to the archive's old images. Existing exact-target checks, device
   command coordination, exact-plan consent, safe Stop boundaries and uncertain
   failure handling remain in place. No unlock, relock or AVB-disable flags are
   added.
6. Distinct candidate journals seal portable composition provenance, both
   source identities, all image origins and the measured results. Reopening
   history remains read-only and is bound to the build project and exact phone.
   Installation, readback, boot/stability and subsystem health remain separate.

The desktop preparation entry exposes the complete rebuilt route alongside the
explicit protected-package and manually mapped subset routes. It uses background
workers and in-place failure messages, with a scrollable body and persistent
action buttons. A missing/stale project during base selection is contained and
does not leave Verify or Cancel disabled. Wording now says **No data erase
requested**, not that data will necessarily be preserved.

## Real-archive read-only verification

The production base verifier passed against these existing protected files in
**27.444 seconds**. This checked both complete archives, the complete OTA payload,
all 50 procedure images and the 48 unchanged comparisons (857,538,560 bytes),
with no mismatches:

| Input | Freshly verified SHA-256 |
| --- | --- |
| `.23` OTA archive | `a58f2f3b876283d88031acbb18859b6b8a19212d9c214d4dc06c6ceb01d45c55` |
| OTA payload | `b614dabafabff794177e24f5ae3f3ef251043527122f2b6e4da535d6473155c4` |
| Custom base ZIP | `adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a` |
| Understood source script | `589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac` |
| Payload header + manifest | `c710c43f9851227bae4be196340dd29a516889b4d500a2e158d0b1d3b636ca5a` |

The current real workspace contains a `.32` project, not an active `.23` project.
The check therefore used explicitly transient in-memory project metadata while
retaining real protected-path checks. No project IDs or receipts were saved;
this is not verification of the user's current `.32` build. Source inode, size,
mtime/ctime and permissions, plus project directory entries/metadata, were
unchanged. No extraction, phone command or workspace write occurred.

The actual `.23` top-level AVB image also passed bounded parsing and embedded-key
RSA signature verification: SHA
`69c245f4a82a610125bb4563a1476aa299ac9bf4e8197f6bf88e21de54c271d4`,
SHA256_RSA4096, flags zero and `vbmeta_system` chain rollback location 2. The
rebuilt unsigned child does **not** possess the root's delegated signing key;
this remains an explicitly local unlocked experimental route, not an OEM-trusted
chain or a claim that the device will accept it.

## Verification evidence and limits

- 103 base-verifier cases, 60 AVB cases, 21 composition cases, 55 mixed-origin
  runtime/history cases and 14 cross-service integration cases are implemented.
  Cross-service tests use real Source/Base/Build/AVB/Composition/transport
  services with test-generated RSA and Merkle bytes. Filesystem/super tools and
  the phone remain explicitly inert simulations; no service success is treated
  as a physical boot proof.
- The 32 composition/preparation-UI cases passed together after the stale-project
  error-containment fix. Separate runtime/history/boot/source integration passed
  237 cases. These selections overlap; they are not additive suite totals.
- Final new-feature selection: **267 passed** across all eight new test files.
  Broader candidate/source/project/boot regression selection: **569 passed in
  61.88 seconds**. The complete application regression run is still in progress
  at this checkpoint. All eight new suites are selected for Windows CI, but
  Windows execution has not occurred here. Only genuinely unavailable Windows
  symlink creation and POSIX-only permission assertions receive platform guards.
- A real Qt managed-worker walkthrough prepared and reviewed the candidate,
  declined with zero phone-changing commands, then completed all 53 actions and
  50 exact image writes through inert transport. Screenshots were visually
  reviewed for preparation, review, completion with boot unverified, and saved
  history. Historical reopening had no command capability and issued no commands.
- AVB Merkle verification was independently checked against installed AOSP
  avbtool-generated multi-level SHA1/SHA256/SHA512 test images. These are temporary
  synthetic images, not firmware extracted from the user's phone.
- Current full-suite, packaging and supported-platform results must be recorded
  separately; the previous 2,398-test packaged source-installation checkpoint
  does not certify this newer code. No current application replacement, APK
  installation, hardware flash or publication is claimed here.

### Isolated wheel check

A newly built wheel passed archive/index validation (293 members, 22 packs),
and all 288 packaged application/source assets were compared byte-exactly with
the current source. SHA-256:
`0a8329231476cb75de70d67c2906be7b281af49f86f38df54dc79b7084e2bbfd`.
It was installed only into a new temporary `pip --target` directory, without
dependency downloads or changes to the user's running installation.

Installed desktop smoke passed with 22 Device Packs, 170 known fixes, 281 offline
evidence records and 19 covered desktop routes, including byte-exact reopening
of a populated disposable workspace. This is wheel launch/integrity evidence;
no newly frozen desktop bundle or Windows package is claimed for this increment.

## Remaining master-goal work

The [Guided Experience Contract](ROMVERSE-GUIDED-EXPERIENCE-CONTRACT.md) is
normative. This increment does not yet implement the application-owned shared
operation session, seamless Guided/Expert switching during active work,
automatic verified remediation, compact goal-oriented presentation, complete
First Light subsystem checks or physical verification. Existing modal lifecycle
and recovery handoff are reused until that integration is implemented and tested.
All twenty master-goal stages and the approved-logo byte lock remain intact.
