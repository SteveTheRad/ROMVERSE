# ROMVERSE Build Status

## Authoritative checkpoint

- Implementation commit: `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Title: `Update Link instrumentation confirmation flow`
- Product Assurance authorization commit:
  `a015b2fdd7e7cc2c23cd1ad5f44ed8e8ddcb8f0a`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation contained Desktop-to-Companion Link integration
- Milestone result: **VERIFIED — 12 PASS / 0 FAIL / 0 SKIP**
- Scope result: the stale instrumentation interaction now follows the current visible safety-code
  confirmation path; the complete contained TLS Link journey passes without changing production
  application behavior.
- Working-tree target state: clean after the implementation commit except for this handoff update.
  The separate original checkout's three protected Companion changes and pre-existing Windows
  launcher drafts were not edited, staged, discarded, built from, or committed.

## Repository coordination

- The latest exact Linux branch and Product Assurance handoff were fetched before work.
- `docs/sync/PRODUCT-ASSURANCE.md` authorized only the bounded existing-test correction recorded
  above.
- `docs/sync/AUTONOMOUS-BUILD-PROTOCOL.md` is not present on the Linux branch. Its committed version
  at `origin/windows-launcher-authorized-work` was read directly without checking out, merging, or
  modifying Windows work. This checkpoint follows its separate-branch, scoped-commit, evidence,
  push, and mandatory-stop rules.
- Git/source truth was used as authority; no chat-to-chat injection or concurrent application-source
  editing occurred.

## Exact change

Only
`companion/app/src/androidTest/kotlin/com/radforge/romverse/companion/MainActivityInstrumentedTest.kt`
changed:

- The existing TLS Link test explicitly opens the existing Link destination.
- It populates only the existing endpoint, certificate fingerprint, and six-digit code fields.
- It proves the retired direct checkbox path remains unchecked, disabled, and non-clickable.
- It activates the existing `CONNECT WIRELESSLY` action.
- It inspects the real visible/accessibility confirmation dialog and requires its title, prompt,
  exact certificate-derived safety code, read-only encrypted-Link explanation, explicit statement
  that no flash/root/wipe/unlock/relock/command authority is granted, and visible
  `YES • CODE MATCHES` action.
- It confirms through that visible accessibility action; no reflection, private-field access,
  preference mutation, test-only production hook, or direct confirmation-state bypass is used.
- All pre-existing post-confirmation assertions remain: TLS pinning, two fresh health snapshots,
  encrypted remembered-session storage and reconnection, schema-six Live Console, Device DNA,
  Ascension, `Execution authority: NONE`, and permanent bootloader-relock prohibition.

No production Activity, navigation, transport, fixture, protocol, dependency, Gradle, asset,
Device Pack, Recovery adapter, desktop runtime, or approved logo changed.

## Build and artifact admission

The approved application source was unchanged. The instrumentation APK alone was rebuilt with the
existing offline Android/Gradle toolchain:

- Build tasks: 64 actionable; 4 executed and 60 up to date.
- Build result: successful.
- Application APK:
  `companion/app/build/outputs/apk/debug/app-debug.apk`
  - Size: 9,060,239 bytes
  - SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
  - Inventory: 874 ZIP entries
  - Result: byte-identical to the Product Assurance-approved application APK
- Instrumentation APK:
  `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
  - Size: 411,737 bytes
  - SHA-256: `5239d6d7efc4b4ce574cc3c9c84cc62783c8e22bfccee306921108711949df5c`
  - Inventory: 9 ZIP entries; ZIP integrity passed
  - Package: `com.radforge.romverse.companion.test`
  - Minimum / target / compile SDK: 26 / 35 / 35
  - Debuggable AndroidJUnitRunner package targeting the Companion application
  - Signer: one Android Debug RSA-2048 certificate
  - Certificate SHA-256:
    `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
  - APK signature: v2 verified; v1, v3, v3.1, v4, and source stamp absent

Both hashes were revalidated immediately before emulator installation. No artifact was installed
on a phone or host system.

## Contained runtime admission

- Host: Fedora Linux with SELinux Enforcing and unchanged.
- Existing clean AVD: `romverse_api35_clean`, Android 15 / API 35 / x86-64, Pixel 7 profile.
- Launch: one visible host-GPU emulator, wiped data, snapshots disabled, no audio, no metrics.
- Sole admitted target: `emulator-5556:device`.
- Guest admission: `sys.boot_completed=1` and `ro.kernel.qemu=1`.
- No physical, simultaneous, ambiguous, unauthorized, or changing Android target appeared.
- Existing verified interpreter:
  `/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/source/.venv/bin/python`
- Python 3.14.7 with `PYTHONNOUSERSITE=1`; `cryptography` 46.0.7 came from that existing
  environment, while all ROMVERSE modules resolved only from this clean Linux worktree.
- No package or environment was installed, removed, upgraded, downgraded, or mutated.

The committed fixture used one ephemeral TLS identity and reported:

- State order: `ready` → `approved` → `first-health-snapshot` → `complete`.
- Certificate SHA-256:
  `d3b34103b3fd66d5f8e0b22f45bd548136375f6c3cb4bf7bb89b5ea2d61d4da1`
- Exact displayed safety code: `D3B3-4103-B3FD-66D5-F8E0-B22F`.
- Model: `sdk_gphone64_x86_64`.
- Final health: `OPTIMAL`.
- Execution authority: `none` at ready and complete.

The one-time pairing code remains only in an expired external evidence log and is not stored in the
repository. The captured sequence shows the device still unpaired while the real safety dialog is
visible; approval follows the explicit visible affirmative action. No unexpected client or request
was observed.

Containment remains honest: the production local-network fixture briefly bound `0.0.0.0:8765` and
used its existing discovery behavior. Containment came from ephemeral identity, short lifetime,
explicit approval, bounded execution, and zero authority—not from loopback or network-namespace
isolation. Product Assurance previously accepted that boundary for this one run.

## Exact integration result

- Runner:
  `com.radforge.romverse.companion.test/androidx.test.runner.AndroidJUnitRunner`
- Complete inventory: 12 tests.
- Passed: 12.
- Failed: 0.
- Skipped/assumption-failed: 0.
- Duration: 18.737 seconds.
- Final result: `OK (12 tests)`.
- No suite, class, or test was isolated, repeated, reordered, excluded, or weakened after the run.

The passing Link test demonstrated:

1. explicit navigation to Link;
2. endpoint, certificate pin, and one-time code entry;
3. disabled legacy bypass;
4. exact safety-code dialog and no-command copy;
5. affirmative visible confirmation;
6. TLS-pinned pairing;
7. two fresh health snapshots;
8. schema-six Live Console evidence;
9. Device DNA and Ascension evidence;
10. encrypted remembered-session reconnection after Activity recreation;
11. execution authority remaining NONE; and
12. bootloader relocking remaining forbidden.

The Android error-priority log contains emulator/system keystore, task-persister, binder, and Google
speech-service noise. It contains no ROMVERSE `FATAL EXCEPTION`, ROMVERSE process crash,
instrumentation failure, or test failure.

## External evidence

External evidence is deliberately outside Git and contains no production credential:

- Fixture log: 444 bytes / 4 lines
  - SHA-256: `9ddcbda1f97f062772239f89cc92a36b9387b7ed21921b8d2701378a95f8072b`
- Runner log: 8,958 bytes / 179 lines
  - SHA-256: `4490e6b7199de0e36c477528823a3083cae4237caba24717bbe269fa2e1a9a45`
- Error-priority log: 3,864 bytes / 40 lines
  - SHA-256: `9c84f7c70b508c235622a3bd628751fddbb081e0fa34ac6667117af9144153b6`
- Screenshot sequence: 90 bounded PNG frames plus `SHA256SUMS`
  - Confirmation dialog frame 26 SHA-256:
    `3b2f0455cb7532304e1e85c5752a575e69b07f5f5d430b7e870b53f49a5447f7`
  - Confirmation dialog frame 27 SHA-256:
    `248c9484b67eea451633b3cd8cc683be4a6ef5782a4365b75f7d270d969cb238`
  - Live Console frame 36 SHA-256:
    `6ad329f5809c950d0c084aa7e5e221c68142ddb33851fd1d39bff9b4165a434f`
  - Full frame manifest SHA-256:
    `b8622616e42a9e1bd2fd464cde46ce1cb38938a44cac0716b0ec271df6cb7d9a`
  - Readable 25-frame Link sequence contact sheet SHA-256:
    `4ab2ec8c5670abe980676c3d6637b9b0907c043905ba8241c9c405367d3ceae8`

The screenshot sampler captured the current dialog and Live Console but did not hold the transient
paired Link, Device DNA, or Ascension pages long enough for a separate static frame. Their existing
runtime assertions all passed; no second execution was performed merely to manufacture screenshots.

## Non-double-counted regression evidence

- Current affected Companion integration: **12/12 passed**. This is the complete current
  instrumentation inventory and the only new runtime total for this correction.
- Current build/static admission: instrumentation Kotlin compilation, debug application assembly,
  debug instrumentation assembly, APK integrity, identity, signature, Git whitespace, and exact
  one-file diff checks all passed.
- The prior runnable Fedora checkpoint's full Linux Python regression remains
  **2,881/2,881 passed** at implementation commit
  `1300dde1b79304149b8acfafe0e3f272d800cd37`. It was not rerun or added to the 12 Android tests
  because this correction changes only Android instrumentation test interaction, not Desktop or
  Python runtime source.
- The prior 79-test Recovery/UI/state and 240-test Fedora Desktop/build/package focused groups are
  subsets of that 2,881-test result and are not counted again.

## Runnable Fedora product status

The already approved runnable Fedora development checkpoint remains intact:

- Source, isolated wheel, one-folder executable, and extracted portable ZIP startup/shutdown passed.
- All 19 canonical Desktop routes opened.
- Project opening, durable persistence, Guided/Expert shared state, and the complete inert
  **Scan → Match → Prepare → Consent → Result → Reassessment → Verification** journey passed.
- Local development artifacts remain unsigned, ignored outputs; nothing was published or installed
  system-wide.
- This Android test-only correction changes none of that source or evidence.

## Classification

- Implemented: current Companion Link instrumentation now exercises the authoritative confirmation
  UX instead of a retired bypass.
- Simulated/Tested: genuine API-35 emulator, real ephemeral TLS fixture, exact development APKs,
  complete 12-test runtime, visual capture, and prior Fedora inert Guided journey.
- Hardware Verified: Fedora host build/launch is genuine host verification. No physical Android
  hardware or phone operation occurred; emulator evidence is not hardware verification.
- Released: no.

## Guided friction and remaining limitations

- The stale test-only pre-pairing dead end is resolved; the contained Link journey now completes.
- The user retains one meaningful safety-code decision. The legacy checkbox cannot be activated and
  no additional confirmation chain was introduced.
- Raw executor machinery is not exposed and no execution authority was added.
- A production-signed Recovery adapter, controlled physical phone verification, Windows release
  readiness, and release signing remain separate mandatory gates.
- The Fedora artifact is still a local development package, not an RPM, Flatpak, signed installer,
  or release.
- Network containment retains the previously reviewed short-lived LAN-listener limitation.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate.
- Pairing, UI confirmation, telemetry, fixture text, preparation, consent, historical identity, and
  this test grant no flash, wipe, root, unlock, relock, Recovery, or command authority.
- Exact-device evidence and same-incident attribution remain unchanged.
- UNKNOWN remains durable, never advances, and never triggers blind or automatic retry.
- Independent Recovery reassessment and verification remain mandatory.
- Bootloader locking/relocking remains permanently prohibited with no Guided, Expert, Recovery,
  adapter, server, Recipe, test, or model override.

## Platform and version-gate status

- Fedora/Linux Desktop: genuinely built, launched, packaged, reopened, and fully regressed at the
  approved runnable Fedora checkpoint; unchanged here.
- Companion Android: standalone and contained TLS Link behavior genuinely verified on one API-35
  emulator; no physical-hardware claim.
- Windows: separate working branch and Product Assurance track; no Linux merge, duplication, or new
  Windows verification claim in this checkpoint.
- 5 September 2026 pre-v1.0 feature freeze: compliant. This is the exact minimum test correction
  requested by Product Assurance and adds no product feature or execution capability.
- v0.2 Golden Foundation: remains **CLOSED** pending production trust/signing, controlled physical
  hardware, Windows, Recovery, and release gates.

## Next proposed Build task

Stop for Product Assurance review of this contained Link checkpoint. Do not begin another
consequential slice, merge a platform branch, perform a phone operation, enable production Recovery,
or publish/release until the repository verdict authorizes the next bounded direction.

## External actions

- Physical phone connection or operation: none.
- ADB/Fastboot against physical hardware: none.
- APK installation: application and instrumentation APKs installed only inside the wiped emulator.
- APK installation on a phone: none.
- System-wide package installation or dependency change: none.
- Fixture: one short-lived TLS instance; completed normally and closed.
- Emulator: one clean host-GPU session; controlled shutdown; final ADB inventory empty.
- Final TCP listener on port 8765: none.
- Host security, firewall, or SELinux change: none.
- Production Recovery execution/trust/signing: none.
- Protected Companion or Windows draft change: none.
- Approved logo or asset change: none.
- Website change: none.
- Publication/release/merge/force-push: none.
- Remote action: normal push of only this scoped Linux branch checkpoint is intended after this
  handoff commit; no unrelated branch will be pushed.

## Product Assurance Review Requested

- Confirm the correction faithfully exercises the current one-decision Link confirmation contract
  and closes the stale-test dead end without weakening the application safety flow.
- Confirm the exact 12/12 run, ordered zero-authority fixture evidence, APK admission, and bounded
  visual evidence satisfy the contained Link integration checkpoint.
- Confirm the approved runnable Fedora development build remains valid and v0.2 correctly remains
  closed pending the existing production, Windows, hardware, and release gates.
