# ROMVERSE Build Status

## Authoritative checkpoint

- Source and Product Assurance authorization commit:
  `db6fcc14b8fd446ed06e4f31100f17ff0e1b37c8`
- Reviewed implementation commit:
  `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Prior handoff commit:
  `e091a555c8ad95d79c4969b6ce77b492d5f7f600`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation real-product Desktop/Companion operability
- Milestone result: **DIRECT FEDORA DESKTOP ↔ COMPANION LINK VERIFIED**
- Product source result: unchanged; this checkpoint commits evidence/handoff only.
- Working-tree target state: clean before this handoff update. The separate original checkout's
  three protected Companion modifications and Windows launcher drafts were not edited, staged,
  discarded, built from, or committed.

## Product Assurance scope

Product Assurance commit `db6fcc1` closed the fixture-backed Companion Link milestone and authorized
one direct journey using the real Fedora Desktop and real Companion production Link surfaces. It
explicitly prohibited implementation/redesign, a fixture, private-state injection, dependency
installation, physical hardware, Recovery, platform merge, signing, publication, and release.

`docs/sync/AUTONOMOUS-BUILD-PROTOCOL.md` remains absent from this Linux branch. Its committed version
on `origin/windows-launcher-authorized-work` was read directly without checking out or merging
Windows work. Repository, separation, scoped-handoff, and mandatory-stop rules were preserved.

## Actual applications and environment

- Fedora Desktop: current source application launched through `romverse.app.main` from the clean
  Linux worktree in one isolated temporary workspace.
- Desktop workspace:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/evidence/direct-product-link-2026-09-07.BfV2nq/desktop-workspace.4iyCPc`
- Companion: unchanged approved debug APK installed only in one wiped API-35 x86-64 emulator.
- Companion APK SHA-256:
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Sole Android target: `emulator-5556:device`, with `sys.boot_completed=1` and `ro.kernel.qemu=1`.
- Host SELinux: Enforcing and unchanged.
- Desktop endpoint: one production TLS listener on the displayed local endpoint and port 8765.
- Desktop certificate SHA-256:
  `77068174fc55234143b7019aa2ffa466a6723dcd984e95eb3b9b121fba9a322d`
- Safety code displayed by both applications:
  `7706-8174-FC55-2341-43B7-019A`.
- The short-lived pairing code is omitted from repository evidence and the retained event log.

No instrumentation APK, fixture server, test-only application hook, private preference mutation,
transport approval call, pairing-state injection, or production execution adapter participated.

## UI-operation method

Fedora's system accessibility inventory did not expose the Qt window. An external, uncommitted
evidence driver therefore launched the real `romverse.app.main` window, navigated via its visible
`Open ROMVERSE Link` action, and used Qt mouse events on the existing visible Generate, safety
checkbox, Approve, and Reset buttons. It observed pending/approved state and the existing public
snapshot signal only for timing/evidence; it never invoked transport pairing/approval/reset methods,
altered preferences, or injected state.

Companion was operated through visible Android screen taps and text entry. All endpoint,
fingerprint, one-time-code, confirmation, navigation, restart, and presentation actions went through
the unchanged application UI. Screenshots are captures of the actual running applications.

## Demonstrated direct product journey

1. Desktop opened its real ROMVERSE Link page in the isolated workspace.
2. Desktop generated a short-lived code and visibly displayed its endpoint, full certificate
   fingerprint, derived safety code, disabled approval controls, and Guardian boundary.
3. Companion opened its real Link page. Emulator multicast discovery did not auto-fill the current
   host endpoint, so the existing manual endpoint, fingerprint, and code fields were used.
4. Companion derived and displayed the exact same safety code as Desktop.
5. Companion presented its real `CONFIRM DESKTOP IDENTITY` dialog. The dialog retained Yes/No
   choices and explicitly stated that the Link grants no flash, root, wipe, unlock, relock, or
   command authority.
6. The affirmative Companion decision submitted the genuine TLS-pinned request. Desktop visibly
   changed to `Wireless request received • approve device`.
7. Desktop's real safety checkbox and `Approve device` action were selected only after that request.
8. Both products reached genuine paired state. Desktop displayed
   `Paired • read-only wireless telemetry enabled`; Companion displayed
   `Paired • two-way health sync active` and `PAIRED`.
9. Desktop received 13 distinct authenticated snapshot observations over the bounded session. The
   first two alone satisfy the milestone; later observations prove sustained operation and are not
   counted as separate tests.
10. The visible Desktop health panel reported Android 15/API 35, battery, storage, RAM, Vitalis
    `OPTIMAL`, Guardian health 100/100, privacy scope, root/bootloader evidence, and
    `authority none`.
11. Companion's actual Live Console displayed a trusted redacted Link-v6 ledger, the encrypted Link
    event, `Execution authority: NONE`, and `Bootloader relock: NEVER`.
12. Companion was stopped and reopened without a new code or approval. Its Home screen returned as
    `ROMVERSE Link • securely paired`, and fresh authenticated snapshots continued through the same
    Desktop listener and certificate identity.
13. Desktop's visible `Reset wireless pairing` control revoked the session. No new authenticated
    snapshot was accepted afterward.
14. Companion was reopened again. Home displayed `ROMVERSE Link • not connected`; its Link page
    displayed `Trusted Desktop remembered • approval required`, `ENTER NEW LINK CODE`, and preserved
    only the pinned identity. The old credential did not reconnect.
15. After reset, Desktop's remembered-session record was absent. Only the workspace TLS certificate
    and private key remained; no bearer token or token digest session record survived.

## Result classification

- Implemented: no new application implementation. Existing Desktop and Companion product surfaces
  were used unchanged.
- Simulated/Tested: genuine real-product integration on one API-35 emulator, including production
  local TLS, certificate pinning, both visible approval boundaries, authenticated telemetry,
  remembered-session reconnect, and revocation. The Android target is simulated and is not phone
  hardware evidence.
- Hardware Verified: Fedora host launch and networking are genuine host verification. No physical
  Android device or firmware operation occurred.
- Released: no.

## Acceptance evidence

- Direct pairing without fixture/private-state injection: passed.
- Exact safety-code equality on both actual applications: passed.
- Companion affirmative/decline dialog retained: passed; affirmative path used.
- Separate Desktop request, safety checkbox, and approval boundary: passed.
- At least two fresh authenticated snapshots: passed; 13 distinct timestamps observed during the
  bounded session.
- Structured/privacy-filtered Live Console: passed visibly.
- `execution_authority: none`: passed in every retained Desktop event and visible Companion console.
- Remembered-session reconnection: passed after Companion process restart without another pairing
  code or approval.
- Session duplication: not observed; one Desktop listener, one certificate identity, one approved
  state, and one continuing stream existed.
- Explicit revocation: passed through the real Desktop Reset control.
- Old-credential reconnect after revocation: rejected; Companion required a new Link code after
  restart, Desktop accepted no later snapshot, and its remembered-session file was absent.
- Bootloader relock: remained `NEVER`; no relock path or command existed.
- Android crash/ANR scan: no ROMVERSE `FATAL EXCEPTION`, process crash, or ANR found.
- Final containment: Desktop closed, Companion stopped, emulator shut down, ADB empty, and no port
  8765 listener or ROMVERSE/emulator process remained.

## Evidence inventory

External evidence root:
`/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/evidence/direct-product-link-2026-09-07.BfV2nq`

- Redacted Desktop event log: 17 lines / 9,751 bytes; contains no pairing-code field or any code used
  during setup.
  - SHA-256: `082aa7090499f3f7ef565b47f86d24177ec68a8f1ee5814c9a06fb26e3c4fcfe`
- Desktop paired state:
  - SHA-256: `b4c247c243e64ce1f08764b499f03532af9d8513f54bda267361f002f7026bf8`
- Desktop authenticated health snapshot:
  - SHA-256: `5c865cbc6178e7e265c8d44ccd42da1203794953a1979a8ca22128feccf3ea6c`
- Desktop continuing after Companion reopen:
  - SHA-256: `bc3d95072b84016a0e6da6b4da37d3e827b7869d329f6fceadad686a51d98032`
- Desktop after visible reset:
  - SHA-256: `27d18912dd766c2dad24376182c9d0ed994238eeb6dfa8323d2c74a2863a4026`
- Companion exact safety-code dialog:
  - SHA-256: `6c76cfc58d03594ea0793d2f0e296e6b98d9fa77f5a6f751c49fc9515678ace9`
- Companion paired state:
  - SHA-256: `7674dbe5a1a7d20179004809119a7dc921982a923e269ee528a8a73ca5f12586`
- Companion structured Live Console:
  - SHA-256: `eee446876d2e34adedffa06497f32d54c5126b40ccdccfd9590b1f7e917224f9`
- Companion remembered-session reopen:
  - SHA-256: `ab909ed34ea76b4285e92c8b608025a1d26332755c1c54397430346dc63868ca`
- Companion after revocation and restart:
  - SHA-256: `f6ea325e3d9f00497ecc59bf788849daaf264ad1adf3acfd2d77e742ec5d14ff`
- Android error-priority log:
  - SHA-256: `e7d7bf631669eefc490c94bf56652a0ed41bc29071e4f36e8d36c1a52d47314c`
  - Contains emulator/system service noise but no ROMVERSE fatal/ANR signature.

Raw local setup screenshots that display a now-revoked one-time pairing code are not referenced as
shareable evidence. No pairing code, bearer token, TLS private key, or private preference content is
written to this repository handoff.

## Proportional verification

No broad regression, build, APK rebuild, or architecture test was repeated. The Product Assurance
authorization was a tangible direct-product operability milestone, and the unchanged approved
artifacts were reused.

Prior non-double-counted evidence remains valid and unchanged:

- Companion instrumentation inventory: **12/12 passed** at implementation commit `b86aca2`.
- Full Fedora/Linux Python regression: **2,881/2,881 passed** at implementation commit `1300dde`.
- The prior 79-test Recovery/UI/state and 240-test Fedora build/package groups remain subsets of the
  2,881-test run and are not added again.

## Harness setup observations

Before the completed journey, two external-driver-only timing mistakes stopped Desktop after a valid
pending request but before its UI approval:

1. the driver evaluated the safety checkbox before Desktop's one-second UI timer enabled it;
2. the next driver mouse event landed in the empty middle of the wide checkbox row instead of its
   visible indicator.

Both attempts stopped before Desktop approval, created no session token, and were explicitly reset
through Companion's visible Reset control. Only the external driver was corrected; ROMVERSE source,
state contracts, transport, APK, and security behavior were unchanged. The third attempt clicked the
actual visible indicator and completed the approved product journey.

These are not claimed as application failures or additional tests. They are retained for audit so
the checkpoint does not hide setup history.

## Guided friction and remaining limitation

- Emulator multicast did not auto-fill the live Desktop identity. The existing manual endpoint,
  fingerprint, and code route worked and was understandable, but emulator discovery remains a
  usability limitation rather than a zero-friction proof.
- After the first pre-approval attempt was visibly reset, its already-running Companion request later
  changed the button label to `APPROVAL TIMEOUT • TRY AGAIN`. The same existing button still opened
  the correct safety dialog and did not block the successful journey. This suggests a late asynchronous
  presentation update can overwrite reset copy and merits Product Assurance triage; no source change
  was authorized or made here.
- Direct integration remains emulator evidence, not physical-phone verification.
- Production Recovery adapters, production signing/trust, Windows release readiness, physical
  hardware, and release publishing remain separate mandatory gates.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate.
- Link carried bounded health/mission evidence only. Pairing, safety confirmation, telemetry,
  remembered identity, and reconnect granted no device-changing authority.
- Exact certificate pinning and both user decisions remained intact.
- Reset revoked authorization while preserving only the non-authoritative pinned identity needed to
  explain that a new code is required.
- UNKNOWN-on-uncertainty, no blind retry, exact-device attribution, same-incident Recovery,
  independent reassessment/verification, and durable evidence were not changed.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora Desktop runnable development build and inert Guided Recovery journey: verified at the
  approved prior checkpoint and unchanged.
- Fedora Desktop ↔ Companion product Link: verified on the real Fedora application and one API-35
  emulator using unchanged production Link surfaces.
- Physical Android hardware: not run and not claimed.
- Windows: remains a separate working branch and Product Assurance track; no merge, duplicate work,
  or Windows claim occurred.
- 5 September 2026 feature freeze: preserved; only a repository evidence/handoff document changes.
- v0.2 Golden Foundation: remains **CLOSED** pending Windows, physical, production trust/signing,
  Recovery, and release gates.

## Next proposed Build task

Stop for Product Assurance review. Do not correct the observed late timeout-label race, start a new
consequential slice, merge platforms, connect a phone, enable Recovery, rebuild artifacts, publish,
or release without the next exact repository verdict.

## External actions

- Physical phone connection/operation: none.
- Firmware, partition, bootloader, flash, wipe, root, unlock, relock, or Recovery operation: none.
- ADB actions: exact emulator admission; approved APK install to the wiped emulator; visible app
  launch, taps/text, presentation stop/reopen, screenshots, log capture, and controlled emulator
  shutdown only. No ADB/Fastboot device-changing command was run.
- APK installation on physical hardware: none.
- System-wide package/dependency/environment change: none.
- Production trust/signing: none.
- Website or approved-logo change: none.
- Companion/Desktop production source change: none.
- Protected Companion/Windows draft change: none.
- Publication/release/merge/force-push: none.
- Remote action: normal push of only this evidence handoff is intended after commit.

## Product Assurance Review Requested

- Confirm the real-product UI evidence closes the direct Fedora Desktop ↔ Companion Link milestone.
- Confirm remembered-session reconnect and post-reset rejection are sufficiently demonstrated without
  overstating emulator evidence as physical hardware verification.
- Triage the observed late `APPROVAL TIMEOUT • TRY AGAIN` presentation overwrite after a visible
  reset and decide whether it warrants a future minimum correctness correction.
- Confirm v0.2 remains closed and the next task must stay within the existing feature freeze and
  platform/hardware/release gates.
