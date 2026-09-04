# ROMVERSE v0.1 ROM workflow

ROM Studio's **Genesis Sequence** presents the complete journey and executes only stages backed
by current evidence and a reviewed Device Pack contract:

Each Genesis stage includes **Learn this stage**. It preserves the active stage and opens
ROMVERSE Archives with a bounded stage-specific query, selecting the matching verified guide when
one exists. This is explanatory navigation only: it cannot create evidence, advance readiness,
approve a plan, or grant phone-write authority.

1. Import a firmware file into `original_roms/`. The source is copied, streamed-hashed, protected read-only,
   and bounded-inspected automatically in the same background operation. Progress covers both phases;
   manual re-inspection remains available when evidence needs to be refreshed.
   The project manifest is a private atomic schema-two record with a content digest. ROMVERSE rejects
   linked sources/destinations and discards the partial import if the source changes during copying.
   Bounded project discovery ignores linked project directories; valid schema-one history upgrades
   on its next successful save.
   A legacy broad Device Pack association may be upgraded automatically only when that archive
   SHA-256 identifies one unique reviewed build contract. ROMVERSE writes a local-only association
   receipt containing the previous/new Pack IDs and source evidence; ambiguous matches stay blocked.
2. Verify the protected original before every downstream operation.
3. Create Device DNA and its Capability Map from source/device evidence. Inspected payload, super,
   or partition-image structure—not merely a ZIP extension—selects the source adapter; unknown
   values remain unconfirmed, and bootloader relocking remains permanently unsupported. The strict
   private schema-two profile consumes structure only from the current persisted schema-two
   inspection report or Forge's same strict current project/source-bound local blueprint. A valid
   blueprint can confirm bounded build preparation but never supplies device-write or flash
   authority; foreign, stale, phone-changing, malformed, or source-mismatched records are ignored.
   Recognized Xiaomi HyperOS version ordering is numeric and is classified only after live/source
   codenames, distribution regions, and firmware branches agree. The resulting Upgrade Candidate,
   Same Firmware Version, Downgrade Candidate, Incompatible, or Unconfirmed label is evidence, not
   install authority. ROM Studio requires the user to acknowledge that they supplied the firmware,
   must confirm its trusted official source and exact model/region/update path, and accept the risk;
   this notice does not claim to exclude rights or obligations that law does not allow excluding.
   ROM Studio presents the same source-bound decision as a Firmware Upgrade Passport, including its
   evidence digest, reasons, next safe step and permanent zero-authority boundary. Forge Control
   re-evaluates it as a required flash-readiness gate. Newer exact-device candidates pass only the
   relationship check; same-version and downgrade inputs are visibly not upgrades and need an exact
   Pack for an explicit alternate route; wrong-device and rejected-metadata inputs stop the route,
   while missing evidence stays Attention. Cross-channel upgrades remain reviewable
   and become relationship-ready only with the separate exact flash-certified Device Pack contract;
   physical country of use is never used as a compatibility signal.
   Schema-one Device DNA remains readable and refreshes forward automatically.
   Genesis requests a fresh read-only device scan at this stage, shows the current identity and
   Capability Map states, and refuses to advance if either the profile or map is missing. A failed
   refresh clears stale ROM Studio device evidence rather than silently reusing it.
4. Create the source-bound Compatibility Matrix. Strong Match and technically possible are not
   treated as proven compatible, and the matrix may inform but never bypass Guardian. Its private
   strict schema-two record is re-derived from current Device DNA on every load; stale or even
   correctly re-digested changed decisions fail closed, while valid schema-one history refreshes
   forward on the next assessment.
5. Inspect archive/container metadata without extraction. The report is a bounded private
   schema-two record whose digest covers every source-bound signal and finding. Rejected or legacy
   evidence is regenerated automatically from the verified protected original before extraction.
6. Create an isolated working copy and optional Time Machine snapshot. The canonical working baseline
   is recorded in a strict private schema-two digest-bound record. Legacy records remain readable but
   require a stable full hash during snapshot creation before ROMVERSE upgrades them.
7. Prepare `working_roms/<project>/tree/`: extract verified ZIP/TAR archives with traversal, link,
   entry-count, and expanded-size guards, or transactionally stage a recognized direct payload or
   partition image under its canonical role with source SHA-256 verification. Unknown or ambiguous
   single-file roles remain blocked. Special/encrypted entries, linked/pre-planted tree paths, and a
   protected source that changes during the operation fail closed; staging directories and files
   use private modes and publish atomically only after the final source-identity check.
8. Generate a deterministic build dry-run plan. Guardian records the preflight status, risk,
   reasons, and manifest digest. Regular files are content-hashed; Android symbolic links are
   hashed as path/target metadata without following their targets. A changed link invalidates the
   plan just like a changed file.
9. Verify the extracted tree against the saved plan hash before any future build execution.
   ROM DNA then binds the current project, Device Pack, protected source, tree-plan hash and Recipe
   digest in a private schema-two record that re-derives itself on load. Nexus likewise stores a
   strict schema-two plan and reconstructs its complete route from current Device DNA and Matrix;
   neither record can grant execution or bootloader-relock authority.
10. Author and preview Guardian-controlled Recipes; matched and unresolved targets are reported and recipe digests are linked into build plans.
    Recipe Forger's in-place Learn this stage guide resolves one verified six-stage Archives article
    without closing the dialog or mutating the unsaved Recipe draft. Guidance cannot validate,
    approve, execute, or grant device authority.
    Its unfinished state autosaves into a private bounded schema-one record bound to the project and
    protected-source digest. Strict fields, a content digest, regular-file containment, safe relative
    targets, bounded steps/parameters, and target revalidation guard resume. Stale targets step back
    to selection; saving the final execution-locked Recipe deletes the draft.
    Final Recipe manifests use private atomic schema-two persistence with exact field/step shapes,
    bounded content, safe relative targets, a record digest, and a stable legacy-compatible Recipe
    digest. Recipe Forger rereads the stored manifest before claiming success. Strict schema-one
    history remains readable and upgrades only on the next intentional save.
11. Route recipe requests through the fail-closed local executor. Approval binds the current tree, recipe, and replacement inputs before any change.
12. Time Machine stores local working-baseline snapshots as bounded private schema-two evidence and
    can restore one after typed digest-bound approval. Legacy records remain visible but require a
    background full hash before upgrade or readiness. Rollback planning uses exact path/size/mtime
    metadata without hashing a multi-gigabyte image on the UI thread; the restore worker rehashes the
    selected bytes, binds a freshly sealed safety snapshot of the current baseline, copies atomically,
    verifies the restored SHA-256, updates the working record, and writes a strict digested receipt.
    It never targets a connected phone.
13. Guarded local recipe execution supports `inspect`, `replace_file`, `set_property`, and contained `remove_package` steps with automatic affected-target snapshots, atomic writes, verification receipts, failure rollback, and explicit later restore. Run receipts and rollback snapshots use bounded private schema-two evidence; readiness re-derives their exact Recipe, step, tree, snapshot, target and digest bindings and rejects links, oversized/extra-field records, renamed snapshots and backup rebinding. Strict schema-one history remains readable through the same fail-closed loader. This edits only the isolated working tree; dependency and boot compatibility still require review before any future build or flash.
14. For payload OTAs, open Partition Atlas to hash and map `payload.bin`, select non-critical ROM partitions, verify the adaptive storage budget, and extract chosen images transactionally.
    The private schema-two manifest rejects extra/nested fields, links, oversized records, source
    metadata drift, and mismatched tool identity. Before extraction ROMVERSE rehashes the exact
    payload and verified dumper; a valid legacy schema-one manifest remains visible and is
    automatically rescanned in the same background extraction operation before work continues.
15. Expand supported sparse/ext4/EROFS images into contained filesystem trees and send exact files directly to multi-step Recipe Forge. Review bounded before/after previews and resolve conflicts before approval.
    Before Nebula Debloat attempts this materialization, Genesis derives a narrow source-shape tool
    profile and opens Forge Arsenal for only the missing read-only dependencies. OTA payloads,
    fastboot `super.img`, and direct partition images receive distinct profiles; all include the
    sparse/ext4/EROFS readers needed to avoid a false empty app list. The inventory is fully
    rescanned after installation, and a denial, failure, or missing tool keeps Debloat paused.
16. Open Forge Control to evaluate workspace, builder, signing, recovery, device, battery, and boot evidence. For an exact supported contract, prepare only its declared partition inputs, preserve fakeroot ownership, combine source-bound SELinux contexts, and save a fresh execution plan.
    Firmware Source Intelligence handles one contained `payload.bin`, one `super.img`, or a bundle
    of uniquely named partition images. For a bundle it hashes every image, records format,
    size/mtime, role and contained path, and persists a private source-bound baseline blueprint.
    Duplicate roles, empty images, unsafe paths, oversized inventories, or later metadata drift fail
    closed. This inventory grants no rebuild, AVB, recovery, root, or device-write authority.
17. Create a Forge Bundle from the frozen plan. ROMVERSE verifies the exact file and symbolic-link
    set while writing a deterministic content-addressed ZIP, preserves links as link metadata
    without reading their targets, embeds per-entry hashes and an explicit
    unsigned/non-bootable/non-flashable contract, then verifies the completed archive again.
18. At the Toolchain stage, select **Install and verify requirements**. ROMVERSE installs only
    missing approved dependencies, records integrity/provenance receipts, rescans every Genesis
    requirement, and resumes the same mission. An authorization denial, download failure, hash
    mismatch, or still-manual tool leaves the stage blocked with its real diagnostic. Every rescan
    reconstructs the managed process path from strict receipts, removing a previously activated
    tool immediately if its bytes, receipt, canonical location, or contained path no longer verify.
19. Choose **Build verified local candidate** only after every Build gate passes. ROMVERSE writes
    to a new plan-ID output directory, runs the exact EROFS/AVB/logical-partition commands,
    unsparses and unpacks `super.img`, byte-compares every A-slot image, removes temporary raw
    verification data, and records output hashes. This executor has no ADB/Fastboot transport.
20. Choose **Inspect AVB topology** to extract and hash the exact source `vbmeta` images, record
    signing algorithm, public-key fingerprint, rollback fields and descriptor partitions, and
    compare them with the current candidate. Finding AVBTool or creating valid descriptors does
    not mean the candidate is signed. A source/candidate key mismatch remains explicit evidence,
    never an inferred success.
    ROMVERSE may also compare the result with separately scoped historical evidence. The proven
    OS4.0.0.20 popsicle workflow preserved Xiaomi's signed top-level `vbmeta`, generated a
    descriptor-correct Algorithm-NONE `vbmeta_system`, and required both unlocked and
    critical-unlocked bootloader evidence. Because the current contract is OS4.0.0.23, that
    structural match is reference-only: it explains the candidate but cannot authorize flashing.
21. If—and only if—the exact Device Pack declares a flash-validated `signed_custom_rechain`
    policy with an attested public-key fingerprint, choose **Offline signing ceremony**. Export
    the exact `product.img` and `vbmeta_system.img` request outside the workspace, sign them in a
    protected external environment, then import the results. ROMVERSE never receives the private
    key. It rehashes both artifacts and verifies their Pack-authorized key fingerprint and AVB
    policy before saving evidence. The returned folder must retain the exact content-addressed
    request manifest. Request/receipt records are bounded private atomic files, symlinked paths and
    redirected evidence directories fail closed, and schema-one receipts are rehashed before a
    one-time migration to responsive schema-two metadata identity. The current OS4.0.0.23
    reference-only Pack intentionally rejects this operation.
22. In Time Machine, register an independently stored phone backup and exact stock-recovery
    package. ROMVERSE hashes each file in place, stores absolute locations only in a private
    `0600` locator, exports only filenames/hashes, and detects later movement or modification.
    Both records are bounded strict-schema atomic files; symlinked/oversized records, extra fields,
    unsafe roles, wrong project/source identity, and workspace redirection fail closed. Preserved
    schema-one evidence requires a complete rehash before ROMVERSE upgrades it to schema two or
    counts it as ready. This user-side evidence cannot bypass the Device Pack's independent physical
    recovery-test attestation.
23. Boot Observatory records Guardian-approved read-only samples of `sys.boot_completed`, device
    uptime, active slot, build identity, battery and probe errors. It flags uptime resets and
    build/slot drift and requires a five-minute consistent window before calling an Android
    session stable. A stable observation is not a verified first boot unless a future successful
    Guardian flash receipt binds the same device, Pack, contract and artifact.
24. Optional Ascension Protocol preparation binds the protected source, exact source Pack or
    blueprint identity, current Device DNA digest, authorized phone, official manager artifact,
    rollback evidence, and rooted local build input. Conflicting codenames fail closed. ROMVERSE
    Live Console records genuine progress through all nine preparation stages and preserves the
    latest verified stage when paused or failed; it never turns preparation into root or flash
    authority and never authorizes bootloader relocking. Learn this stage safely pauses when idle
    and opens the matching stage inside one verified nine-stage Archives guide; the guide cannot
    create evidence or approval. The tracker, Next Safe Action, status text, guide and Live Console
    share one canonical order: Prerequisites, Official manager, Patch capsule, Phone handoff,
    Patched image, ROM integration, Build seal, Device binding and Guardian review. A manually
    verified patched image may bypass the physical handoff checkpoint but cannot complete any later
    checkpoint without its own evidence. The automatic route record and exact-kernel KernelSU
    support observation use bounded private
    atomic storage. Extra or mistyped fields, oversized files, linked or redirected evidence paths,
    stale source/Device DNA/phone/kernel identity, or a Manager that fails current vault
    revalidation invalidates the decision instead of selecting a root route. After the approved
    install/transfer, Desktop can resolve the allowlisted Manager, temporarily copy only its
    installed base APK,
    revalidate the full official hash/package/signer, remove the copy, and open that package. The
    open-only receipt stores no serial or Android install path and carries no reusable authority.
    Official Manager storage is separately contained beneath the workspace with non-linked bounded
    tag enumeration, exact content-addressed APK paths, private `0700` directories and `0600` files,
    atomic strict-schema receipts, and complete signer revalidation on every load. A redirected
    vault, linked tag, entry flood, extra or mistyped receipt field, future release timestamp, or
    correctly re-digested path substitution is rejected without using a cache or touching the phone.
    With another explicit approval, a nine-minute bounded watcher then checks only Downloads
    filenames every twelve seconds, shows actual elapsed-time progress, and automatically enters
    exact-file review when the selected manager output appears. It stops on close, disconnect,
    evidence change, timeout, error, or success and never keeps a hidden background poll alive.
    Root-target discovery is content-aware: byte-identical duplicate `init_boot.img`, `boot.img`,
    or `recovery.img` copies are collapsed to one canonical partition path, while byte-distinct
    duplicates, excessive candidate sets, unsafe paths, and implausibly large targets block with an
    exact explanation. Selection also verifies the Android boot version, required header/page
    layout, section bounds against the real file size, and a non-empty ramdisk:
    Magisk safely falls back from `init_boot` to `boot` and then recovery mode with the skipped
    reason shown, while KernelSU LKM remains restricted to `init_boot` or `boot`. ROMVERSE never
    selects a root image merely because its pathname sorts first.
    Ascension automatically resolves the minimum verified host dependencies at their point of use:
    AAPT2 plus APK Signer before official Manager acquisition, and Python plus Payload Dumper before
    scanning one unambiguous contained OTA payload. Before target discovery it can also prepare a
    verified safe archive, a correctly named Android boot image, or a standalone payload inside the
    isolated tree after checking the extraction budget. Critical archive findings and an Android
    boot binary whose partition role is not evidenced remain unconfirmed. It rescans Forge Arsenal
    and resumes the same step only when every required tool is genuinely available; otherwise it
    stops before manager trust or patch-target selection and explains the unresolved dependency.
    Official manager acquisition distinguishes connectivity loss from rejected trust evidence:
    invalid metadata, URLs, hashes, package identity, or signer pins stop the route. Only a manager
    revalidated within 30 days under a tamper-evident freshness receipt can be used during a genuine
    provider outage, and the UI marks that state as attention rather than current online evidence.
    Rollback discovery applies the same rule across extracted tree and partition directories:
    identical stock-recovery copies collapse to the canonical partition path, byte-distinct copies
    block, and a previously sealed content-addressed rollback remains valid if unrelated working-tree
    files appear later.
    Every rollback reuse re-derives the boot header and ramdisk facts from the vaulted bytes and
    requires exact semantic roles, canonical content-addressed filenames, and containment under the
    active project's rollback vault. Recomputing a receipt digest cannot redirect it elsewhere.
    A locked or unconfirmed bootloader is an attention gate during local image preparation, not a
    reason to prevent building a rooted ROM candidate. It becomes a hard blocker again in the
    Guardian manifest and final handoff, which require a freshly observed explicitly unlocked state.
    ROMVERSE never performs the unlock and never permits relocking.
    A sealed handoff can open Guardian
    Consequence Review: seven plain-language acknowledgements plus the typed phrase `ASCEND`
    produce a ten-minute, exact-handoff-bound review receipt with no command or execution authority.
    Root-plan, Guardian-manifest, final-handoff, and consequence-review records use private bounded
    atomic storage and strict complete shapes. Oversized, linked, redirected, extra-field, or
    primitive-type-confused evidence fails closed even if its outer digest is recomputed; every
    current dependency is re-derived before the chain can be shown again.
    The earlier rollback, patch-capsule, patched-image, reversible integration transaction/receipt,
    rollback snapshot, and build-seal chain follows that same private bounded exact-shape contract.
    ROMVERSE rehashes each current artifact, rejects linked or redirected storage, stops before a
    local input change when interrupted recovery metadata is unsafe, and restores the pristine local
    image if the integration receipt cannot be stored. Invalid evidence returns the guide to the
    first rebuildable stage and never grants phone authority.
    The approved manager-install/input-transfer receipt, signature-verified Manager-open receipt,
    and filename-only patched-output discovery also use private bounded exact-shape storage with
    private history. Each load revalidates its current capsule, official Manager, pseudonymous phone
    binding and candidate set; links, redirects, oversized/extra fields, type confusion, artifact
    changes and expired discoveries return the user to the affected stage without granting future
    approval or execution authority.
    Local source/target/rollback preparation alone leaves flash-contract and physical-validation
    readiness at ATTENTION and routes its evidence action to Device Atlas; it cannot turn the project
    green or create a new flash-mode handoff. A valid existing handoff, or a future handoff created
    after signed exact Pack certification is present, separately opens Guardian Manifest Review. It recompiles current
    readiness, rebinds the protected source and exact phone, displays the data choice and every
    PASS/BLOCKED check, and exposes no consent or execution action. Unless the selected Device Pack
    supplies a signed, exact-build, physically recovery-tested partition-to-artifact write contract,
    the partition-write list and command manifest remain empty and the review stays blocked. A Pack
    filename, image name, reference-only AVB policy, or historical success is never write authority.
    Build-contract schema two can carry that declaration as a bounded ordered mapping of a unique
    partition to one allowed `.img` artifact, explicit Fastboot/Fastbootd transport and slot, and
    mandatory post-write verification. It must bind the exact source build and the same signed
    physical-attestation digest as a flash-validated AVB policy, require an unlocked bootloader,
    state supported keep-data/wipe-data modes, and permanently prohibit relocking. Destructive
    data/control targets, implicit slot suffixes, unknown outputs, duplicate mappings, and mismatched
    authority are rejected when the Pack loads. Even a valid declaration remains zero-authority
    until Guardian binds its artifacts to the current immutable build receipt.
    For a future flash-certified Pack, Guardian performs that binding off the UI thread. It accepts
    only current verified local-build outputs, or exact imported offline-signing evidence when the
    policy requires re-signing; signed composite images that the current pipeline cannot prove are
    rejected. Every selected image is fully rehashed with byte progress and bound to the exact
    handoff, phone pseudonym, data mode, source, Pack, contracts and evidence-receipt digests in a
    private strict record. The review may then show ordered hash-bound writes, but still contains no
    commands, final consent or execution authority. Same-size/same-mtime edits, links, changed
    handoffs, unsupported data modes and re-digested relock attempts fail closed.

The full mission continues with Guardian flash and first-boot health verification. Device-changing
stages remain explicitly locked until ROMVERSE has an exact authorized signing receipt, external
phone backup proof, tested recovery route, exact final manifest, and approval bound to the final
device and artifact.
The user's keep-data or wipe-data choice is a zero-authority, private bounded schema-two handoff
bound to the protected source, exact phone and a stable digest of every current readiness fact.
Re-running an unchanged assessment preserves the choice, while any real gate/evidence change,
device change, linked or oversized file, malformed shape, extra field, or safety-invariant change
invalidates it. Schema-one history remains readable only as audit evidence and must be recreated
before Genesis can advance.

Genesis Sequence and Forge Control use the same readiness engine. The guided Build & Sign
stage opens the detailed gate view rather than displaying an unrelated placeholder, and no
saved navigation state can convert a missing artifact or planned Device Pack capability into
completion evidence.

Mission navigation and user choices are saved in one bounded private atomic schema-five
`guided-mission.json` record with exact fields and a content digest. ROM Studio project cards read
that same record rather than a duplicate progress summary. Strict schema-two through schema-four
history remains readable and upgrades on the next intentional save; links, oversized/extra-field
records, altered digests and type coercion fail closed with a safe recovery explanation. Completion
is derived from real project evidence wherever available. ROMVERSE diagnoses failures at the active stage
and may automatically remove only known incomplete `.part`, `.tmp`, and `.rollback-part`
transaction files contained inside the active workspace; it never auto-bypasses integrity or
compatibility failures.

## Proven HyperOS reference evidence

ROMVERSE's offline guidance includes the successful Xiaomi 17 Pro Max (`popsicle`) HyperOS 4
reference workflow as scoped evidence. The exact OS4.0.0.25.XPBCNXM clean-install package was
flashed to one real `popsicle` on 2026-09-03 and the user confirmed its Android Auto and Gboard
result fully working. The build changed only `product`, preserved the base Google framework and
Xiaomi-signed top-level `vbmeta`, retained source EROFS identity/features and filesystem metadata,
updated only the product descriptor inside `vbmeta_system`, then expanded and unpacked sparse
`super` and byte-compared all nine slot-A logical partitions.

The Android Auto result came from a coordinated privileged integration: verified Google signer,
system stub, privileged/default-permission XML, a minimal static overlay naming the projection
package and appending notification-listener access without dropping Xiaomi's listeners, plus
exact-build conflict resolution for CarWith. CarWith removal is recorded as specific to this
build, not a universal Android Auto requirement. ROMVERSE keeps build-static verification, flash
completion, first boot/setup, and real in-car projection as separate evidence states. A successful
result on one phone raises confidence for an identical target but cannot guarantee all units.
Physical location is never a compatibility gate: a Chinese device used in Australia is still the
same device. Firmware channel is shown as review evidence rather than an automatic refusal for a
full clean package; signed incremental OTA pre-build requirements remain exact. Device identity,
package hashes, rollback, unlock states, partition geometry, backup and recovery facts still
require fresh per-device checks. These lessons improve diagnostics and build
planning but do not supply build, flash, wipe, slot, unlock, relock, or phone authority.

Extraction capacity is adaptive rather than a generic small-archive ceiling. ROMVERSE uses the
inspected expanded size, source-to-output ratio, current workspace free space, a minimum 4 GiB
post-extraction reserve, and a 256 GiB hard ceiling. This permits legitimate modern factory ROMs
while retaining disk-exhaustion and archive-bomb defenses. The archive metadata and size budget
are revalidated before any contained extraction begins.

Local rebuilding is enabled only for an exact integrity-indexed contract and remains separate
from signing or device authority. Signing, privileged operations, device modification, and
flashing remain locked. The protected original is never used as an edit target.

## Device Atlas expansion after ROM Studio

Before expanding Pack coverage, Device Atlas preserves the exact ROM Studio mission that opened
it. A valid project-local source blueprint replaces stale build/tool cards from a phone-matched but
different firmware Pack: the UI names the active project, protected source hash, build ID, source
kind, plan digest, and observed partition count; Build returns to that project's Build & Proof tab;
Compile opens Forge Arsenal with only the source-derived ordered tools. Every button reloads the
manifest and source receipt. Changed bytes, digests, authority, source identity, or phone codename
stop the handoff visibly. This project-local build evidence never supplies flash authority, so the
Flash lane remains locked unless the exact source also has the separate reviewed Device Pack and
Guardian write evidence.

ROMVERSE will expand to another phone only through a versioned Device Pack. Each accepted model,
region, carrier and firmware build must include authoritative source URLs, immutable archive and
payload hashes, exact product/codename identifiers, partition and slot topology, filesystem and
AVB parameters, tool-version constraints, rollback and stock-recovery artifacts, known failure
codes, and a signed physical test attestation. Similar model names or OEM-wide assumptions never
inherit build or flash authority. A historical workflow may improve diagnostics immediately, but
it remains `reference_only` until reproduced against the exact firmware contract.

The planned ingestion order is: authoritative source collection; hash/provenance verification;
offline read-only identity and diagnostic knowledge; deterministic extraction/build fixtures;
emulator or local artifact validation; controlled physical recovery and first-boot testing; then
signed Pack publication and revocation support. This lets the Device Atlas grow across Xiaomi,
Samsung, Google, OnePlus, Motorola and other OEMs without turning breadth into guesswork.

Device Atlas can start this work directly for a connected phone with reviewed OEM knowledge but no
exact build contract. **Prepare model Pack draft** copies only bounded Android-reported
manufacturer/model/product/codename evidence and the matched Pack's existing reviewed HTTPS source
starting points; it excludes the serial and private user data. The proposed identity stays limited
pending direct official-source corroboration. Maintainers can run the same workflow with
`scripts/create_device_pack_draft.py` and the reviewed request shape in
`docs/device-pack-draft-request.example.json`. The generator uses bounded no-link reads and private
atomic content-addressed writes, forces firmware, partition, recovery, and device actions locked,
requires exact model and product patterns plus HTTPS source evidence, and emits a file marked
`publication_status: draft`.
The production registry explicitly rejects that marker even if someone manually adds the file to
an integrity index. Publication therefore remains a separate reviewed change, never an ingestion
side effect.

For a ROM Studio source-mismatch handoff, Device Atlas also reloads the content-addressed private
draft on every render and matches its project, protected-source hash, and source-blueprint digest.
Once that exact draft exists, the page marks the step complete and replaces **Prepare exact-source
Pack draft** with **Review draft and missing evidence**. The review lists the remaining write,
readback/first-boot, transition/slot/recovery, AVB-policy, stock-recovery, and independent physical-
test contracts. Reopening the project therefore does not recreate the same draft or send Guided
Setup through the same step again. Changed content, a mismatched source, an authority-bearing draft,
or linked storage is rejected and cannot produce a completed state.

The read-only expansion now includes integrity-indexed Google Pixel, OnePlus/OxygenOS,
OPPO/ColorOS, realme UI, Nothing OS, Motorola, and Sony Xperia Packs. Their official OEM and AOSP
reference URLs are schema-validated, dated, and visible in Device Atlas. These Packs can classify
standard identity, health, slot, and boot evidence; their firmware, unlock, recovery, root, and
flash capabilities remain locked because an OEM-wide source page is not a model/build contract.

Desktop is the canonical source for Companion's Atlas catalog. The generated Kotlin catalog binds
the same Pack ID, version, SHA-256, priority, manufacturer/model/product match patterns, source
scope, verification date and boundary text. CI compares the generated file byte-for-byte with the
verified registry so the two apps cannot silently disagree. Source dates cannot be in the future,
and UI surfaces a review warning after 180 days.
The Atlas source-audit export inventories every Pack digest, source reference, verification date,
and review status in a canonical JSON document. The filename is content-addressed and the payload
contains no connected-device identifiers or execution authority. This gives maintainers a stable
review queue without weakening any Guardian gate.
Registry loading rejects every copy of a duplicated Pack ID. Live resolution considers all valid
manufacturer/model/product/codename matches and accepts only one highest-priority result. A tie is
an explicit ambiguity failure, not an ordering decision. Companion mirrors this behavior and
withholds OEM-specific guidance until the catalog conflict is corrected.

The first exact-model read-only family covers the published Pixel Tensor/GKI models and codenames
from Pixel 6 through Pixel 9a. The match is more precise than `google.pixel`, but the Pack still has
no firmware digest, partition contract, recovery attestation, signing identity, or execution
authority. Exact identity is useful evidence; it is not permission to build or flash.

The Sony Open Devices exact-identity family matches only product codenames in an immutable revision
of Sony's published support table, while the broader `sony.xperia` Pack remains the fallback for
unknown products. Announced, WIP, and deprecated labels are context only. The exact Pack has no
stock firmware hash, partition contract, AVB/signing policy, or physical recovery evidence and
therefore carries no build or device-changing authority.

Physical recovery evidence is imported as a detached Ed25519-signed attestation. The signature
must bind the exact Device Pack version and SHA-256, firmware build, model and product, and a
content-addressed report covering stock restore, failed-flash recovery, slot recovery and
first-boot validation. ROMVERSE stores trusted public keys only; publisher private keys remain
external and offline. A valid attestation clears only its publisher and physical-test evidence
checks. It cannot override a reference-only AVB policy, an incomplete stock recovery route, or
any other Guardian gate.

Verified envelopes are copied atomically into the workspace attestation vault and reverified
against the bundled, integrity-checked publisher trust catalog every time Device Atlas, Genesis
Sequence, or Forge Control assesses readiness. Rejected evidence is not retained. Tampering,
expiry, revocation, hardware mismatch, source-build mismatch, unsafe filenames, and oversized
envelopes all fail closed. ROMVERSE ships no fabricated RadForge production key; a genuine
offline-controlled release public key must be added through the release process before real
publisher evidence can be accepted.

Recovery Bay treats local checkpoints, external phone backups and stock firmware as different
evidence classes. External artifacts must remain outside the ROMVERSE workspace. A stock-recovery
file is accepted only when its SHA-256 is byte-identical to the project's protected firmware
source; renaming another archive cannot satisfy the gate. ROMVERSE records private locators and
public hashes, then requires reverification if the file changes.
