# ROMVERSE Companion

The Android sidekick for ROMVERSE Studio.

Package: `com.radforge.romverse.companion`

The current 0.2 alpha provides the branded mobile **Home**, **ROMVERSE Link** pairing,
**Pulse**, **Vitalis**, **Lifeline**, **Live Console**, **Device DNA**, **Ascension Protocol**,
**App Launchpad**, **ROMVERSE Galaxy**, Guardian Core state, and activity feed.

Home begins with a truthful **ROMVERSE Link Flight Path**: PHONE → DESKTOP → IDENTITY → SESSION →
SYNC. Its five evidence-derived stages, deterministic progress, freshness label, and one contextual
action distinguish discovery, safety-code comparison, authorization, expiry, refresh, and a genuinely
fresh two-way sync. USB detection never masquerades as encrypted Companion pairing and no longer
disables wireless setup; it remains useful for Desktop-side read-only identity while Companion can
pair independently over trusted local Wi-Fi. USB assist can also deliver an exact one-use request
through a loopback tunnel to the selected authorized phone. Companion then shows the Desktop safety
code in a dark, accessible Yes/No dialog; Yes submits and completes read-only Link automatically,
while No blocks the attempt. USB presence by itself never establishes trust. The animated
active-stage pulse is purposeful, stops
off-screen, and respects Reduced Effects and Android's disabled-animation setting. The entire route
has a concise accessibility description and permanently states that it grants no flash, root, wipe,
unlock, relock, or command authority.

The approved Galaxy interface now uses a responsive `RomverseDrawerLayout`: swipe inward from the
left edge (or tap the menu control) for the translucent glass feature drawer. A bounded classifier
accepts only a deliberate horizontal right-swipe that begins in the 28dp edge zone; vertical,
diagonal, reverse, multi-touch, out-of-edge, and already-open gestures do not take over navigation.
On Android 10+ a centered, narrow system-gesture exclusion zone improves reliability without
claiming the full Back edge, while the menu button remains the accessibility fallback. A persistent glass bottom
bar keeps Home at the bottom-left exactly once, followed by Link, Live Console, Vitalis, and More.
Device DNA and Ascension have distinct first-class drawer actions, so their evidence pages remain
discoverable without depending on a restored session or an off-screen shortcut.
One validated connectivity badge remains persistently visible at the top-right of the app bar;
Home, focused sections, and the swipe drawer do not duplicate or independently calculate it.
The Home command deck renders genuine read-only health, battery, storage, and RAM gauges; missing
measurements remain visibly unconfirmed. Sections stay inside the same navigation shell, Android
Back returns to Home, and the current section is never hidden behind a fixed-width sidebar.
About ROMVERSE now uses a responsive vertical story layout with live build metadata, the ROMVERSE
Promise, SteveTheRad/RadForge Labs identity, ecosystem and trust boundaries, and crisp standalone
website actions for `https://romverse.app/` and `https://radforgelabs.com/`, followed by Facebook
and Reddit actions using their exact clean official destinations. The website and social rows use
aligned touch targets, untinted vector marks, validated HTTPS hosts, and no tracking parameters.
Double-tapping the R
discovers **ROMVERSE: The Origin**; the local discovery and **Beyond the Verse** state enable replay
without inventing account XP. The purpose-built vertical experience presents the seven approved
chapters with automatic readable pacing, progress, previous/next, pause, skip-to-finale, immediate
exit, runtime Reduced Effects, restrained haptics, and optional locally packaged ambience that stays
off by default.
Home now applies the Companion three-second rule with one deterministic contextual hero above the
secondary gauge deck. Guardian attention outranks a running Nexus mission, a running mission
outranks routine Vitalis attention, and healthy local state becomes ROM Health. The same card always
states ROMVERSE Link/USB evidence, Guardian state, and whether a live Desktop mission is confirmed;
missing Link telemetry remains explicitly unconfirmed. Its single action opens the evidence-backed
Live Console, Vitalis, or ROMVERSE Link route selected by that state.
Vitalis safe-cache preview and cleanup now use a genuine indeterminate operation bar, keep the
trigger locked through confirmation, and release it only on a terminal result; no decorative
percentage is presented for filesystem work that has no measurable progress callback. If deletion
returns but its atomic receipt cannot be saved and reverified, the outcome is explicitly failed
evidence—not a completed cleanup—and the user is told to resolve app storage and preview again.
Physical USB evidence now reads Android's device-side USB state and USB power state before falling
back to attached-accessory enumeration. A deliberately disconnected USB link remains an optional
Link condition rather than turning an otherwise 100/100 phone-health result into false attention.
Vitalis now requires current battery-temperature and validated-network evidence before publishing a
numeric Guardian health score. Missing evidence stays `UNCONFIRMED`, known critical evidence still
surfaces when another signal is unavailable, and observations outside the two-minute freshness
boundary cannot produce a reassuring verdict. Authenticated Desktop sync uses health schema four:
temperature, network, USB, state, evidence coverage, and score travel together so Desktop can
re-derive the result and reject a contradictory or replayed claim. Schemas one through three remain
readable for compatibility but do not gain schema-four certainty retroactively.
Lifeline schema three now binds active, ready, and comparison-complete states to their exact reviewed
checkpoints and before/after findings. The displayed comparison is re-derived, and Companion opens
the checklist instead of running a premature comparison. Verified schema-two sessions migrate
without data loss; an older completion that skipped checkpoint review is backed up and safely returns
to the guided checklist rather than remaining falsely complete.
Ascension now distinguishes an unavailable manager from a Desktop-verified official root tool. Its
beginner card shows the allowlisted repository, stable release tag, exact APK name, and a 16-character
integrity reference; full hashes, host paths, approvals, and execution authority remain on Desktop.
Desktop and Companion now consume the same project-persisted Ascension Route Record. It binds the
automatic Magisk/KernelSU decision to the protected source, Device DNA, authorized phone, and kernel
evidence; changed or insufficient evidence invalidates or leaves the route explicitly unconfirmed.
The record always carries zero execution authority and can never permit bootloader relocking.
Blocked starting states use the same deterministic prerequisite-resolution plan as Desktop, so the
Companion card distinguishes ROMVERSE's safe local extraction/tool work from the smallest real
phone or user action instead of showing a generic failure.
When that evidence is verified, Companion checks Android's currently installed package and full
signing-certificate digest against the pinned official Magisk or KernelSU signer. Only an exact match
receives a **Continue in manager** button, which merely opens the app; missing or mismatched packages
stay explained and blocked, with no patch/root/flash authority.

Public builds no longer contain a developer-specific Home greeting. Companion uses a bounded local
display name from Settings, temporarily prefers a server-verified Members profile while signed in,
and falls back to “Explorer” for a new user. Exact identity-only records are generated from Desktop
Device Packs that contain a verified build contract. On the primary validated device this displays
**Xiaomi 17 Pro Max** together with the raw `2509FPN0BC` model, `popsicle` codename, Pack identity,
and evidence hash; unmatched devices keep Android's reported model explicitly unconfirmed.

Companion Settings now exposes only policies it enforces. Its public HTTPS switch gates and cancels
Members authorization while leaving encrypted local ROMVERSE Link available. Community research,
Desktop tool acquisition, and Desktop notifications remain Desktop controls rather than decorative
mobile switches. Saving an unrelated preference preserves a valid in-memory Members session unless
the issuer/client changes or public HTTPS services are disabled.

The optional **Privacy Curtain** is also a real local setting. When enabled, Companion covers the
device/project/session working area every time the app opens or returns from the background and sets
Android's secure-window policy to block screenshots and screen recording. **Reveal this session**
uncovers the current foreground session without disabling capture protection; leaving the app closes
that temporary reveal. The persistent app bar, single connectivity status, drawer, ROMVERSE Link,
and Guardian state remain available and unchanged.

Android backup and device-to-device transfer explicitly exclude all Companion app-private state.
Link tokens, certificate pins, private evidence, and local history therefore cannot silently migrate
to another phone; that device must establish and verify its own Link identity.

Optional **OLED mode** applies a tested true-black palette to the command surface, focused sections,
glass cards, swipe drawer, persistent bars, and inactive navigation controls while preserving the
cyan/violet ROMVERSE accent lighting and restrained stars. It removes the ambient nebula layer,
persists locally, applies immediately through Android Activity recreation, and restores the exact
visible route. Display mode never changes evidence, Guardian policy, or device authority.

Settings also persists **Guided · Arcana** or **Expert · Architect** presentation. Guided Mode
shows the essential Device DNA answer first and folds Capability Map overflow behind an explicit
technical-evidence action. Vitalis keeps every diagnosis and next safe action visible while folding
its evidence ledger and trend graph; Live Console keeps its mission/event ledger and Raw Terminal
attention summary visible while folding privacy-filtered terminal lines; Ascension keeps its stage,
route, blockers, verified-manager state, next action, and Guardian boundary visible while folding
source-bound project, artifact, digest, and patch-target references. Expert Mode opens all of that
accepted technical evidence immediately. Both choices use the same evidence and pairing state,
grant no execution authority, leave Guardian unchanged, and preserve the permanent
`bootloader_relock: never` boundary. The policy is covered by JVM tests and Android 15 Activity
recreation tests in both modes.

Build with Android Studio, or use the repository-managed Android SDK and Gradle runtime:

```bash
cd ..
ANDROID_HOME="$PWD/.build-tools/android-sdk" \
  .build-tools/gradle/bin/gradle -p companion :app:assembleDebug
```

The debug APK is written to `companion/app/build/outputs/apk/debug/app-debug.apk`.

Run the Companion JVM gate and build together with:

```bash
cd ..
ANDROID_HOME="$PWD/.build-tools/android-sdk" \
  .build-tools/gradle/bin/gradle -p companion testDebugUnitTest :app:assembleDebug
```

Install all analysis dependencies and run the strict Android UI/package lint gate with:

```bash
cd ..
ANDROID_HOME="$PWD/.build-tools/android-sdk" \
  .build-tools/gradle/bin/gradle -p companion :app:lintDebug
```

With an authorized Android device or the repository's Android 15 / API 35 emulator connected,
run the real Activity UI gate with:

```bash
cd ..
ANDROID_HOME="$PWD/.build-tools/android-sdk" \
  .build-tools/gradle/bin/gradle -p companion :app:connectedDebugAndroidTest
```

The gate covers Vitalis evidence assessment, Lifeline finding-specific checkpoints and fresh-scan
comparison, private activity-history rules, local Galaxy validation/search/voting, Ascension
status, safe-cache operation-state transitions, Link v6 Live Console validation, deterministic
left-edge gesture classification, fail-closed route restoration, emulator-safe device identity,
and the single-Home responsive navigation contract. The connected Activity gate additionally
checks the one-owner connectivity status, all five primary destinations, About and official
community actions, Android Activity recreation, OLED live application and route persistence, Privacy
Curtain foreground return and secure-window protection, and emulator identity on a genuine Android
runtime. A
debug APK is a test artifact and is not a signed
public release.

## PC emulator validation

The Companion can be exercised without a connected phone by creating an Android 15 / API 35
Google APIs x86_64 AVD and installing the debug APK with ADB. ROMVERSE deliberately labels Android
SDK emulator markers as **Android Emulator** and leaves physical marketing identity unconfirmed;
an emulator can never masquerade as a supported retail Google device. Emulator validation covers
layout, navigation, lifecycle restoration, and read-only local behavior. It does not replace
physical-device checks for USB, wireless Link recovery, battery temperature, storage permissions,
or manufacturer-specific Android behavior.

For a contained end-to-end Link run, start `scripts/companion_link_emulator_fixture.py` from the
repository root. It prints a short-lived pairing code, emulator endpoint, certificate pin, and
safety code, automatically approves only that fixture request, and exits successfully only after
the Companion has returned two fresh health snapshots. Pass its three connection values to
`connectedDebugAndroidTest` as `romverseLinkHost`, `romverseLinkCode`, and
`romverseLinkFingerprint` runner arguments. The integration test verifies TLS pinning, explicit
pairing, schema-six Live Console, Device DNA, and Ascension parsing, the health return channel,
remembered-session refresh, Live Console hydration after Activity recreation, and the rendered
Guardian boundary on the linked Ascension page. The fixture exposes no execution or device-changing
authority.

`scripts/verify_companion_update.py` exercises upgrade continuity on an Android emulator only. It
refuses every non-emulator serial, requires Android's qemu identity, seeds a previous signed debug
candidate with valid private Settings, Activity, Galaxy, Vitalis trend, encrypted Link credential,
and Lifeline evidence, installs the current APK with Android's data-preserving update path, then
revalidates every domain and integrity envelope. It never targets a phone and grants no execution
authority. This development gate does not replace an update test from the eventual signed public
candidate on representative physical devices.

## Wireless pairing

Keep the PC and phone on the same trusted Wi-Fi network. ROMVERSE Studio advertises
its local endpoint automatically (default TCP port `8765`). In Companion, let the PC
address fill by discovery, enter the short-lived code generated on the desktop, and
approve the request on the PC. Authorized USB/ADB remains a separate read-only Desktop evidence
path: detecting the APK over USB never claims that encrypted Link is paired and never disables
wireless code generation. A generated or pending wireless request also survives periodic USB scans.
As an optional convenience, **Pair connected phone with USB assist** creates a private loopback-only
tunnel for the one selected authorized phone and opens the same certificate-identity checkpoint in
Companion. The six-digit code is delivered in memory, the user must still choose Yes on the matching
safety-code dialog, and only then does Desktop approve that exact request automatically. Choosing No
blocks it. The tunnel handoff is reversible, Guardian-approved, and grants no general ADB command or
device-changing authority; the serial and one-time code are redacted from the Guardian ledger.
Wireless pairing currently grants read-only Companion visibility; Guardian does not
allow flashing, wiping, unlocking, or other device-changing actions.

Protocol v3 requires HTTPS with TLS 1.2 or newer. Desktop keeps a persistent per-workspace ECDSA
certificate; automatic discovery fills its exact SHA-256 fingerprint and Companion pins that
certificate for every request. Compare the human-readable Link safety code on both screens before
approving. A request identity protects approval polling and an approved, expiring token protects
every telemetry read. An explicitly approved phone is remembered for up to 30 days across phone,
network, and Desktop restarts. Desktop persists only a mode-0600 SHA-256 verifier rather than the
reusable token. Companion stores its required reusable token only as an AES-GCM envelope whose key
is generated inside Android Keystore; a valid legacy plaintext preference migrates one way, while
missing, altered, or undecryptable envelopes fail closed and require fresh approval. Companion
Desktop's verifier record is separately private, atomic, byte-bounded and exact-schema; linked,
redirected, oversized, extra-field, re-digested type-confused, expired, or overlong-lifetime records
cannot restore approval. A genuine schema-one verifier migrates only after its digest, expiry and
configured lifetime are revalidated. Companion
accepts a rediscovered address only when the advertised certificate is
the previously pinned Desktop identity **and** the newly discovered endpoint proves that identity
over pinned TLS with the still-active approval. A DHCP address change is then saved and telemetry
resumes automatically. Discovery keeps listening across bounded receive timeouts and is retried
alongside bounded reconnect backoff; an advertisement alone can never replace the saved endpoint.
Reset Pairing or expiry revokes the remembered session. Protocol-v2
cleartext sessions must pair again after upgrading, and Android rejects cleartext traffic. Only
private/local network endpoints are accepted; USB read-only features remain available when the
wireless listener cannot start.

The read-only telemetry payload is currently schema v6. It can carry up to eight genuine,
privacy-scrubbed Desktop Live Console events plus bounded Nexus/Pathfinder/Guardian status.
It carries no command, approval, serial, private host path, full hash, or execution authority.
Raw Terminal is a separate one-way, four-record feed containing only bounded privacy-filtered
results from six Guardian-approved read-only Command Console probes. Companion cannot request or
execute a terminal command, and ADB device enumeration plus host-detail probes are excluded.

Schema v6 also carries a privacy-bounded Device DNA Capability Map for the selected Desktop
project. Home shows a compact summary and a dedicated panel renders up to twelve `SUPPORTED`,
`CAUTION`, `UNSUPPORTED`, or `UNCONFIRMED` decisions. Only a scrubbed project label and truncated
profile reference cross the Link; paths, full hashes, commands, approvals, and write authority do
not. Companion requires `execution_authority: none` and `bootloader_relock: never` and rejects the
entire profile if those safety constraints or any bounded field are invalid.
The dedicated panel can copy the same bounded map as a privacy-safe support/community report; the
report repeats its no-authority and never-relock boundaries and cannot expose evidence that was not
accepted by the Link parser.
Device DNA, Live Console, and Ascension manual Link refreshes display a genuine indeterminate
network-operation bar, lock duplicate taps while the request is active, and always return to an
explicit success, expired-session, or unavailable state instead of leaving a permanent loading label.
