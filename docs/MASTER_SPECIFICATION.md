# ROMVERSE Master Specification v1.0

Status: active release-candidate development; Desktop and Companion vertical slices implemented
Product owner/creator: SteveTheRad  
Studio: RadForge Labs  
Tagline: **Build. Optimize. Perfect.**

## 1. Product definition

ROMVERSE is an online-first Windows, Linux, and Android ecosystem that makes advanced
Android diagnostics, repair, optimization, device management, and ROM development
accessible through a polished interface. Powerful operations are mediated by Guardian.
ROMVERSE intelligence uses verified connected services for current tools, firmware metadata,
signed Device Packs, compatibility rules, recovery routes, fixes, and Galaxy community data.
Content-addressed local caches allow an interrupted process to resume without changing its plan.

The core audiences are everyday users seeking repair help, enthusiasts optimizing a
device, modders changing firmware, ROM developers, and professional technicians. The UI
will progressively disclose complexity through two coherent experiences: **Guided Mode powered by
ROMVERSE Arcana** and **Expert Mode with the Architect workspace**. They use the same projects,
evidence, and Guardian rules; the difference is presentation density and control depth, never a
safety bypass.

## 2. Product family and bounded contexts

- **ROMVERSE Desktop**: Windows/Linux shell, projects, device workflows, diagnostics,
  repair, ROM tooling, backups, and build orchestration.
- **Guardian**: independent policy and evidence layer for compatibility, risk, battery,
  partitions, hashes, boot state, backups, recovery readiness, approvals, and verification.
- **Companion**: Android client for local device status/diagnostics, secure Desktop pairing,
  integrity-checked build monitoring, notifications, and approved APK transfer/install flows;
  broader production services remain gated by their exact evidence and backend contracts.
- **Galaxy**: optional online services for updates, firmware discovery, compatibility
  intelligence, Device Packs, Recipes, plugins, sync, and community. Never required for
  basic local operation.
- **ROMVERSE One**: future intent/planning interface that converts natural-language goals
  into reviewable workflows; it never bypasses Guardian.

Extensible domains include Recovery Bay, ROM Intelligence, Universal Android Repair,
Autonomous Repair, Battery Lab, App Compatibility Lab, Performance Autotuner, Recipes,
ROM DNA/Carry My Mods Forward, Personalization Studio, Custom ROM Creator, Lab/SimBoot,
Project Time Machine, licensing, Academy, SDK/plugins, and reproducible `.romverse`
projects.

## 3. Non-negotiable principles

1. **Safety is an architecture, not a warning dialog.** Dangerous actions follow:
   Inspect → Simulate → Guardian → Backup/Recovery Check → User Approval → Execute → Verify.
2. **Evidence before claims.** Explain what was observed, what it implies, confidence, risk,
   limitations, and verification. Simulation never guarantees physical boot success.
3. **Online intelligence, locally proven.** Connected evidence enriches each workflow, while
   exact local source hashes and receipts decide what may execute. Network loss never weakens
   Guardian or silently changes an active plan.
4. **Originals are immutable.** Imported source ROMs are protected; mutations occur only
   in working copies with provenance and hashes.
5. **Multi-OEM by design.** Generic Android facts live in core models. Xiaomi/HyperOS,
   Samsung, and future OEM knowledge arrives through signed, versioned Device Packs.
6. **Least privilege.** No implicit elevation. Commands use explicit arguments, timeouts,
   bounded output, audit events, and a single execution gateway.
7. **Privacy by default.** Serial numbers and other identifiers are masked in UI/logs;
   diagnostics exports require review and redaction.
8. **Honest limitations.** ROMVERSE cannot promise repair of physical damage or bypass OEM
   security, encryption, unlock, wipe, or service-tool requirements.

## 4. v0.1 milestone scope

The first usable slice proves the foundation end-to-end:

- branded PySide6 desktop shell with dark purple/blue/cyan visual language;
- first-run setup and non-invasive tool verification;
- deterministic workspace initialization;
- platform abstraction for Linux and Windows paths/tool discovery;
- automatic ADB USB discovery and manual refresh;
- Device Portal showing connection/authorization, manufacturer, model, product/codename,
  Android release/API, build fingerprint/ID, ROM display, security patch, ABI, battery,
  storage, bootloader lock/verified-boot signals, root signal, and masked serial;
- Guardian classification and deny-by-default policy between requested operation and the
  subprocess executor;
- unit tests using fake runners; no physical device required.

Explicitly excluded: fastboot execution, flashing, unlocking, rebooting, installing APKs,
file transfer, root acquisition, recovery changes, ROM extraction/building, automated
repair, telemetry, accounts, licensing enforcement, and Galaxy networking.

### Read-only diagnostics increment

Milestone two begins with deterministic analysis of Device Engine snapshots. Each finding
contains a severity, plain-language explanation, references to the exact observed evidence,
conservative guidance, and limitations. Initial generic signals cover ADB availability,
battery level and temperature, storage pressure, security-patch age, bootloader/Verified
Boot posture, root ADB identity, and incomplete probes. These thresholds are prompts for
review rather than diagnoses or repair guarantees.

Users may explicitly save a JSON report under `diagnostics/history`. Saved reports exclude
raw serial numbers and build fingerprints. A random per-workspace secret derives a stable
local pseudonymous device key; this permits history correlation without persisting the raw
identifier. No report is uploaded and no automatic repair follows a finding.

The Health Timeline UI validates stored schema/privacy markers before display. It compares
only reports carrying the same local pseudonymous device key, showing health-signal score
movement and added/resolved finding IDs. Invalid, corrupt, unsupported, or unredacted
files are ignored rather than rendered. History remains a review aid, not a repair trigger.

### Guardian audit increment

Every request crossing the execution gateway produces one local audit record containing
the typed operation, policy decision, redacted command, result code, timeout state and
duration. Standard output and error are never persisted. Device targets use the same
workspace-local pseudonym mechanism as diagnostic history, while `adb -s` arguments are
replaced with a redaction marker.

Audit records form an append-only JSONL sequence linked by SHA-256 hashes. Guardian checks
the full chain before process creation; schema, sequence, previous-hash or record-hash
failure blocks the gateway. Guardian Core displays integrity state and recent decisions.
When a verified active ledger reaches its bounded capacity, ROMVERSE moves it byte-for-byte
into a bounded archive and starts a new active chain with a rollover receipt containing the
archived record count, prior chain tail, and full-file SHA-256. Verification follows those
receipts recursively and detects an archive change in the same running process. A legacy
oversized ledger is migrated only after its complete chain validates under separate bounded
recovery limits; malformed, tampered, redirected, missing, or excessively large history still
fails closed before process creation.
This provides tamper evidence, not absolute protection against an attacker who can replace
the whole application and audit history together.

### Guardian Preflight and repair assessment increment

Recovery Bay can construct a typed, immutable operation manifest from a selected concern
and the current Device Engine/Diagnostics evidence. Manifests contain required
preconditions, categorized steps, purposes, expected effects and reversibility statements.
A canonical SHA-256 digest detects any change between review and later approval.

Quantum Optimizer may route its exact highest-priority actionable finding ID to Recovery Bay.
The handoff must use a deterministic finding-to-concern map and must be accepted only when the
same finding exists in Recovery Bay's current independently derived report. The selected plan must
show the diagnostic source identity and an explicit no-action-started boundary. Unknown or stale
findings fail closed without navigating to a fallback concern, starting a session, launching a
worker, researching remotely, or requesting approval. Recovery Bay must provide a reversible source
action that returns to Quantum Optimizer and visibly focuses that exact finding in the unchanged
current report. A stale reverse handoff must stay on the current page and request fresh evidence.
Forward and reverse refusal must also persist a visible in-page explanation on the initiating page;
optional Desktop toast settings may add secondary feedback but cannot be the sole failure surface.

Guardian Preflight returns Ready, Review or Blocked plus the maximum risk, reasons and
approval requirement. A failed required safety condition is a hard stop. Unknown required
evidence, advisory findings, and future state-changing, privileged, or destructive steps enter
Review instead: every applicable consequence must be shown plainly and accepted against the exact
current plan before a supported gateway can proceed. Advisory acceptance can never override a
wrong target, altered artifact, rollback violation, or other failed required condition. All v0.1
preflight outcomes keep generic device repair locked until that operation has its own typed, tested
execution contract; the three-level model prevents that implementation boundary from becoming a
permanent blanket ban.

The first such contract is Recovery Autopilot's host ADB daemon recovery. It is offered only
for an offline or failed ADB state, binds approval to the exact ADB executable SHA-256 and plan,
allows only host `kill-server`, `start-server`, and the read-only `devices -l` verification,
records no device-list output, and writes a tamper-evident receipt stating
`device_commands_executed: false`, `phone_changed: false`, and `bootloader_relock: never`.
If stopping the daemon returns failure, ROMVERSE still makes the bounded start attempt. A healthy
daemon is left alone, and an unauthorized phone remains an explicit on-device user action.

When a real warning/error exists, Recovery Bay may automatically research a privacy-scrubbed
fingerprint through the configured online remediation providers. The UI must show source authority,
freshness, scope, corroboration, confidence, and its reason; a result received after online research
is disabled is discarded. Remote text cannot become an operation. Only an allowlisted built-in
typed action with a successful integrity-bound local receipt may create a verified-fix outcome,
and those outcomes are restricted to host/read-only work with `phone_changed: false`. Outcome
schema two must bind the candidate to the exact persisted error fingerprint and revalidate a
workspace-relative, format-specific ADB-host, exact-toolchain, OTA-source, or AVB evidence file on
creation and load. A digest-shaped value or legacy schema-one outcome is never sufficient proof.
The online-research surface is secondary to local assessment: its disabled state remains a compact
discoverable row, while active, returned, or failed evidence expands automatically. Folding research
details is presentation-only and cannot clear, accept, retry, promote, or otherwise mutate evidence.

The ranked receipt must also produce a deterministic Smart Solution Brief. It must distinguish no
match, locally verified typed outcomes, an available built-in typed action, official guidance,
reported community/maintainer risk, independently corroborated hypotheses, single-source community
hypotheses, and discovery-only results. The brief must explain the lead evidence and one next safe
move in plain language, display the strongest alternatives, and enter the privacy-safe report. A
reported harmful result can only increase caution. Receipt revalidation and current typed-outcome
verification are required immediately before display; failed revalidation must remove the proposed
solution. Every state retains guidance-only authority and `phone_action_allowed: false`.

If and only if the current lead is official/maintainer evidence with a registered typed local action,
the Brief may offer one built-in workflow handoff. Recovery Bay and the application shell must each
revalidate the persisted fingerprint, receipt digest, lead source, authority, action, and synthesized
state. Host ADB review remains local to Recovery Bay; Platform Tools opens a host-only Forge Arsenal
context; payload, OTA-source, and AVB reviews bind the currently selected project and protected-source
SHA-256 before Forge Control opens without Autopilot. The destination highlights a local typed action
but does not invoke it. Unknown IDs or changed receipt, ranking, project, or source evidence must stop
visibly, and navigation grants no install, project-worker, build, signing, approval, flash, wipe,
reboot, relock, or other phone authority.

Guided repair sessions persist a pseudonymous initial evidence digest, health signal score,
finding IDs, and the user's reviewed checkpoints. Checkpoints record review only and never
assert success. Verification always requests a fresh read-only Device Engine scan and
compares it with the baseline, reporting improved, unchanged, or needs more attention.
Current session evidence uses a strict private schema-two record with bounded fields and size,
stable article identities, derived resolved/added finding sets, derived direction, and a complete
content digest. Linked, non-regular, oversized, extra-field, wrong-type, duplicate, altered, and
semantically false re-digested records fail closed. A valid legacy record may be read for continuity
but cannot contribute learning until an intentional update rewrites it in the current format.
Archives may aggregate only current integrity-verified comparisons for the exact recommended article
and must label the result local correlation rather than causal or verified-fix evidence. No serial,
raw symptom, unrecorded action, approval, or execution authority enters that memory. Sessions do not
execute device-changing operations.

Recovery Bay exact-symptom input and Quantum Optimizer findings hand off to ROMVERSE Archives through
stable structured article identities. The deterministic Advisor maps typed repair concerns and exact
diagnostic finding IDs, distinguishes unauthorized/offline/no-device ADB states, and permits a symptom
to outrank a generic concern only when the complete bounded phrase matches a structured article. When
Device DNA identifies a supported manufacturer family, the Advisor must add that family's exact
source-backed OEM guide before the generic concern fallback. That match improves diagnosis and route
selection only: it cannot prove firmware compatibility, select an artifact, or grant repair authority.
Recovery reports retain article key, title, selection reason, source authority, and automation
boundary without retaining extra raw symptom data. Manual and ROM Studio stage searches remain
bounded, local, ranked, category-aware, and fail closed for weak or unknown queries while preserving
their draft and stage. Structured known-fix records must expose meaning, checks, safe fix steps,
verification, evidence basis, automation boundary, canonical Desktop destination, and source
authority. A recommendation, source link, or historical field result is guidance evidence only and
never provides Guardian approval, device identity, compatibility, build readiness, or execution
authority.

Archives must visibly separate official/OEM/AOSP sources, maintainer/community reports, ROMVERSE
field evidence, and local-only guidance. Outbound controls must name the actual lane—official source,
maintainer source, or community report—and exact workflow handoffs must reset stale manual filters
before selecting the requested article. Maintainer and community reports may contribute diagnoses,
negative results, and candidate verification steps, but remote instructions cannot become commands or
set a solution to verified working. Only a matching typed local action plus integrity-verified outcome
may promote a fix, and it remains bound to that exact error and device/build scope.

Companion implements the same pattern using Android app-private storage: a real local safe
diagnostic becomes the baseline, safety checkpoints persist across restarts, and verification
re-runs local telemetry before comparing score and finding sets. The result is evidence, not
a repair guarantee, and no system setting or other application is changed.

Recovery comparison semantics are isolated from Android UI code and covered by JVM unit
tests. A new finding cannot be presented as improvement when the score is unchanged, invalid
scores are rejected, and identical baselines are explicitly reported as unchanged.

### Device Pack increment

Device Atlas presents versioned schema-validated OEM metadata bundles. Built-in Generic Android,
Xiaomi/HyperOS, Samsung/One UI, Google Pixel, OnePlus/OxygenOS, OPPO/ColorOS, realme UI,
Nothing OS, Motorola/Lenovo, Sony Xperia, vivo/iQOO, ASUS/ROG Phone, HUAWEI, and HONOR Packs
declare matching criteria, capability status, scope, limitations, authoritative references, and
future boundaries. Matching uses explicit priority with Generic Android as the lowest-priority
fallback, preventing one OEM's assumptions from entering the core Device Engine.

Bundled file bytes are checked against a SHA-256 index before parsing; altered or invalid
packs are excluded from matching. This is package-integrity checking, not publisher
authenticity. Future downloaded packs require signed manifests and trust/revocation policy.
No pack contains command definitions, grants execution authority, or bypasses Guardian.

Desktop Device Engine additionally records the live Android retail brand. Device Atlas may refresh
Google's public supported-device CSV from the one fixed official endpoint and cache it under a
bounded private SHA-256 receipt. Recognition requires the exact OEM-reported retail-brand/device
pair; model can narrow variants, but marketing name, model, device codename, row order, or popularity
alone cannot decide an ambiguous identity. Remote catalog data is identity-only context: it can
select a retail name and improve Pack discovery, but cannot create or strengthen a firmware digest,
build contract, partition-write contract, physical attestation, Guardian approval, or execution
authority. Unknown or conflicting devices remain explicit and build/flash locked.
Catalog refreshes are validated in memory before activation. Withdrawing online-source permission
cancels a pending worker and prevents a late result from being committed, while prior independently
verified local evidence remains searchable read-only.

Device Atlas deterministically selects one next safe action from the exact current validation
report. Every handoff binds the report digest, selected check, route, and exact Archives article
identity where applicable. Build locks route to verified guidance; a build-ready but stock-
recovery-locked Pack routes to Time Machine with the Pack/report context; a fully ready Pack routes
to ROM Studio. Time Machine requires an existing protected-firmware project before external stock
evidence can be enabled and otherwise routes visibly back to ROM Studio. Readiness reports publish
deduplicated genuine Live Console evidence with Device Atlas as the canonical source. Navigation
grants no build, flash, approval, worker, or execution authority.

A ROM Studio → Device Atlas handoff scopes the Automatic Requirements Blueprint to the exact
selected project when a strict source-intelligence receipt is current and its manufacturer/codename
matches the connected phone. The Build lane may then report a verified project-local OTA,
fastboot-super, or partition-bundle baseline, and Compile derives the narrow ordered tools for that
same source. Both routes revalidate and return to the exact project/source/blueprint/plan identity.
This does not upgrade the phone's Device Pack: without an independently source-matched recovery,
AVB, physical-test, publisher, and partition-write contract, Flash remains locked. If the manifest,
source tree, receipt, build identity, or phone target changes, the retained route fails closed and
must not fall back to requirements from a different Pack build.

### ROM project provenance increment

ROM Studio creates project directories containing a private atomic, versioned `project.romverse`
JSON manifest. Schema two binds the exact manifest body to a SHA-256 digest and strict field shape.
A project records its stable ID, timestamps, associated Device Pack and at most one protected
original artifact. Project enumeration is bounded, linked project directories are ignored, and
manifest artifact paths are validated to remain inside the workspace Original ROM store. Valid
schema-one history remains readable and upgrades on the next successful project save.

Original import is explicit and non-blocking to the UI. ROMVERSE checks available disk
space, streams the selected regular file to a temporary workspace copy while calculating
SHA-256, flushes it, atomically moves it to a content-addressed filename, then marks the
copy read-only. The external source is never modified. Identical content is deduplicated;
existing content must pass full hash and size verification before reuse. Partial imports
are removed on failure. A selected symbolic link, a pre-planted linked/non-regular destination,
or a source whose size, modification time, or identity changes during the copy fails closed.
Users can recompute integrity later.

The isolated baseline uses a canonical project path and a private atomic schema-two working-copy
record bound to its project, protected-source digest, path, size, modification time, content hash,
and record digest. Linked paths, oversized or extra-field records, and redirected artifacts are
rejected. A valid schema-one working-copy record remains readable but upgrades only after the
baseline receives a stable full hash while a Time Machine snapshot is created. None of these local
provenance records grants device-operation authority.

### Read-only ROM structure inspection increment

After re-verifying the protected original's SHA-256, ROM Studio may inspect outer container
metadata on a background worker. Signature detection covers ZIP, TAR, Android sparse
images, Android boot images, update payloads, vbmeta, ext4, EROFS and unknown/raw binaries.
ZIP/TAR inspection inventories entry counts, declared expanded size, common Android
partition filenames and OTA metadata paths without reading entry contents or extracting.

The bounded inspector stops at 100,000 archive entries and records unsafe absolute or
parent-traversal paths, symbolic/hard links, encrypted ZIP entries, extreme compression,
corruption and incomplete coverage. Results are persisted as a versioned
`inspection.romverse` report tied to the original name and SHA-256. Schema two has an exact record
digest, strict nested shapes, a one-MiB read/write boundary, private atomic persistence and linked
record rejection. Schema one remains readable for history but is regenerated after original
verification before extraction. An integrity mismatch or source identity change blocks the
operation. Detailed findings are capped at 250 plus one truncation marker, individual text fields
are bounded, and recognized metadata signals use a fixed vocabulary, bounding hostile-report
growth. A clean structural result is not proof that firmware is compatible or safe.

Extraction independently rechecks entry count, paths, links, encryption, special entry types and
declared/actual output size. It writes first to a unique private staging tree, rejects a linked or
pre-existing final tree, confirms the protected source identity did not change, and only then
atomically publishes the contained tree. Direct partition inputs additionally reproduce the exact
protected-source SHA-256. No inspection or extraction evidence grants device authority.

### Guardian-approved APK installation increment

App Launchpad is the first enabled state-changing workflow. Selection performs a bounded
ZIP/APK structure inspection, streams SHA-256, and records manifest, DEX, signature-metadata,
entry-count, battery, and free-space evidence. Approval is bound to the immutable manifest
digest and a workspace-private pseudonym for the exact selected device. The raw serial is
held only for the live ADB request.

Immediately before execution, ROMVERSE re-hashes and re-inspects the APK. Guardian permits
only the exact shell-free argument vector `adb -s <selected-device> install <approved-apk>`
when its executable, command shape, device binding, plan digest, and approval record all
match. Downgrade flags and all other device-changing commands remain denied. Installation
runs off the UI thread, requires a second confirmation, and writes a privacy-safe result
receipt without command output. ADB's explicit `Success` result is required before the UI
reports completion.

A failed result may retain only one allowlisted Package Manager failure code and a workspace-key-
bound identity derived from the exact install-plan digest; raw stdout/stderr and device identity
remain forbidden. The deterministic Archives Advisor maps that typed code to one structured guide,
refuses unknown or conflicting codes, and revalidates the latest receipt before opening it. Archives
must show a navigation-only return path to the unchanged originating Desktop workflow. Guide or
return navigation cannot create approval, retry an install, start a worker, or change the phone.
App Launchpad content must remain readable through an explicit dark responsive scroll surface.

### Transactional local Recipe execution increment

ROM Studio may execute bounded Recipes only inside a verified extracted working tree.
Supported steps are read-only inspection, atomic file replacement, UTF-8 property editing,
and removal of a contained package/path. Absolute paths, traversal, symbolic links,
unresolved targets, oversized property files, malformed parameters, overlapping parent and
child mutation targets, and more than 100 steps are rejected before mutation.

Approval binds the recipe digest, exact resolved tree root, full deterministic tree hash,
and the content hashes of external replacement inputs. ROMVERSE snapshots every affected
target into a separate Time Machine recipe directory before the first change. Each step is
verified after application. If any later step fails, all affected targets are restored and
re-verified automatically. Successful runs and explicit rollbacks create atomic receipts.
Recipes cannot target protected originals and do not invoke ADB, fastboot, signing, building,
or flashing.

### ROMVERSE Recipe Forge increment

Guided Recipe authoring uses a full-size **Recipe Forge** sequence rather than nested text
prompts. Six stages cover Recipe identity, bounded operation selection, target selection from
a lazy filesystem model rooted at the contained working tree, operation-specific configuration,
Guardian review, and a saved digest receipt. The UI remains responsive for large extracted
trees because it does not eagerly enumerate every file into a list.

Recipe Forge validates names, contained targets, required file types, replacement sources,
property key syntax, UTF-8 and size requirements, and explicit removal acknowledgement before
review. Existing project Recipes require visible replacement confirmation. Saving creates an
execution-locked manifest only; execution still requires preview, input-bound approval,
automatic affected-target snapshots, post-operation verification, and failure rollback.

Recipe Forge supports multiple bounded steps in one manifest. It rejects duplicate mutations
and parent/child overlaps before saving. Guardian Review renders a bounded read-only change
preview: text property operations receive a unified before/after diff, replacement operations
show source and size evidence, removals show rollback scope, and inspections explicitly report
that no bytes change. Large-file hashing remains deferred to explicit approval so authoring
cannot stall on multi-gigabyte images.

### Payload and Partition Atlas increment

Update-engine OTA projects may scan `payload.bin` with a shell-free `payload-dumper-go`
invocation after the protected source and contained outer tree exist. ROMVERSE hashes the
payload, parses a bounded partition list, classifies ROM-content versus critical boot-chain
and radio partitions, and stores `payload-manifest.romverse`. Selective extraction is
transactional, verifies output hashes, and preserves at least 4 GiB of workspace free space.
Critical partitions are excluded from the recommended set and cannot become filesystem Recipe
targets.

Extracted Android sparse, ext4, and EROFS images may be expanded with verified local tools into
`working_roms/<project>/tree/partition_files/<partition>/root`. Entry count, content size,
symlink containment, source hash, and extractor identity are recorded in per-partition
manifests. Partition Atlas uses lazy filesystem models, allowing users to browse large
trees and hand a selected contained target directly to Recipe Forge. It also exposes a local
source-AVB inspection for `vbmeta` and `vbmeta_system`. This rehashes both images, parses verified
AVBTool output, distinguishes chain descriptors from all other protected descriptors, and persists
a strict source/project/payload-bound receipt. The receipt is diagnostic development evidence only:
it contains no signing key and cannot authorize a Pack or phone action.
Forge Control reuses this source-only service whenever the current Pack lacks an exact contract for
the protected source; an exact contract retains the full source-versus-candidate inspection. The UI
must independently reload the worker's receipt before presenting success, must not advance
Autopilot from source-only evidence, and must preserve explicit zero Pack/signing/flash authority.

### Build Control and evidence gates increment

Build Control derives separate workspace, build, signing, recovery, and flash readiness from
persisted artifacts, tool status, Device Pack capabilities, and live authorized-device
evidence. A local workspace can be ready while build or flash remains blocked. A matching OEM
name is insufficient: the pack must declare a supported build contract, signing inputs must be
complete, and the exact target and recovery path must be evidenced.

The pipeline simulator writes only a local receipt and stops at the first blocked phase; it
never invokes compilers, signers, ADB, or fastboot. Separately, the exact local Device Pack
executor runs only after all Build gates pass, writes to a versioned plan-ID directory, and has
no device transport. It records command logs, output hashes, and byte-for-byte unpacked-super
verification. Source blueprints, local-build and super-verification records, and AVB topology use
bounded private atomic workspace persistence with strict top-level/nested schemas and contained
artifact/log references. New AVB schema-three evidence records image size and modified-time
identity for bounded reload; schema two remains historical evidence and cannot support a new online
verified-fix promotion. An exact flash-validated Device Pack may also authorize the offline signing
ceremony. Its request, external manifest, imported artifact evidence, and local receipt use bounded
exact schemas; workspace state is private and atomic, detached manifests and symlinked paths fail
closed, and private keys never enter ROMVERSE. New signing receipts use schema-two size/mtime
identity after import-time full hashing; valid schema-one receipts are rehashed and migrated once.
Evidence export produces a
content-addressed bundle containing hashes of small project, inspection, payload, filesystem,
Recipe, receipt, readiness, and build-plan manifests plus tool versions. Firmware bytes are
not duplicated. Genesis Sequence consumes the same readiness engine and opens Build Control
at Build & Sign.

### ROMVERSE Genesis Sequence increment

ROM Studio's guided mode is the persistent **Genesis Sequence** rather than a checklist
dialog. Its state engine derives progress from project artifacts, live device state, Device
Pack resolution, Recipe receipts, build-plan evidence, recovery snapshots, and verified tool
status. Saved UI state records navigation and explicit user decisions, but cannot manufacture
completion evidence.

The mission presents fifteen stages: project, firmware, provenance, isolated working lab,
device match and Device DNA, customization, change validation, Nebula Debloat, optional root,
deterministic build planning, recovery, toolchain, build/sign, Guardian flash, and first boot.
Every stage explains its purpose, recommended choice, observed evidence, blockers, and the outcome
that unlocks next. Safe multi-operation stages run sequentially on background workers and
acknowledge loading before allowing navigation.

Large extracted working trees must never be recursively enumerated by a normal Qt page refresh.
Extraction creates a private, source-bound, digest-checked display index on its managed worker;
legacy trees remain immediately navigable through a constant-time containment check and clearly
label an unavailable detailed inventory. The display index grants no build authority. Deterministic
build planning always performs a fresh background enumeration before deriving inputs, partitions,
or hashes, and then refreshes the index from that current scan.

Failures are converted into plain-language diagnoses for low disk space, integrity mismatch,
unsupported containers, unauthorized ADB, unsafe paths, missing inputs, and unknown errors.
Automatic recovery is limited to removing recognized incomplete transaction files inside the
active ROMVERSE workspace. Integrity failures, compatibility gaps, or device-changing actions
are never bypassed or silently repaired. A local build can complete only for the exact reviewed
contract. Exact-contract offline signing is available only when a flash-validated Pack authorizes
its identity; flash and first boot remain Guardian-locked until external device backup, physical
recovery validation, a device-bound manifest, separate final consent, execution, and postcondition
evidence exist.

After the command-free manifest has hash-bound every declared image, Guardian may compile a
separate inert execution-plan preview. The preview rehashes the current artifact binding, remains
bound to the exact project, source, readiness facts, pseudonymous phone identity, Device Pack,
write contract and physical-attestation digest, and derives only bounded Fastboot product,
unlock-state, mode and slot preconditions plus the explicitly declared partition writes. Raw device
serials never enter the saved plan. Workspace and target placeholders keep it non-executable, while
strict reload independently regenerates the expected commands and rejects changed evidence,
unknown Fastboot options, destructive targets, relock language, hostile structure and type
confusion. When a schema-one write contract does not define exact readback or post-boot
postconditions, the plan remains `blocked-missing-exact-post-write-verification` with final consent
unavailable, execution authority `none` and phone changed `false`. Partition-write schema two
defines the next exact contract boundary: one full-partition `fastboot fetch` size and SHA-256 per declared
write, the same source-build and signed physical-attestation digest, authorized ADB, a 30-to-900
second first-boot timeout, and an allowlisted minimum Device DNA set including boot completion,
device, fingerprint, incremental, SDK, security patch and Verified Boot state. Device Atlas counts
this as flash-contract evidence only when all of those facts match exactly; schema one remains
readable but not flash-ready. The inert plan binds the schema-two verification contract's identity,
digest and bounded counts, then advances only to `ready-for-inert-gateway-contract`. That state permits
only regeneration of the separately verified, still-inert gateway/result template. Neither record can
expose final consent or execute a command.

Partition-write schema three adds a separately signed transition/recovery contract. It binds the
same exact source build and physical-attestation digest, a contiguous device-mode chain at explicit
write boundaries, transport-correct Bootloader/Fastbootd states, one final system transition, and,
for slotted writes, one exact final slot activation. Its recovery contract names a bounded adapter,
binds the exact stock source-package SHA-256, declares typed recovery actions and prior-slot capture
where applicable, requires an external backup and stock-recovery evidence, discloses every possible
data wipe, prohibits automatic wipe and relocking, and requires separate final consent while granting
execution authority `none`. The execution plan binds the complete transition/recovery digest and
counts but stops at `ready-for-inert-transition-aware-gateway-contract`: it does not turn those typed
rules into runtime authority. A successful Fastboot response alone must never be presented as a
verified healthy upgrade. A fresh live-target re-identification receipt, immutable execution/postcondition
receipts, a governed runtime, explicit final consent and independent physical validation remain separate
gates.

The next private record is a typed, still-inert execution-gateway contract. It independently reloads
the current execution plan, rehashes its bound artifacts through that plan, and accepts only a
signed schema-two or schema-three verification contract. It expands the preview into exact typed result obligations:
Fastboot variable equality for every precondition, zero exit status for each declared write, one
bounded private `fastboot fetch` output with exact size and SHA-256 for every write, and allowlisted
ADB property equality for every post-boot Device DNA fact. For schema three, it also interleaves only
the signed mode/slot transitions at their exact write boundaries, attaches explicit resulting-mode or
active-slot evidence and timeout obligations, and binds the exact recovery strategy, source-package
digest, adapter, wipe policy and ordered typed recovery actions. Recovery actions deliberately contain
no executable or raw argument vector. Raw serials and concrete host paths remain
replaced by target, workspace and private-output placeholders. Strict reload regenerates every step
from current evidence; changed expected values, extra fields, linked records, type confusion, added
authority, uncontracted options and erase/reboot/unlock/relock substitutions fail closed. This
contract is not an execution receipt: it records `runtime_invoked: false`, `phone_changed: false`,
execution authority `none`, and final consent unavailable. Schema two remains
`blocked-missing-signed-transition-recovery-and-final-consent`; schema three advances only to
`blocked-missing-live-runtime-receipts-and-final-consent`. Neither status authorizes a phone action.

The result side of that boundary is now specified by a strict Ed25519 execution-result verifier.
It accepts no locally asserted success: every imported envelope must be signed by an externally
trusted runtime identity whose raw public-key digest and exact adapter identity/version/digest are
pinned by the caller and scoped to the exact Device Pack, write contract, write attestation and
transition/recovery digest. The signed receipt is bound to the complete gateway, plan, manifest,
artifact, device, Pack, live-target and final-consent digests. The prerequisite record itself must
match the exact gateway and private device key; live-target and consent digests must also equal
independently supplied, pre-verified prerequisite bindings, so the runtime signer cannot invent its
own target or consent authority. Ordered results form an exact gateway prefix and bind each gateway
step digest, bounded timing, exit state, privacy-safe evidence digest and the expected value or full
readback size/SHA-256. A success state requires every step and every postcondition; failure and abort
states cannot skip or reorder evidence. Recovery results are separately bound to the exact typed
adapter actions and a separate recovery-consent digest, while a recorded wipe additionally requires
a distinct wipe-consent digest. Phone-change attempted/verified/uncertain states are derived from the
attempted signed steps rather than trusted as runtime assertions. Canonical JSON, a domain-separated
signature, whole-receipt and per-result digests, exact fields, duplicate-key rejection, bounded regular-
file loading and chronological/timeout checks fail closed. The verifier deliberately contains no
private-key API, runner or execution method, and the Desktop has no enrolled runtime trust; therefore
it can verify future evidence but still cannot execute or fabricate one.

Immediately before any future final-consent or governed-runtime stage, Guardian can now issue one
short-lived local live-target receipt using only its existing allowlisted discovery and Fastboot
identity paths. It requires a complete earlier Android build identity bound to the gateway's private
device pseudonym, exactly one Fastboot target and no simultaneous ADB target, three identical discovery
passes around two identical probe rounds, exact product, unlocked state and Bootloader/Fastbootd mode,
every entry-stage signed `has-slot` requirement, and the current A/B slot when the signed recovery
contract requires prior-slot capture. A disconnect, reconnect token change, target swap, second target,
timeout, missing value, changed value, wrong product/mode/unlock state or incomplete reviewed build fails
closed before a receipt is written. The two-minute receipt binds the exact gateway, plan, manifest,
artifact binding, Device Pack and hashed pre-transition build identity. It stores no raw serial,
fingerprint, stdout or stderr; uses strict bounded regular-file loading with duplicate-key and link
rejection; and records no runtime invocation or phone change. It is explicitly local observation,
not cryptographic device attestation, consent or execution authority. Real-device validation and the
separately trusted runtime remain required.

The next verification-only boundary is a runtime-bound Guardian final-consent receipt. It accepts
only the current schema-three transition/recovery gateway, its independently validated execution
plan, the still-current stored live-target receipt, the same reviewed device, and an externally
supplied runtime public key/trust record scoped to the exact Pack, write contract, attestation and
transition/recovery digest. The user must acknowledge every exact-device, forward-write,
transition, verification, failure-state, recovery-separation, relock-prohibition, expiry and
keep-data/erase-data consequence and type a phrase containing the observed product, final plan
digest segment and explicit data action. The receipt materializes every ordered forward consequence
and every signed recovery consequence, but final consent covers the forward gateway only; recovery
and every possible wipe remain separately unconsented. It expires at the same instant as the
two-minute live-target receipt, stores no raw serial, typed phrase, public key or ephemeral grant
token, and binds only their digests. The raw ephemeral token exists in memory only. A future isolated
runtime must still atomically consume it once; this service deliberately provides no consumption,
signing, command, runner or execution method. Consequently the receipt records runtime trust bound,
final consent recorded, execution authority `none`, runtime invoked `false`, phone changed `false`,
automatic recovery/wipe `false`, and bootloader relock allowed `false`. No production runtime trust
is enrolled, so the shipping Desktop correctly offers no final-consent control yet.

The next runtime boundary is now defined without pretending that a writing runtime exists. Guardian
issues a 45-second local challenge only while the same live-target receipt remains current and binds
it to the exact gateway, private device key, result schema, enrolled runtime public-key digest and
adapter identity/version/hash. A separate runtime instance must return a domain-separated Ed25519
attestation accepting that exact forward-only scope while explicitly denying automatic recovery,
wipe, relock, opened device access and phone change. The first fully valid response wins a
boundary-anchored exclusive claim; concurrent or replayed answers, wrong keys, stale challenges,
changed context, re-signed unsafe claims, duplicate fields, links and tampering fail closed. The
signed envelope is reverified whenever the session is loaded and contains no raw phone serial.

After exact final consent, a second local-only service can exclusively reserve that consent for the
one verified runtime session. Its create-once filename is derived from the random consent identity;
concurrent callers cannot replace it, and the record binds the gateway, plan, target, device,
consent, token digest, session attestation, signer and adapter. It persists no raw token and
explicitly records runtime consumption incomplete, execution grant unissued, execution authority
`none`, device access unopened, runtime uninvoked and phone unchanged. This closes the duplicate
Desktop-side reservation race.

A runtime-only authorization service now revalidates that complete reservation/session/consent
chain, requires the matching externally supplied Ed25519 runtime private key, and exclusively creates
one signed consumption record before returning a new memory-only exact-forward grant. Exactly one
concurrent caller wins. The record binds every upstream digest plus the ordered forward steps and
data action; persists neither raw consent token nor raw execution token; and explicitly denies
recovery, wipe, automatic recovery/wipe, relock, opened device access and phone change. Expiry,
replay, changed context, the wrong private key, re-signed unsafe claims, duplicate fields, links and
tampering fail closed. Loading the record supplies audit proof only and cannot reconstruct its lost
memory token. This is a source/package protocol boundary backed by a private local workspace record,
not protection against an administrator deleting local state and not evidence of process isolation.
A second runtime-only service revalidates that live memory grant, requires the same matching private
key, and create-once signs an exact execution claim before returning a new memory-only target-open
permit. The claim binds the consumption, grant-token digest, first gateway-step digest and transport,
entry mode, product, unlocked state, pre-write slot, Pack, adapter and expiry. One concurrent caller
wins; neither token nor the raw target serial is persisted; and the first bound operation must be a
read-only precondition. Loading the claim is audit-only and cannot recreate its permit. It explicitly
records target unopened, first forward step unstarted and phone unchanged. No production runtime
key/process is enrolled and the Desktop never imports or exposes either signer. A separately
packaged runtime source boundary now consumes that target-open permit through a create-once signed
record before any tool call, revalidates every artifact before device access and immediately before
its write, then requires exactly one freshly discovered matching Fastboot serial. It resolves only
the gateway's exact target/workspace/private-output placeholders, runs the read-only-first ordered
forward prefix, observes signed mode/slot transitions, hashes full private readbacks, verifies
allowlisted post-boot properties, stops on the first failure or operator cancellation, and verifies
its own domain-separated signed result before preserving it. The result and open records persist no
raw serial, raw token, stdout or stderr. The executor exposes no recovery action, automatic wipe,
unlock or relock path; recovery and wipe remain separately unconsented. It is not constructed or
enrolled by the shipping Desktop UI. Separate production packaging and runtime self-integrity,
externally protected/enrolled production keys, OS-level exact-device binding across transport
changes, distinct recovery/wipe consent, hostile-runner review and physical-device validation remain
required before the final-consent control can be exposed.

ROM Studio's managed Guardian review worker carries this inert chain through the actual Desktop
journey. It seals the command-free manifest, independently rehashes the same artifacts for the inert
plan, and, when schema two or schema three is present, rehashes them again before sealing the result template. One
monotonic byte-derived progress scale covers every required full pass; terminal 100 is withheld until
the applicable records are validated and saved. The review dialog presents separate dark, scrollable
cards for exact binding, partition intent, preconditions, signed transitions, immediate readback
sizes/digests, typed recovery contingency, wipe disclosure, post-boot Device DNA and unresolved blockers.
Guardian Core retains the same exact plan/template identities
only while the manifest remains valid. Changed or authority-bearing cached objects are discarded,
and neither surface exposes an execute, flash, consent, transition or reboot control. Both surfaces
state that result-receipt schema two requires an Ed25519 runtime signature plus independently verified
target/consent bindings and that no runtime trust is enrolled.
They also expose live-target check v1 as a read-only, two-minute prerequisite while making clear that
opening a review does not capture a receipt or contact the phone. When the exact gateway, reviewed
Android build identity, ADB and Fastboot runtimes are all present, the manifest dialog offers one
explicitly labelled read-only check control. It runs on a managed background worker, displays the
verified product/mode/unlock/slot scope and expiry, and still exposes no flash, reboot, wipe, unlock,
relock, consent or execution control. A failed retry invalidates the prior short-lived receipt.
The same review now shows a separate final-consent-v1 card. It explains the exact gateway/target/
runtime/consequence binding and changes to a current-target explanation after a successful read-only
check, while remaining visibly locked because no production runtime identity is enrolled. It never
substitutes the live-target receipt for consent and adds no consent or execution button.
For schema three, the same worker performs all three measured full rehash passes and seals the
transition-aware gateway only after the artifact-bound manifest and transition/recovery-bound plan
remain exact. The gateway is still inert and reaches terminal completion only after all fail-closed
records exist.

Time Machine registers independently stored phone backups and exact stock-recovery packages without
copying them into the workspace. Its public-safe evidence and private locator use separate bounded
atomic exact-schema records bound to the project, protected source, Pack, role, size, mtime, and
hash. Legacy schema-one evidence remains inspectable but cannot satisfy recovery readiness until an
explicit full rehash upgrades it to a digested schema-two record.

Forge Control Autopilot resolves recovery in two safe local phases before requesting personal or
externally signed evidence. It creates the missing Time Machine working-baseline checkpoint on a
background worker, then fully rehashes any preserved schema-one recovery record. Irreducible signed
flash certification is deferred until those local phases have run. ROMVERSE still pauses for the
user to choose private backup/firmware files and never treats an unverified file, local checkpoint,
or online recommendation as physical recovery proof.

When final user-data backup evidence is the next unresolved gate, Forge Control opens the established
beginner chooser automatically, with local-drive backup highlighted while verified-file and explicit
cloud-confirmation routes remain available. Completion refreshes the readiness report and resumes
Autopilot; it does not jump directly to Guardian or imply that a backup supplies missing signed Pack,
write-contract, or physical-recovery evidence. Any interim dialog must state that the project is not
yet flash-ready and enumerate the remaining gates.

Local working-baseline snapshots independently use schema-two private atomic records with exact
project/path, size, mtime, SHA-256, and record-digest binding. UI enumeration and rollback planning
remain metadata-bounded; a managed verification/restore worker performs the full content hash. A
restore also proves the pre-restore safety snapshot matches the recorded before-hash, writes only to
the canonical working baseline, verifies the final bytes, and records a strict digested receipt.
Snapshot creation reports one stable measured total across source hashing, copy or duplicate
verification, final hashing, and the evidence commit. Restore reports one stable measured total
across selected-snapshot verification, current-baseline hashing, the full safety snapshot, local
copy, pre-replacement verification, post-replacement verification, and both restore-receipt writes.
Progress remains monotonic and 100% is withheld until the applicable strict receipt is committed.
The standalone Time Machine page and Forge Control guided backup path publish matching privacy-safe
Live Console missions for snapshot verification/restore, local phone-media backup, external backup
registration, and preserved recovery-evidence revalidation. Only coalesced worker percentages enter
the console. Success requires the producing service's terminal receipt; failures retain raw detail on
the local card while the shared ledger records a fixed explanation without paths, hashes, serials,
or other private identifiers. Forge Control applies the same producer-owned lifecycle to firmware
source blueprinting, exact rebuild-input preparation, local candidate construction, AVB topology,
and offline-signing request export/import. Completion handlers accept only their exact typed receipt
classes; an unexpected worker payload becomes a failed mission rather than inferred success.
Ascension applies that producer-owned boundary to official Manager installation, patch-capsule
preparation, exact-phone handoff, and filename-only patched-output discovery. The UI independently
reloads the current persisted receipt and checks its project, method, phone target, source binding,
artifact digest, candidate filename references, no-write state, and execution authority before
advancing. Untyped values and changed or missing evidence stop safely. Detailed diagnostics may
remain on the local Ascension card, but its shared Live Console lifecycle uses fixed privacy-safe
explanations without workspace paths, device serials, or raw provider errors.
Ascension's overall journey progress is derived only from the nine persisted checkpoints that
reload successfully from current evidence. The current stage number is navigation, not completion:
a blocked stage one reports `0%`, four verified checkpoints report `44%`, and a review-ready
manifest without the final sealed handoff reports `89%`. The visible journey bar, checkpoint
tracker, and shared Live Console consume the same value so reopening or losing evidence cannot
preserve a fabricated percentage.

## 5. Functional requirements

### First run and workspace

The setup wizard explains the safety boundary, shows the selected workspace, creates the
standard directories, and verifies Python/ADB without modifying the operating system.

Managed official tool downloads are bounded, staged, archive-validated, and content-addressed.
Receipts retain the official source, archive digest, size, and required-file digests. Managed
executables enter ROMVERSE's process path only after their on-disk hashes match the receipt;
an altered or unreceipted download is not activated.
Initialization is idempotent and writes a versioned manifest. Standard areas are:
`original_roms`, `working_roms`, `builds`, `projects`, `apks`, `backups`, `snapshots`,
`tools`, `device_packs`, `recipes`, `diagnostics`, `logs`, `cache`, and `temp`.

### Desktop navigation and Command Deck

Desktop keeps a permanent grouped sidebar with canonical areas for Home, ROM Workshop, Device,
Guardian & Recovery, Activity & Knowledge, Live Operations, Connected ROMVERSE, and System. Every
existing feature route remains distinct and highlights its own active destination. Guided mode may
fold specialist sidebar entries without hiding Guardian or Live Console.

Ctrl+K opens a keyboard-first, navigation-only command palette populated from that same sidebar
route registry and canonical feature vocabulary. Named nested features resolve through one
authoritative owner map and display their exact current prerequisite inside Command Deck, System
Scan, ROM Studio, Recovery Bay, or Archives without invoking the focused control. This includes
Device Engine, Device DNA, Compatibility Matrix, Pre-Build Simulation, ROM DNA, Boot Observatory,
Recovery Autopilot, ROMVERSE Intelligence, and ROMVERSE Synapse as well as the guided creation
surfaces. Health Review is distinct from starting System Scan, and Expert mode can open Pathfinder,
Foresight, or Insight at the matching current Nexus panel without generating or adapting a plan.
Every visible Command Deck launch-card name also resolves to its canonical destination. Familiar
legacy names remain searchable, while Guided mode excludes its folded specialist destinations and
Expert mode exposes them. Synapse evidence returns to its real Archives owner rather than Nexus.
Live Console and legacy Activity source actions retain the exact producer feature, restore an exact
referenced ROM project before navigation, and invoke the same nested destination resolver without
repeating the operation. An explicit event link may reveal its bounded Architect-only destination
from Guided mode but cannot change the persisted experience mode. Unknown features and stale projects
fail visibly in the originating evidence surface.
The ROM Studio Architect control updates and persists that same Desktop experience. The palette and
mode transition have no operation callback, execution authority, device selector, or approval
surface.

The group/route structure has one authoritative registry shared by sidebar construction, active
selection, command search, and live breadcrumbs. Ctrl+B may collapse the full sidebar into a
permanent icon rail; text remains available through accessible names and bounded tooltips. The
Focus workspace temporarily hides that rail and the connection footer while retaining the exact
page widget and session state. Ctrl+Shift+F toggles Focus, Escape restores the prior expanded or
collapsed choice, and the slim workspace bar keeps page context, connectivity, and visible Ctrl+K
access. These are presentation-only transitions and cannot start work, clear evidence, change a
project, or grant Guardian authority.

Command Deck is the contextual home surface, not a second implementation of those features. It
reads the actual active ROM Studio project and connected-device state, then labels its launch cards
honestly as create/import/continue, needs firmware, connect device, ready, verify required,
verifying, integrity verified, reverify required, or execution locked. Guardian Core exclusively
owns the Guardian card state and its matching in-page handoff; an audit, verified-archive, or
approval-file revision retires a cached green claim before the full background verifier runs. Build
ROM, Pre-Build Simulation, Device DNA, Recipes, Health Review, Repair Phone, Guardian,
Rescue & Backup, Timeline, Live Operations, Wireless Transfer, and ROMVERSE Lab route to their
canonical pages. A missing phone or firmware remains a usable beginner state and never fabricates
readiness.

Repair Phone is evidence-aware rather than a blind page route. Command Deck consumes the same
current typed report and severity-ranked finding-to-concern map as Quantum Optimizer. An exact
actionable match visually promotes and names the topic-specific plan card, then opens the matching
Recovery Bay context. No actionable match opens a labelled general intake. If Recovery Bay cannot
independently re-confirm the selected finding, the intake states that fresh evidence is required and
does not guess a fallback category. All three paths are navigation/presentation only and start no
session, worker, remote research, approval, or phone action.

The upper Command Deck now pairs Device Portal with an evidence-backed **Genesis Flight Plan**
instead of repeating device-health gauges. The Flight Plan is compiled from the same
`GuidedContext` and `GuidedMissionEngine` assessment used inside Genesis Sequence, so its current
stage, verified-stage progress, blockers, root route, recovery checkpoint and Guardian-handoff
state cannot drift into a separate dashboard claim. Its primary action opens Genesis at the first
stage not supported by persisted evidence. A saved Genesis error remains visible as attention and
no absent fact is promoted past unconfirmed.

The lower Command Deck telemetry bay consumes only current read-only device evidence and bounded
local metric history. It presents nullable battery, battery-sensor thermal, memory, storage and
evidence-coverage gauges; Device DNA facts; boot trust, slot, encryption, transport and uptime
details; and battery, thermal, connection and storage history graphs. Missing readings render as a
dash or `UNCONFIRMED`, never zero. Thermal rings disclose their 0–60 °C display scale and are never
described as CPU utilization. Workspace/source readiness and the permanent Guardian boundary remain
useful when no phone is connected, while the history retains at most 30 privacy-reduced scans.

### Device Engine

Discovery combines `adb devices -l` with `fastboot devices -l` when each executable is present in
the verified host inventory. Offline and unauthorized ADB devices remain visible with actionable
state text but are not queried. For an authorized ADB device the engine reads properties, battery,
`/data` filesystem usage, ADB state, and process identity. For a Fastboot device, Guardian permits
only the exact `product`, `current-slot`, `unlocked`, `secure`, and `is-userspace` variable reads;
the latter distinguishes bootloader Fastboot from userspace fastbootd when the device reports it.
Fastboot observations are identity-only and connect to Device Atlas, while Android health fields
stay unknown and no reboot or write command exists in the adapter. Failure of one probe yields
partial information rather than discarding a detected device. Polling is non-blocking to the UI,
duplicate ADB/Fastboot serials prefer the richer ADB snapshot, and multiple devices are modeled.
One visible transport is selected automatically. Two or more require an explicit Command Deck
selection; every device-facing action surface receives only that same selection, and receives no
device until the selection is made. The session-only choice is retained across scans only while the
exact transport remains present.

### Device DNA and Capability Map

Device DNA is the source-bound authoritative project profile consumed by ROM Studio, Genesis,
Compatibility Matrix, Nexus, Ascension, Guardian, and the privacy-reduced Companion view. Its facts,
partition geometry, warnings, evidence and SUPPORTED/CAUTION/UNSUPPORTED/UNCONFIRMED Capability Map
retain explicit confidence; unknown evidence remains unconfirmed.

The generic ADB identity passport records the standard product name, product/vendor device aliases,
hardware and hardware SKU, build ID/fingerprint/incremental/timestamp, Android/SDK/security patch,
ABI, verified boot, slot, dynamic/A/B state, encryption, kernel, platform and health observations
that the device actually reports. Vendor-neutral OTA intake reads only the bounded standard
`META-INF/com/android/metadata` ZIP entry and validates its target, current-build preconditions,
post-build identity, SDK and timestamp against that live passport. The comparison may label upgrade,
same timestamp, downgrade, incompatible, or unconfirmed, but it grants no installation authority.
OEM-specific transport and write protocols remain separate signed adapter/Device Pack work.

Schema-two profiles use a strict nested shape, bounded collections and text, private atomic storage,
an exact profile digest, protected-source binding, typed confidence/state enums, unique identifiers,
and evidence-reference validation. Linked, oversized, extra-field, coerced, malformed, or stale
source records fail closed. Structure facts are taken only from the current persisted schema-two
inspection report or the same strict current project/source-bound source blueprint used by Forge
readiness. That blueprint may reconcile source identity, adapter, tool selection, partition
inventory and bounded local build preparation across both features, while retaining its explicit
local-evidence-only authority and granting no device-write or flash authority. Foreign, stale,
phone-changing, malformed or non-current blueprints are ignored. Valid schema-one profiles remain
readable and upgrade at the next refresh.
`bootloader_relock_permitted` must be false and the `bootloader_relock` capability must remain
UNSUPPORTED even if a modified profile has been re-digested. Device DNA remains advisory and grants
no command or device-changing authority.

The Compatibility Matrix is a separate Device-DNA-bound advisory artifact. Its schema-two private
atomic record has strict nested decision/evidence shapes, bounded collections and text, and an exact
digest. On every load ROMVERSE deterministically re-derives every decision from the current Device
DNA and the saved assessment time; a missing, additional, reordered, stale, or re-digested changed
decision is rejected. Community telemetry remains unused, Guardian advisory mode remains true, and
bootloader relocking remains false. Valid schema-one records upgrade on reassessment only while
their Device DNA digest still matches.

Nexus Plans are strict private atomic schema-two records bound to that current Device DNA and
Compatibility Matrix. On every load ROMVERSE deterministically reconstructs the plan status,
understanding, research requirements, Pathfinder route, Foresight predictions, Insight decisions,
Guardian requirements and flash-mode consequences. Missing, reordered, stale, extra-field,
coerced, linked, oversized or re-digested changed plans fail closed. Execution and bootloader-relock
authority remain false. Adaptation retains only a bounded previous-plan ID and evidence-backed
reason; valid schema-one plans upgrade through fresh replanning.

Before planning, Nexus must visibly distinguish a missing project, missing Device DNA, and missing
Compatibility Matrix. Its exact evidence-recovery handoff opens a structured Archives article or
ROM Studio and must not create a plan, start a worker, infer project evidence from a connected phone
or device catalog, or grant Guardian authority. Desktop-native item views, text editors, and scroll
viewports must retain explicit high-contrast dark surfaces independent of the operating-system theme.

ROM DNA separately binds current project ID, Device Pack association, protected-source hash,
working-tree plan hash and Recipe digest. Its schema-two record is bounded, private, atomic and
digested, but the loader also re-derives current ROM DNA before returning it. Thus a correctly
re-digested stale record still cannot appear verified. Valid schema-one history remains readable
only while all current provenance still matches and upgrades on the next save.

### Guardian

Every executable request has an operation ID, category, arguments, purpose, target,
expected effects, and evidence. Guardian returns allow/deny, risk, reasons, required
checks, and whether approval is needed. The foundation policy permits only known read-only
ADB probes. The expanded policy additionally permits the exact approved APK-install
contract described above; unknown, privileged, destructive, and every other state-changing
request is denied before process creation.

Guardian Core does not start a verifier merely because its hidden page was constructed or rapidly
passed during sidebar navigation. Device-scan changes mark its evidence dirty, and a short
visibility-aware debounce starts background verification only while the page is actually being
viewed. Hiding the page cancels an unstarted refresh; an explicit **Verify audit trail** request is
immediate. This avoids needless worker/page lifetime overlap without weakening any execution gate.

Command Console ADB checks use this gateway rather than a UI-owned process runner. Console
requests target only the currently selected authorized device, are audit-recorded, and mask
the serial in displayed output. Host platform and Python version details are read in-process.

### Truthful local activity ledger

Command Deck recent activity and the canonical Activity Center use an atomic, byte-bounded,
strict-schema local ledger rather than illustrative sample entries. Health Timeline remains the
single surface for saved diagnostic snapshots and health change, rather than duplicating general
activity ownership. Only operations that reached their real completion or safe-failure boundary may
append an event. Entries contain bounded summaries, outcomes, and source modules; raw device serials,
console output, build fingerprints, and user-authored Galaxy content are excluded. Ledger and lock
files are regular-file checked and private, unique staging prevents predictable temporary-path
replacement, oversized/extra-field/linked records fail closed, and unreadable data is never silently
replaced.

Activity Center provides full-ledger search plus category and outcome filters, truthful summary
counts, a readable evidence inspector, privacy-safe JSON export, and canonical source-page handoffs.
Those handoffs navigate only; authoritative receipts, project evidence, Guardian state, and any
operation authority remain owned by the source feature.

ROM Studio owns the terminal boundary for Genesis operations. Each active operation accepts only
its expected typed result, binds it to the exact project that launched the worker, and independently
reloads persisted firmware-import, inspection, working-copy, snapshot, build-plan, Forge, payload,
filesystem, Recipe-run, or Guardian-review evidence where such a receipt exists. Unexpected,
cross-project, stale, or changed values are routed through the failure path. Genesis advances only
for the exact object ROM Studio marked as validated; a generic completion signal cannot clear an
error or continue an automatic queue.

Companion applies the same truthfulness rule to an independent app-private, 100-event local
history. Routine health refreshes are deduplicated, restart persistence is required, and the
user can copy a privacy-safe report or explicitly clear this history. Sensitive device, APK,
and Community Lab content is not included in activity titles.

## 6. Quality attributes

- UI scanning must never block the event loop; each command has a timeout.
- Tool absence, no device, unauthorized device, offline device, and partial probe failure
  are normal states with useful messages.
- Core parsers and policies are Qt-independent and testable without ADB.
- Platform-specific behavior stays behind protocols/adapters.
- Logs avoid raw serials and command output that may contain personal data.
- Packaging uses a `src/` layout, type hints, immutable domain records, and dependency
  injection at process/device boundaries.
- Desktop release candidates are built natively on Linux x86-64 and Windows x86-64 as PyInstaller
  one-folder applications, launched against disposable workspaces, and packaged as bounded verified
  ZIP archives. CI manifests remain explicitly unsigned. Public trust requires the external-key
  Ed25519 ceremony and independent verification in `docs/DESKTOP_RELEASE.md`; release metadata has
  no device-operation authority and updates are never installed automatically.

## 7. Roadmap gates

1. **Foundation (v0.1):** this read-only vertical slice.
2. **Device diagnostics:** structured evidence, reports, history, backups, broader transports.
3. **Guardian expansion:** manifests, hashing, compatibility, dry-run, approvals, audit log,
   recovery/rescue packages, and verified postconditions.
4. **ROM projects:** import, immutable originals, working copies, extraction/rebuild and
   reproducible manifests; Recipes, ROM DNA, Time Machine, and Device Packs mature here.
5. **Repair/optimization:** evidence-based guided workflows with reversible actions first.
6. **Companion and Galaxy:** secure pairing followed by strictly optional online services.
7. **ROMVERSE One:** planning on top of proven typed operations and Guardian policies.
8. **Commercial readiness:** Windows/Linux parity, accessibility, threat model, signed
   updates/packs, beta hardware matrix, licensing, website, and launch campaign.

No gate may weaken Guardian to accelerate a feature.

### Galaxy Community Lab increment

Galaxy begins as an explicitly offline Community Lab on Desktop and Companion. Users can
create real local topics and replies, record a single local vote, search their own content,
delete it, and export or share a copy. Desktop persistence uses atomic, schema-validated
workspace JSON; Companion persistence uses a versioned private application record. Corrupt
data is reported and preserved rather than silently replaced. Seeded fake users, scores,
online state, synchronization, and moderation claims are prohibited. Public forums remain a
separate release gate requiring accounts, authentication, privacy controls, moderation,
reporting, abuse prevention, transport security, retention policy, and explicit sync UX.

## 8. Branding

The official hierarchy is ROMVERSE / Build. Optimize. Perfect. / Created by SteveTheRad /
A RadForge Labs Project. The full badge is for splash, installer, and marketing. The
approved cross-platform application icon is `romverse-app-icon.png`: the dimensional
purple/blue R inside a cyan orbital arc with the ROMVERSE wordmark beneath it. Desktop,
Windows packaging, and Android launcher resources must derive from that canonical asset
without distortion or creative reinterpretation.

The Desktop About ROMVERSE page places the canonical ROMVERSE product crest and the byte-exact
approved RadForge Labs company logo together in one responsive studio-identity hero without
altering either source asset. Build, channel, Guardian boundary, and navigation-only authority facts
remain visible near the top. Product-family cards are real handoffs to canonical Desktop routes;
About itself never gains device-changing authority. A balanced Official Websites section links to
the clean HTTPS `romverse.app` product destination and `radforgelabs.com` studio destination with
distinct crisp marks, aligned actions, accessible names, and no tracking parameters. Browser-launch
failure is visible and cannot be presented as a change to Desktop or device state. It sits before
the existing official community/social destinations. The read-only ROMVERSE Now map must include a prominent
Guardian-owned audit/approval lane alongside device, knowledge, build, and Live Console evidence.
Only Guardian Core may publish that lane as integrity verified; unverified, changed, checking,
locked, failed, or unavailable evidence keeps About out of its all-current state, and opening About
must never start an approval, command, build, flash, or phone action. A double-click on the About mark opens the
approved cinematic supporter tribute: inward-
moving stars, a purple/cyan accretion disk, event horizon, collapse pulse, mark reveal, and
the complete “To Everyone Who Believed” message signed SteveTheRad / A RadForge Labs
Project. The sequence must remain fully visible without scrolling, keep a dark opaque
ROMVERSE background, and stop its animation timer when complete or closed. This interaction
and its message are a locked brand moment and should not be replaced during general UI
restyling without an explicit product-owner decision. Discovery is stored only as a private,
bounded, exact-schema, atomic local record. Malformed, oversized, linked, or extra-field records
fail visibly; the record has no XP, account, membership, entitlement, or operation authority.

The About Trust Dock includes complete, scrollable, versioned Terms & Conditions and Privacy Notice
review drafts, with each status and SHA-256 visible. The Terms address authorised use, misuse,
user-supplied firmware, third-party dependencies, high-risk Android operations, recovery
responsibility, plan-specific warning acceptance, fair liability limits, and rights that cannot
legally be excluded. The Privacy draft describes the actual local workspace, device probe, brief
in-memory target addressing, Companion Link, backup, research, community, contribution, retention,
network-recipient and automated technical-decision boundaries. Its layered header shows the current
validated online/community/contribution/tool-download settings without modifying them. Both remain
explicitly ineffective until professional legal/privacy review completes provider/contact,
jurisdiction, recipient-country, retention, access/correction/deletion, complaint, collection-notice,
effective-date and signed-release binding gates. Opening or reading either is local-only, starts no
network request, and records no acceptance. Effective general Terms acceptance remains separate from
the exact expiring consent required for each device-changing plan.

The core palette moves from purple through blue to cyan on a near-black space-like surface.
Product-family marks remain related but distinct. Windows, Linux, and Android are planned;
no iOS claim is made.

## 9. Future commercial/security constraints

The confirmed commercial model is one A$14.99 AUD monthly all-inclusive membership with a
seven-day full-access trial, signed entitlements, periodic validation, and reasonable offline
authorization. The production billing service is not v0.1 behavior. Guardian's core
safety protections must never disappear solely because licensing cannot validate.
Secrets remain server-side; clients verify signed statements rather than embedding shared
secrets. A formal threat model and legal/trademark review are release gates.
