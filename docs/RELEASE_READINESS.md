# ROMVERSE release readiness

ROMVERSE must not be described as production-ready merely because the desktop shell or a
debug APK opens. A public build is eligible for release only when every applicable gate below
has current evidence.

## Required gates

1. Run `pytest`, `ruff check .`, and `ruff format --check .` on supported Linux and Windows
   Python versions. Stress every byte-reporting worker with thousands of duplicate and late
   backwards callbacks; only new bounded integer percentages may reach Qt, and the operation must
   still publish its truthful terminal state.
2. Run Companion `testDebugUnitTest` and `assembleDebug` with Java 17, Gradle 8.11.1, and the
   configured Android SDK. The activity, Galaxy, optimizer-history, health-contract, and recovery
   domain tests must execute; a `NO-SOURCE` result is not a pass. On a gesture-navigation phone,
   verify a horizontal swipe from the bounded left-edge zone opens the drawer, an edge-originating
   vertical scroll leaves it closed, swipe-to-close still works, and the menu button remains usable.
3. Build the desktop wheel in an isolated environment and inspect it for all runtime Python
   modules, branding art, phone art, and integrity-indexed Device Packs. CI runs
   `scripts/verify_wheel.py`, installs that wheel, opens its packaged desktop shell offscreen, and
   initializes a fresh workspace with `scripts/smoke_installed_desktop.py`.

   Current Ubuntu development evidence recorded on 2026-08-31: a fresh isolated Hatch build
   produced a 211-member wheel; the strengthened verifier byte-compared every current Python module
   and runtime visual/audio asset against the source tree and validated all 21 indexed Device Packs.
   A separate temporary environment installed the wheel and its declared dependencies, opened the
   packaged Desktop offscreen, initialized a fresh workspace, and reloaded all 21 packaged Packs.
   Repository tests also prove a changed packaged runtime module is rejected. This does not replace
   the required Windows installed-wheel pass or signed release-artifact validation.

   Current Fedora development evidence recorded on 2026-09-01: 1,103 Desktop tests and the complete
   Ruff check/format gate pass after the Ctrl+K navigation-only palette, canonical Activity Center,
   connected About ROMVERSE V3, collapsible/focus workspace shell, and structured ROMVERSE Archives
   and deterministic Archives Advisor increments. Tests cover bounded ranked retrieval, weak-match
   rejection, catalog/schema/source validation, every typed Advisor rule, exact ADB-state and
   error-code priority, direct article and canonical-page handoffs, exact Diagnostics-to-Recovery
   finding identity with stale-evidence refusal, no-worker navigation, a reversible exact-source
   focus, notification-independent in-page refusal feedback, and evidence-aware Command Deck
   exact/general/mismatch repair routing; exact source-bound Nexus-plan review context in Guardian
   Core, bidirectional navigation, zero approval/execution authority, and source/destination stale
   identity refusal; Recovery Bay report boundaries, adaptive research
   disclosure, strict guided-session evidence, exact-article local Resolution Memory, hostile and
   semantically false re-digested
   outcome rejection, Live Console table contrast, Activity Center filtering and export, adaptive
   rendering, accessibility, hostile ledger boundaries, and the strict private Origin-discovery
   record. A fresh
   isolated build produced a 219-member wheel with SHA-256
   `2ff0ae2b90ccc2692a37606e49d90d07606def4040aecc547ecb993abaa773d2`; the verifier
   byte-compared all runtime modules with source and revalidated all 21 indexed Device Packs. A
   separate wheel-target environment imported the packaged 110-guide catalog, Advisor, strict guided
   sessions, Resolution Memory, and the deterministic Diagnostics-to-Recovery concern map from
   outside the source checkout; verified one installed local improvement comparison and an exact
   storage-finding handoff with no session/worker start, its exact highlighted return to Quantum
   Optimizer, the promoted `STORAGE PLAN READY` Command Deck route, the healthy general-intake
   fallback, preservation of the real Platform Tools resolver after a failed refresh, and both
   handoff refusal messages with Desktop notifications disabled; opened an exact current Nexus plan
   in the installed Guardian Core review card with its project/objective/digest/requirements and
   zero authority; opened the packaged Desktop
   offscreen; initialized a fresh workspace; and reloaded all 21 Packs. This remains development
   evidence, not the required signed Windows/Fedora public-release certification.
4. Launch the installed wheel on Ubuntu, Fedora, and Windows, initialize a fresh workspace, and verify
   that an existing workspace opens without migration loss.
   For Desktop Device DNA, tamper and correctly re-digest nested facts and bootloader-relock state;
   add top-level/nested fields; inject wrong types, duplicate/cross-missing evidence IDs, oversized
   content, a linked profile, wrong project/source identity, and a caller-supplied inspection
   lookalike. Confirm every invalid profile fails closed, only persisted schema-two inspection can
   strengthen structure capabilities, records remain `0600`, and a genuine schema-one profile
   remains readable then upgrades on the next refresh.
   With a real phone, open Genesis at Device DNA and request a refresh. Confirm the progress card
   remains responsive, the fresh marketing identity and Capability Map appear, and Genesis advances
   only from current evidence. Disconnect or stop ADB during a second refresh and confirm ROM Studio
   clears the last-seen device, explains the failure, and does not reuse stale identity; reconnect
   and confirm a later fresh scan restores the correct profile without changing phone state.
   For Compatibility Matrix, alter and correctly re-digest each decision/status/boolean; add
   top-level or nested fields; coerce booleans; oversize or link the record; remove/reorder a
   decision; and refresh Device DNA after saving a Matrix. Confirm every load re-derives the exact
   decision tuple, stale bindings fail, safety/telemetry invariants cannot be changed, files remain
   `0600`, and a valid schema-one Matrix upgrades only through a fresh assessment.
   For Nexus and ROM DNA, alter then correctly re-digest route state, research gaps, predictions,
   Guardian requirements, project/Pack/source/tree/Recipe identity, and authority booleans. Add
   top-level/nested fields, coerce values, oversize or link each record, then refresh Device DNA,
   Matrix, build plan or Recipe. Confirm loaders re-derive current evidence, stale records vanish,
   private `0600` storage holds, and genuine schema-one records upgrade only through replanning or
   a verified ROM DNA save.
5. Exercise ROMVERSE Link over USB and a trusted local Wi-Fi network. If local networking is
   unavailable, ROMVERSE must remain usable and visibly mark only wireless pairing unavailable.
   Verify unauthenticated telemetry is rejected, request identities cannot be exchanged, expired
   and reset tokens fail, code throttling is per client, oversized/malformed phone snapshots fail,
   capability-bearing and private identifier fields are rejected, and a valid authenticated phone
   snapshot is rendered on Desktop. For Link v6 Raw Terminal, confirm that only the six approved
   read-only probe classes are relayed, size limits hold, serials/host paths/hashes/credentials are
   scrubbed, content changes invalidate the digest, and Companion has no command return channel.
   For Link v6 Device DNA, confirm the profile reference is truncated, source paths and full hashes
   are absent, malformed or authority-bearing maps fail closed, unavailable evidence stays explicit,
   and `bootloader_relock: never` is enforced without being counted as a project fault.
   For Link protocol v3, verify TLS 1.2+, exact Android certificate pinning, matching safety-code
   confirmation on both screens, rejection of cleartext/protocol-v2 sessions, identity persistence,
   certificate-expiry behavior, and fail-closed handling of a changed or damaged identity. Change
   the Desktop DHCP address while an approved session remains live; the Companion may persist the
   new endpoint only after the advertisement matches the saved fingerprint and an authenticated
   pinned-TLS telemetry request succeeds. Inject a spoofed matching advertisement, wrong pin,
   invalid endpoint, expired token, receive timeout, and temporary outage; none may silently replace
   trust, and bounded discovery/backoff must recover when the genuine Desktop returns. Repeat
   this on representative physical Android versions and hostile-network test fixtures before
   describing wireless pairing as safe on an untrusted network.

   Current repository evidence recorded on 2026-08-31 covers strict endpoint parsing, exact
   fingerprint comparison, refusal without active authenticated proof, bounded reconnect delay,
   continued discovery after UDP receive timeouts, persisted digest-only Desktop sessions across
   restart, private bounded atomic schema-two Desktop persistence, validated schema-one migration,
   hostile link/redirect/oversize/extra-field/re-digested-type rejection, safe contained removal,
   explicit reset/expiry revocation, and the production Android build/lint gate. A contained
   Android 15 emulator-to-Desktop run additionally proves a real short-lived code request, automatic
   test-fixture approval, exact Android certificate pinning, schema-six Live Console and Device DNA
   display, two accepted schema-four Companion health snapshots, remembered-session refresh, and
   rehydration of the already-open Live Console after Activity recreation. The first run exposed a
   stale restored panel despite successful background refresh; that lifecycle defect is fixed and
   guarded by JVM plus connected Android tests. The contained Android 15 fixture was repeated after
   strict Desktop session-store hardening on 2026-08-31. It was repeated again after wider
   Guided/Expert evidence disclosure and the phase-gated update harness: all 11 instrumentation
   tests passed with zero skips/failures, the
   fixture received two health snapshots, route recreation preserved the selected mode, and
   execution authority remained `none`. Physical DHCP-change, certificate-expiry, and
   hostile-network validation remain required before public release.

   Companion credential-at-rest evidence recorded on 2026-08-30 covers Android-Keystore AES-GCM
   round-trip, absence of a plaintext token preference, one-way legacy migration, altered-envelope
   rejection and credential clearing, and the full pairing/recreation fixture using the encrypted
   credential. Android backup remains disabled. Hardware-backed Keystore availability and upgrade
   migration still require representative physical-device validation.
6. Install the Companion APK as an update over the previous public candidate and confirm that
   private activity, Galaxy, optimizer, pairing, and guided-recovery data remain readable.

   Current Android 15 emulator development evidence recorded on 2026-08-31 installs the earlier
   signed debug candidate (`685504d38f4463bdd016321a79317d897c8f6da28b2baabd0ccee21a47008cf6`),
   seeds valid private Settings, Activity, Galaxy, Vitalis trend, Android-Keystore Link credential,
   and Lifeline evidence, then installs the current candidate through Android's data-preserving
   update path. Every value and integrity envelope reloads successfully. The host runner accepts
   exactly one `emulator-*` target, also requires `ro.kernel.qemu=1`, and refuses physical phones.
   The eventual signed public-candidate update on representative physical Android versions remains
   required before public release.
7. Review the Guardian audit chain and confirm that no unapproved device-changing command can
   bypass the gateway. Flashing, unlocking, wiping, rooting, remounting, and arbitrary shells
   remain release blockers until their device-specific contracts and recovery tests exist. Tamper
   with every Guardian approval line, verify the approval chain fails closed, confirm legacy
   approvals remain audit-only, and confirm current approvals stop authorizing at ten minutes.
   Verify Guardian Core keeps the interface responsive while it checks a long valid chain, locks
   duplicate refreshes, and reports an honest indeterminate state. Fill a valid audit to its file
   and record capacities and confirm ROMVERSE archives it byte-for-byte, binds the archived count,
   prior chain tail and full-file SHA-256 into the new ledger, and recursively verifies every prior
   archive. Mutate the newest and oldest archives without restarting ROMVERSE; both must invalidate
   the live chain and block execution. Inject an unverified oversized audit file, an oversized
   record line, invalid UTF-8, replacement and symlink paths; every hostile case must fail closed
   before unbounded parsing and authorize nothing. A legacy oversized ledger may roll forward only
   after its complete chain validates under the separate bounded recovery limits.

   Current Ubuntu development evidence recorded on 2026-08-31: repository tests cover record-
   capacity rollover, byte-identical archival, rollover-receipt binding, recursive multi-archive
   verification, same-process archive tamper detection, hostile legacy oversized evidence, and
   automatic migration of a valid legacy oversized chain. The live 45,796-record, 27,754,805-byte
   Guardian ledger was fully verified, archived without byte loss, rebound into a new active chain,
   and followed by successful physical Xiaomi Device Engine probes. This is development evidence,
   not independent disaster-recovery or hostile-filesystem certification.
   Exercise Recovery Autopilot with no approval, an altered ADB binary, tampered approval and
   receipt histories, kill/start timeouts, failed daemon stop, failed daemon start, and a hostile
   device-list output. Confirm it always attempts the bounded daemon restoration after an unclean
   stop, stores only output digests, never constructs `adb -s`, never deletes host keys, and cannot
   authorize any phone operation.
   For automatic Recovery Bay research, inject paths, email addresses, credentials, IP addresses,
   serial-like values, long hashes, hostile URLs, stale/future/missing dates, malformed provider
   responses, and settings changes during lookup. Confirm private values never enter the query or
   receipt, stale/unconfirmed evidence stays labelled, disabled results are discarded, remote text
   remains non-executable, and only a successful matching typed receipt can be promoted locally.
   Replace receipt/outcome paths with symlinks or non-regular files, symlink an intermediate store
   directory, inject oversized/extra-field/candidate-flood records and provider-controlled source or
   action identifiers, and forge a provider `confirmed working` flag. Confirm every path fails
   closed, writes remain inside the workspace with private unique staging, outcome enumeration is
   bounded, and a cached confirmation is rejected when its matching local outcome becomes invalid.
   Attempt outcome creation with a valid-looking random digest, a candidate from another error
   fingerprint, a failed ADB receipt, a changed tool executable, a wrong-project OTA/AVB receipt,
   missing contained artifacts, and a schema-one digest-only outcome. None may produce or retain
   `confirmed working`; valid ADB, exact-tool, OTA-source, and AVB evidence must still round-trip.
   For the final Guardian flash-mode handoff, refresh an unchanged readiness report, then alter a
   gate, source, device identity, data-handling flag, relock flag, record shape, file size and path
   type. Confirm only unchanged schema-two readiness facts preserve the exact keep-data/wipe-data
   choice, every safety or evidence change returns Genesis to review, and schema-one history remains
   audit-only. Repository tests cover stable-versus-ephemeral readiness identity, private `0600` file
   and `0700` directory modes, linked/oversized/extra-field rejection, source/device rebinding,
   re-digested relock rejection and permanent zero execution authority. Physical final-manifest and
   consent behavior remains a release-device gate.
   Confirm a current schema-two handoff routes from Genesis to Guardian Manifest Review rather than
   reopening Forge Control. Re-run with unchanged report identifiers/timestamps, changed evidence,
   another device, another source, an extra field, a re-digested authority/source mutation, an
   oversized record and a symlink. Only unchanged current facts may reopen the review. Until the
   Device Pack contains a signed exact partition-to-artifact write contract backed by physical
   recovery testing, verify that the review is `blocked-missing-exact-write-contract`, contains no
   partition writes or commands, exposes no final-consent control, reports no phone change and keeps
   bootloader relocking permanently prohibited.
   Prepare a matching phone, source blueprint, AVB/build evidence and pristine rollback capsule
   without a flash-certified Pack. Confirm the Pack flash and physical-validation cards remain
   ATTENTION, `guardian_handoff_ready` and `flash_ready` remain false, and **Provide required
   evidence** opens Device Atlas instead of restarting Autopilot. Import a signed fixture through a
   real verifier and confirm its root/Pack directories are `0700`, its envelope is `0600`, and a
   linked storage root is rejected without persisting bytes outside the workspace.
   Exercise Forge Control Autopilot with the Pack flash card ordered before a missing recovery
   checkpoint. Confirm it defers external flash certification, creates the local Time Machine
   checkpoint on the Studio worker with an indeterminate progress bar, and leaves the phone and
   protected source unchanged. With schema-one recovery evidence, confirm the managed verification
   worker reports measured hashing progress and upgrades it only after a full successful rehash;
   missing personal backup or stock-package locations must still produce a clear user choice rather
   than fabricated completion.
   Let Autopilot reach the final user-backup gate while signed write-contract evidence is still
   absent. Confirm the backup chooser opens automatically with local drive as the recommended route,
   cancellation does not advance, and local-file, local-drive, and explicit cloud completion all
   refresh readiness then resume Autopilot. The resulting UI must say the backup is secured but the
   project is not yet flash-ready, list the remaining gates, and never claim every prerequisite is
   complete while Pack or physical evidence is absent.
   Parse schema-one build contracts as non-write-authoritative and require an explicit bounded
   partition-write contract for schema two. Reject missing/extra fields, wrong source or attestation
   digests, reference-only AVB policy, false unlocked requirements, any relock permission, no data
   mode, unknown/non-image/duplicate artifacts, duplicate or destructive targets, implicit slot
   suffixes, unsupported transports/slots, disabled verification and more than 32 writes. Confirm
   only an exact signed physical-attestation envelope makes the Device Atlas write-contract check
   pass. With a synthetic flash-certified Pack and current local-build receipt, prepare both
   supported data modes and run Guardian artifact binding on its managed worker. Confirm byte
   progress is relayed unchanged below completion, binding's terminal 100 is withheld during
   unbounded manifest compilation, and review completion reaches 100 only after the command-free
   manifest exists; fixed 90/94 stage estimates must never appear. Confirm every declared image is
   fully rehashed and bound in order, private files use `0600` under a `0700` directory, and the
   review shows hashes/transports/slots while commands,
   consent, execution authority and phone changes remain absent. Reject a stale handoff, wrong Pack/
   source/contract, missing output, linked path, unsupported data mode, same-size/same-mtime content
   change, re-digested relock flag, hostile/oversized record, mismatched signed evidence, and a signed
   composite image not proven by the current signing pipeline. Confirm command-free schema-one
   review history remains readable only for audit.
   Refresh Forge Control repeatedly while readiness changes between blocked and attention states at
   its 1040-pixel minimum width. Confirm removed cards are no longer parented or visible, the content
   keeps its natural scroll height, no footer buttons overlap, and blocked/attention totals match the
   current cards.
8. Produce signed release artifacts, checksums, a privacy statement, known limitations, and a
   rollback procedure. Debug APKs and unsigned desktop bundles are test artifacts only.
9. For every Device Pack advertised as build-capable, verify an exact model/codename match,
   versioned partition and payload descriptors, a publisher signature and revocation path,
   exact stock-recovery inputs, and an independently reviewed physical recovery-test record.
   An exported Device Atlas validation request is evidence of missing work, not certification.
   For OTA/fastboot/partition-bundle blueprints, local-build attempts/results, super verification,
   and AVB topology,
   inject symlinked intermediate/target paths, oversized and extra-field JSON, invalid nested
   collections, missing logs/images, changed source size/mtime, wrong project IDs, and duplicate AVB
   roles. Confirm private atomic writes stay inside the workspace and every invalid loader fails
   closed. For partition bundles, also duplicate a partition role in separate directories, mutate a
   recorded format/path/plan field, exceed the image-count or aggregate-size cap, and alter an image
   after preparation. Confirm none reload or grant AVB/device authority. Confirm AVB schema three
   detects changed image metadata without UI-thread rehashing and schema two remains readable but
   cannot promote connected remediation. Confirm source-blueprint preparation begins
   indeterminately, emits no fixed 5/42/55/72/88 or 5–90 milestones, switches only to genuine
   cumulative fastboot/super or partition-image hashing bytes with one stable total, and reaches
   100 only after its private source-bound receipt is stored. OTA/tool/metadata phases without
   bounded work must stay animated, and a source changed during hashing must fail closed.
   For Payload Atlas, vary `payload.bin` filename case; create two case variants; inject top-level or
   nested fields; oversize or symlink the manifest; change payload path/size/mtime; perform a
   same-size payload or dumper mutation with restored timestamps; alter the source/project/tool
   hashes; and supply a genuine schema-one fixture. Confirm ambiguity and every hostile current
   record fail closed, extraction rehash catches content substitution, private mode is retained, and
   legacy evidence remains visible, is automatically rescanned in the same background operation,
   and continues extraction only after the fresh current evidence succeeds. A failed migration must
   preserve the reviewable legacy record and report the real scan failure. Confirm scan and the
   external extraction phase remain indeterminate, verified output images then publish one stable
   cumulative byte total, all pre-terminal updates remain below that total, and completion is
   withheld until the manifest commit. A linked existing partition target must be rejected without
   changing its referent or retaining partial staging.
   For an authorized offline signing fixture, detach or mutate the request manifest, add fields,
   oversize or symlink request/receipt records and artifacts, redirect an intermediate evidence
   directory, change Pack/build/policy identity, and tamper with imported bytes. Every case must
   fail closed. Confirm private `0600` records, no private-key ingestion, schema-two bounded reload,
   and full-hash migration of a genuine schema-one receipt.
   For Time Machine, inject extra/oversized/symlinked recovery records and private locators, swapped
   roles, changed project/source identity, missing external files, metadata drift, and a locator back
   into the workspace. Confirm none can satisfy readiness. A genuine schema-one fixture must remain
   visible but blocked until **Verify evidence** fully hashes every file and writes schema two.
   Confirm backup and stock-recovery verification uses one stable total equal to their combined
   selected-file bytes rather than equal per-file weighting, stays below 100 until persistence, and
   emits terminal completion only after the private recovery-evidence record is stored. A ROMVERSE-
   created phone-media registration must also wait for its enhanced device-bound receipt update.
   For the local-drive backup itself, keep ADB pull phases indeterminate, then switch to one stable
   cumulative source-file byte total after inventory. Confirm no fixed 55/38 or 82/18 phase values
   are emitted and terminal completion waits for archive/sidecar/manifest verification plus any
   required project recovery-evidence update.
   Create and deduplicate a multi-gigabyte Time Machine snapshot. Confirm both routes retain one
   stable measured total across all three real byte phases, remain monotonic, and withhold 100 until
   the snapshot receipt exists. Restore a different working baseline and confirm its selected-source
   hash, before-state hash, full safety snapshot, copy, temporary hash, post-restore hash, working
   record, and both restore receipts are covered by one stable measured total; a failed hash or
   receipt write must stop without displaying terminal completion.
   For local snapshots, inject extra/oversized/symlinked records, a symlinked snapshot directory or
   artifact, same-size content tampering with restored mtime, a redirected working-copy target, a
   changed pre-restore safety snapshot, and hostile restore receipts. Confirm UI planning performs
   no content hash, legacy restore stays disabled until background verification, and the restore
   worker rehashes before any canonical local-baseline replacement. Confirm snapshot verification
   and multi-phase restore publish monotonic measured percentages through the shared bounded relay
   and matching Live Console missions. Confirm producer failure cannot become success, terminal 100
   follows the strict receipt, and raw local failure paths, hashes, or identifiers never enter the
   Live Console ledger. Confirm
   every Forge Control worker through source blueprint, rebuild inputs, local candidate, AVB
   topology, offline-signing export/import, recovery evidence, and backup creates one running Live
   Console mission and relays only genuine coalesced progress when available. Success must require
   the exact typed terminal receipt. Inject an arbitrary completion object and a failure string
   containing an absolute path, hash, and serial; the former must become failure and none of the
   private text may enter the shared console ledger. Confirm
   Partition Atlas begins payload scans, opaque extraction, and filesystem expansion indeterminately,
   switches extraction to a percentage only after genuine output-byte verification begins, and
   clears the bar on success or safe failure. Confirm fastboot super normalization and LP extraction
   emit no fixed 4/32/72 milestones; after outputs exist they must use one stable cumulative image-
   byte total and reach terminal completion only after the source-bound unpack receipt is stored.
   For Nebula Debloat, confirm unknown-size tree discovery and nested payload/LP/filesystem
   materialization remain indeterminate even when nested tools emit their own unrelated milestones;
   once the complete candidate set exists, app-record cataloguing must publish monotonic count-based
   progress and reach 100 only after scan-evidence persistence. Confirm the mixed full-tree
   revalidation, rollback snapshot, removal, and receipt transaction remains indeterminate until its
   real terminal receipt, including the keep-every-app route.
   For project provenance, alter a valid schema-two manifest without updating its digest; add fields;
   oversize or symlink the manifest; link an entire project directory; redirect the protected original
   or working baseline; pre-plant a linked content-addressed destination; and mutate the selected source
   during copy. Confirm bounded project discovery hides rejected records, partial imports are removed,
   the external source is never overwritten, private records remain `0600`, and genuine schema-one
   project/working-copy fixtures upgrade only at their documented verified save/hash boundary.
   Confirm the combined Firmware Import/Automatic Detection worker begins indeterminately, relays
   only genuine protected-source copy percentages below completion, emits no fixed 68% handoff, and
   reaches 100 only after the saved inspection report exists. Standalone inspection must likewise
   withhold hash completion while its metadata pass runs and complete only after report persistence.
   For inspection/extraction, alter every valid schema-two top-level and nested field without
   resealing it; add fields; oversize or symlink the report; substitute source name/hash evidence;
   inject a linked final tree, special/encrypted entries, output beyond inspected size, and a source
   mutation during scan or copy. Confirm rejected/legacy reports are regenerated only after source
   verification, partial staging is removed, final tree paths remain contained, and published tree
   directories/files use `0700`/`0600` modes on POSIX. Confirm isolated-tree preparation begins
   indeterminately during source/report/budget preflight, emits no fixed 15% handoff, then uses one
   stable byte total with exact extracted/copied output progress below completion. Terminal 100 must
   occur only after the staging directory is atomically published, and any failed partial staging
   directory must be removed.
   For Recipe execution, confirm approval/tree/snapshot and final-tree hashing phases remain
   indeterminate, no fixed 3/25/95 milestones are emitted, multi-step runs expose only genuine
   completed-step counts below completion, and terminal 100 occurs only after the private project-
   level execution receipt is stored. A failed step must restore its verified snapshot without a
   success event.
10. Exercise Forge Arsenal from a clean host with managed-only, Ubuntu-authorized,
    Fedora-authorized, mixed, and
    manual-only plans. Cancel the authorization prompt; inject network, timeout, malformed
    archive, hash-mismatch, and partial-install failures; tamper with every managed executable;
    and confirm Genesis remains blocked until a fresh complete verification succeeds. Confirm
    repeated setup is idempotent and never installs packages outside the allowlist.

    Current Linux development evidence: repository tests cover managed, Ubuntu and Fedora
    allowlists, distro-specific argument arrays, unknown-distro fail-closed planning, manual plan
    separation, and authorization denial; malformed/path-traversing
    and ambiguous archives; pinned digest failure with preservation of the prior install; executable
    tampering; strict receipt shape/source/type rejection; canonical-directory rebinding; redirected
    and linked storage; linked package directories; unapproved resealed file sets; candidate floods;
    idempotent activation; and removal of stale managed `PATH` entries after post-activation
    tampering. New installs use private directories, executables, and atomic receipts. The current
    user workspace's AVBTool, Payload Dumper, and pinned AOSP partition-tool receipts also reload
    through the production verifier. Repository tests also confirm content-length-bound official
    downloads expose their real byte counts, pinned multi-file downloads expose actual completed
    files, duplicate percentage callbacks are coalesced, and lookup/verification phases return to
    an indeterminate bar instead of presenting fixed stage estimates. Clean-host
    administrator-prompt, outage, and multi-host runs
    remain required before public release; this is development evidence, not independent certification.
11. Exercise Companion cache cleanup with recent files, stale files, symlinks, oversized files,
    post-preview mutation, cancellation, storage failure, and receipt tampering. Confirm only exact
    unchanged stale files under the app-private cache are removed and every evidence failure remains
    visible.

    Current JVM development evidence recorded on 2026-08-30 covers recent/stale selection, linked
    roots and files, an after-preview file-to-link swap, oversized sparse files, path traversal,
    root rebinding, content changes with restored size and timestamp, cancellation/invalid UI states,
    receipt storage failure after a genuine deletion result, simple receipt tampering, and a correctly
    re-digested altered receipt identifier. Receipt reads are byte-bounded and result invariants are
    re-derived. A receipt failure now ends in `FAILED` and uses an explicit evidence-failure headline,
    never `COMPLETE`. Physical Android storage-denial and cancellation testing remain required.
12. Exercise Ascension official-manager acquisition against current stable Magisk and KernelSU
    releases with the production APK verifier. Confirm exact GitHub repository/tag/asset binding,
    published SHA-256, package identity, and pinned Android signer. Simulate provider outage with a
    fresh and a 31-day-old cache, corrupt the freshness receipt, and inject invalid metadata, URL,
    digest, APK, and signer evidence. Only the fresh connection-failure cache case may continue, and
   it must remain visibly marked as pending online freshness with execution authority `none`.
   Confirm a 99.5% declared-byte transfer remains below 100 and terminal progress is not emitted
   until APK structure, package identity, pinned signer, private vault permissions, and the strict
   artifact receipt have all been verified and stored.

   Current Ubuntu development evidence recorded on 2026-08-31: the production verifier resolved and
   downloaded Magisk `v30.7` and KernelSU `v3.3.0` from their exact official GitHub release paths,
   matched GitHub's published sizes and SHA-256 digests, decoded the expected Android package names,
   and matched both pinned complete signing-certificate digests. Reload passed from contained `0700`
   tag directories with `0600` APK/receipt files. Repository tests additionally cover typed outages,
   fresh/stale/legacy cache behavior, trust failures, strict receipt tampering, redirected/linked
   storage, candidate floods, and exact-vault rebinding. This is current Linux development evidence,
   not independent multi-host release certification. Route and exact-kernel support tests also
   cover private bounded storage, links, redirected directories, oversized or extra-field input,
   and correctly re-digested Boolean type confusion. The same hostile cases are exercised across
   the root plan, Guardian manifest, final handoff, and short-lived consequence review, including
   private history copies and restoration only from current dependencies. The upstream rollback,
   patch-capsule, patched-image, integration transaction/receipt, rollback snapshot, and build-seal
   tests now cover the same private modes, byte bounds, exact shapes, links, redirected directories,
   extra fields, and correctly re-digested primitive-type substitution. An unsafe interrupted
   transaction stops before changing the isolated input, and receipt-commit failure restores the
   pristine image. Phone-preparation, installed-Manager-open and filename-only output-discovery
   tests exercise private latest/history copies, exact shapes, byte bounds, links, extra fields and
   re-digested Boolean substitutions while keeping later execution authority absent. Repository UI
   tests verify that Manager
   acquisition cannot start before AAPT2/APK Signer resolution and that one contained payload resumes
   its exact scan after Python/Payload Dumper resolution. Safe fastboot archives and named Android
   boot images enter isolated-tree preparation automatically, while traversal archives and renamed
   boot binaries without partition-role evidence do not. The KernelSU app-only support preflight now
   runs Manager hashing/container inspection off the UI thread with monotonic measured progress,
   revalidates the exact phone/release/path before consent, and keeps the actual ADB install visibly
   indeterminate because it has no trustworthy percentage. Repository service and UI tests now
   confirm that the subsequent Manager install, pristine-image transfer, installed-APK retrieval,
   signature verification and Manager launch publish no fixed milestone percentages, keep the
   visible bar indeterminate, and still require genuine terminal receipts. Physical transfer,
   launch, approval-cancellation, and disconnect behavior remains part of the release-device pass.
   Repository tests also cover automatic phone-output retrieval and manual patched-image import:
   the ADB/lineage phase begins indeterminately, the protected local copy and independent hash use
   monotonic measured bytes, and success reaches 100 only after the actual vault operation and
   strict receipt commit complete.
   Patch-capsule tests likewise confirm that pre-copy trust validation remains indeterminate and
   that pristine boot-target plus official-Manager copy/rehash work uses monotonic byte-derived
   progress, preserves verified content-addressed reuse, and never changes the phone.
   Local-integration service and UI tests confirm that safety revalidation begins indeterminately,
   six complete pristine/snapshot/patched/integrated byte passes then publish monotonic measured
   progress, and 100 is withheld until the strict receipt commit succeeds. Build Seal service and UI
   tests confirm that artifact plus full-tree verification stays indeterminate because the complete
   freeze has no trustworthy bounded total; no fixed stage weights are emitted.
   Ascension UI regressions additionally inject arbitrary terminal objects into Manager-install,
   patch-capsule, phone-handoff, and patched-output-discovery completion handlers. None can create a
   success state; each exact typed completion must match its pending plan and independently reloaded
   persisted evidence. Filename references are recomputed before display. Failure and connectivity
   fixtures include raw local paths and a device serial and confirm those details remain absent from
   every shared Live Console title, summary, explanation, and next action while the local card retains
   the useful diagnostic.

   Ascension journey-progress regressions now verify that the visible bar and Live Console count
   only authenticated checkpoints: a blocked initial route reports `0%`, four current checkpoints
   report `44%`, and a manifest awaiting its final sealed Guardian handoff reports `89%`. Stage
   numbering remains visible guidance but can no longer manufacture progress.

   A read-only physical Xiaomi 17 Pro Max (`popsicle`) preflight on 2026-08-31 also revalidated the
   current OTA source blueprint, SUPPORTED Device DNA identity, exact live codename, bootloader
   observation, Android boot-v4 `init_boot.img` with ramdisk, pristine init-boot and stock-recovery
   rollback evidence, and selected a `verified / ready-local-only` Magisk route with zero blockers.
   Its stored route retained `execution_authority: none`, `phone_changed: false`, and permanent
   relock prohibition. The private vault then independently revalidated Magisk `v30.7` and KernelSU
   `v3.3.0` package/digest/signer receipts. User-data backup remained explicitly ATTENTION and no
   Manager installation, file transfer, patch, root, reboot, flash, wipe, unlock, or relock was run.
   Desktop navigation tests also verify every canonical route and active highlight after the grouped
   Home, ROM Workshop, Device, Guardian & Recovery, Activity & Knowledge, Live Operations,
   Connected ROMVERSE, and System sidebar headings were introduced. Command Deck tests cover all
   twelve approved mission cards in no-project/no-device and active-firmware contexts, verify that
   missing prerequisites remain explicit, and prove Guardian, Link, and Lab shortcuts land on the
   existing canonical pages rather than duplicate implementations. Command Deck telemetry tests
   cover explicit unknown readings, the permanent Guardian boundary, real workspace context,
   complete versus partial evidence coverage, detailed boot/slot facts, and four bounded local
   history graphs. The former duplicate upper System Health gauges are replaced by a Genesis Flight
   Plan whose stage and percentage are asserted against the same evidence assessment used by the
   guided sequence; UI regressions also prove its primary action opens the canonical Genesis route
   and that each battery and thermal gauge appears only once. Nebula Debloat UI regressions
   additionally inject a changed typed scan and a
   changed typed receipt; neither can display or advance unless it exactly matches the pending plan
   and independently reloaded persisted evidence. ROM Studio/Genesis regressions inject an untyped
   terminal object and a changed typed working-copy receipt; both must enter the failure path, emit
   no completion, and preserve the guided error instead of advancing the automatic queue.
   Open a legacy multi-gigabyte extracted project with no tree index and repeatedly refresh ROM
   Studio, Command Deck and Genesis. Confirm each UI refresh uses only the constant-time contained-
   tree check, remains responsive, and labels the detailed inventory as pending. Then run build
   planning on its managed worker and confirm a private digest-checked index is created from the
   fresh complete enumeration; add or remove an input before replanning and confirm the plan and
   refreshed index both follow the real tree rather than the previous display cache.
   Guardian lifecycle regressions confirm a hidden page starts no worker, dirty evidence remains
   pending, a visible page begins exactly one debounced verification, and rapid canonical-route
   navigation leaves no hidden Guardian verifier running.
13. Exercise Companion Vitalis with missing temperature/network/USB data, critical evidence plus a
    missing signal, contradictory schema-four scores/states/coverage, stale replays, future clock
    skew, malformed numeric and Boolean fields, reset pairing, and a physical Link reconnect. Confirm
    partial evidence never becomes `OPTIMAL`, a known critical condition remains prominent, Desktop
    independently re-derives the result, and no health payload grants execution authority.

    Current JVM/Desktop development evidence recorded on 2026-08-30 covers complete healthy input,
    missing temperature, known high temperature with another missing signal, readings older than two
    minutes, extreme future timestamps, altered score/state/coverage, incomplete resource pairs,
    wrong field types, authenticated schema-four round-trip, and transport-level replay rejection.
    Schemas one through three remain structurally readable. Android 15 / API 35 emulator evidence
    covers Home, Link, Live Console, Vitalis, Lifeline, Launchpad, Members, Galaxy, Settings, About,
    compact and landscape layouts, About-route restoration across Activity recreation, guarded
    back navigation, and emulator-safe identity that cannot masquerade as a physical Google device.
    The app process remained alive with no app-scoped error log after the paced route run. Physical
    clock-skew, reconnect, storage-permission, manufacturer-specific, and long-running Android
    validation remain required before public release.

    The repeatable connected Android gate now passes all 11 tests with zero skips on the Android
    15 / API 35 ROMVERSE emulator: single Home and single connectivity-status ownership, the complete
    primary navigation shell, truthful emulator identity, About and official Facebook/Reddit actions,
    About-route persistence across Activity recreation, Guided evidence reveal plus Expert
    evidence-open behavior after recreation, Android-Keystore credential round-trip,
    one-way legacy migration, tamper rejection, and the contained TLS-pinned Desktop Link fixture.
    The fixture approved one short-lived request, delivered schema-six Live Console/Device DNA,
    received two fresh health snapshots, and restored the encrypted remembered session after Activity
    recreation with execution authority `none`. This automates the stable runtime contract but does
    not replace the remaining physical-hardware checks above.

## Honest feature boundary

The current safe milestone supports read-only Android evidence, local diagnostics, guarded APK
installation, contained ROM workspace operations, exact-contract local ROM candidate builds,
local recovery snapshots, offline Galaxy data, and read-only Companion telemetry. Public release
still requires independent validation of every advertised build contract. Signing, full app-private
phone backup/restore, public Galaxy synchronization, and device flashing must remain visibly locked
unless their exact contract is implemented and independently verified with real compatibility and
recovery evidence. The offline signing ceremony is implemented for an explicitly flash-validated
Device Pack policy; it does not make any current or future Pack production-certified.
