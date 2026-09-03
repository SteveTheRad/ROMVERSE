# ROMVERSE v0.1

**Build. Optimize. Perfect.**  
Created by **SteveTheRad** — A **RadForge Labs** Project

ROMVERSE is an online-first Windows, Linux, and Android platform for intelligent firmware
analysis, diagnostics, repair, optimization, device management, and ROM development. Local
source evidence remains the safety anchor while verified online services provide current tools,
Device Packs, compatibility knowledge, and recovery intelligence. This first vertical slice
is intentionally read-only: it creates a safe workspace, verifies local tooling, detects
Android devices through ADB, and presents live device details in the PySide6 **Device Portal**.

The second read-only slice adds ROMVERSE Diagnostics: evidence-backed health/security
findings, conservative signal scoring, explicit analysis limitations, and privacy-safe
local report history. Reports are saved only when the user selects **Save report**.
The **Health Timeline** screen compares saved snapshots from the same pseudonymous device,
showing score movement plus new and resolved findings without retaining raw serials.

The Desktop **About ROMVERSE** experience now presents the approved ROMVERSE product crest and
byte-exact RadForge Labs company identity together in one responsive studio hero. Live build,
channel, safety-boundary, and navigation-authority facts remain visible near the top; product-family
cards open their canonical Desktop destinations instead of acting as decorative tiles. Official
website and social actions report browser-launch failure without implying that Desktop or device
state changed. The hidden Origin discovery remains replayable, while its tiny local record is
strictly schema-validated, private, atomic, and deliberately carries no XP, membership, account, or
device-operation authority.
Its ROMVERSE Now evidence map gives Guardian a full-width owner lane: About can display only the
current Guardian Core audit/approval state, cannot turn green before full verification, and retires
stale audit metadata to reverify-required without starting an approval or device action.

The **Guardian Core** exposes the safety boundary: every Guardian-controlled operation is
recorded in a local SHA-256 hash chain with device identifiers redacted. ROMVERSE verifies
that chain before execution and blocks the gateway if previous audit records were altered.
The verified audit tail is cached against the file's device/inode/size/timestamp identity, so
routine device probes remain constant-time after one full verification while external writes
or replacement still force a complete fail-closed recheck. Guardian Core performs the full audit,
approval, APK-receipt, and recovery-evidence review on a managed background worker with duplicate
refreshes locked and an honest indeterminate progress indicator. The audit itself is bounded by
file, record-count, and per-line limits before JSON parsing, so oversized or flooded history fails
closed instead of freezing the interface.
Explicit Guardian approvals use a separate append-only SHA-256 chain. New approvals bind the
exact plan and privacy-safe target, expire after ten minutes, and are reverified before use;
altering any entry invalidates the chain and blocks every stored approval. Legacy approval lines
remain visible for audit compatibility but can never authorize a new operation.

**Recovery Bay** now provides Guardian Preflight assessments. It converts a selected
problem category and live device evidence into an immutable operation manifest, evaluates
preconditions and risk, and displays the inspect → simulate → repair → verify workflow.
Device-changing repair remains locked unless a separate exact implementation exists.

Its first typed **Recovery Autopilot** executor handles only an evidenced offline or failed
host ADB daemon. After one explicit Guardian review it revalidates the approved ADB binary,
runs only exact host `kill-server`/`start-server` operations, verifies with `devices -l`, writes
a privacy-safe SHA-256-bound receipt, and requests a fresh Device Engine scan. The executor has
no `adb -s` surface, cannot target a phone, never deletes an ADB key, and never infers recovery
from elapsed time. An unauthorized phone instead receives the correct on-screen RSA instruction,
and a healthy daemon is not restarted merely because the user opened the page.

Recovery Bay also accepts an exact symptom or error and automatically creates a bounded research
fingerprint when real warning/error evidence exists. Host paths, contacts, credential-like values,
IP addresses, serial-like identifiers, and long digests are removed before official and optionally
enabled community providers are queried. The result card exposes authority, source date/freshness,
scope, corroboration, confidence, and the confidence reason. Remote text remains guidance-only.
Only a matching built-in typed action with a successful local receipt can be recorded as locally
verified working; disabling online intelligence while a lookup is running discards that result.
Research receipts and verified-outcome records now use size-bounded, private `0600`, uniquely
staged atomic writes anchored beneath the workspace. Symlinked directories/files, non-regular
targets, malformed or extra-field schemas, oversized records, unbounded outcome collections, and
provider-controlled action/source identifiers fail closed. A provider cannot set ROMVERSE's
`verified working` state; loading that state also requires the matching local outcome record to
remain valid. Schema-one guidance receipts remain readable with their newer evidence explicitly
unconfirmed.

Recovery Bay now also offers **Search local Archives** beside the exact symptom field. Its deterministic
Archives Advisor prioritizes an exact error-code match, then the selected typed repair concern and
current diagnostic finding IDs. The assessment displays the primary source authority and automation
boundary, records every recommendation in the privacy-safe exported report, and opens the selected
stable article identity directly. Quantum Optimizer also carries its highest-priority actionable
finding ID into Recovery Bay, which selects the deterministic matching concern only when that same
finding is present in Recovery Bay's current report. A visible source-context strip names the finding
and states that no action started; stale or unknown handoffs fail closed instead of opening a generic
plan. **View source finding** returns to Quantum Optimizer, scrolls to the same current finding, and
highlights its exact read-only evidence without rerunning or changing the report. A stale reverse
handoff also fails closed. Both pages retain an in-page refresh/no-action explanation even when
optional Desktop notifications are disabled, so safe refusal never looks like a dead button. These
handoffs do not start research, approval, or repair, while ROM Studio, Genesis, Ascension, and Recipe
Forge retain their stage-specific guides and drafts.
When online research is off, its secondary panel folds into a compact, accessible status row so local
preconditions and the Advisor stay prominent. Active, returned, or failed research expands its full
evidence automatically, and the user can fold only those details without changing assessment state.

The Desktop **ROMVERSE Archives** catalog now contains 151 validated local guides across ten
categories, including 101 structured known-fix records and 38 official-source-backed records. The added
official-source-labelled device triage covers battery/heat, storage, Android updates,
app crashes, screen/touch, network, and performance, while camera/audio guidance remains explicitly
ROMVERSE-scoped until exact OEM evidence is available. Ranked punctuation-tolerant retrieval covers
ADB/USB, host tools, firmware intake, dynamic
partitions and filesystems, AVB/boot, SELinux/build failures, APK install status, Guardian/recovery,
and evidence integrity. Every structured fix separates meaning, checks, safe steps, verification,
evidence, automation boundary, and source. Weak searches return no verified match instead of broad
advice; category filters and canonical route buttons return the user to the relevant Desktop
workspace. Local guidance never grants approval or execution authority.

Device Engine now discovers both running Android/ADB transports and phones already connected in
bootloader Fastboot or userspace fastbootd. The Fastboot adapter is routed through Guardian and can
run only `devices -l` plus the exact `product`, `current-slot`, `unlocked`, `secure`, and
`is-userspace` variable reads documented by the AOSP Fastboot contract. Command Deck presents the
result as identity-only evidence and connects it directly to Device Atlas, where the observed
product/codename can select the integrity-checked Device Pack and build/tool roadmap. Android health
telemetry stays unknown in this mode, serials remain masked, and reboot, flash, erase, unlock, wipe,
and relock commands are not on the adapter or Guardian allowlist.
Device Engine probes every visible transport. Project-bound Device DNA uses live phone evidence only
when exactly one authorized Android phone is connected; with multiple authorized phones ROM Studio
withholds the binding instead of guessing. An explicit selection model shared across every
device-facing page is still required before simultaneous multi-device targeting is supported.

Verified outcomes now use schema two and require more than a digest-shaped string. The candidate
must belong to the exact persisted error fingerprint, and the built-in action must supply a
workspace-relative typed evidence reference. Recovery Autopilot revalidates its successful ADB
history receipt; Forge Arsenal writes and rehashes an exact required-tool receipt; OTA source and
AVB results revalidate their project-bound persisted evidence and contained artifact metadata.
Changing or removing that evidence revokes the cached confirmation. Legacy digest-only outcomes
remain local historical files but cannot promote a fix.

Recovery Bay also supports **guided repair sessions**: ROMVERSE preserves a pseudonymous
diagnostic baseline, saves which recommended checkpoints the user reviewed, and requests a
fresh Device Engine scan before comparing health signals and finding IDs. A checked step is
never treated as proof of repair, and comparison results say improved, unchanged, or needs
more attention. Schema-two session evidence is strict-field, size-bounded, private, atomically
stored, content-digested, and semantically re-derived; altered, linked, oversized, and falsely
re-digested outcomes cannot teach the app. A new session also binds the primary evidence-matched
Archives article identity. After a genuine fresh comparison, Archives may show aggregated local
resolution memory for that exact article, clearly labelled as correlation rather than proof that a
guide caused the change. Legacy sessions remain readable but cannot strengthen Archives until an
intentional update rewrites them into the current verified format. Sessions remain local; no repair
command is executed and the memory grants no execution authority.
If the verified ADB runtime is missing, Recovery Bay now presents **Resolve Platform Tools and
scan** inside its blocked-state card. The same scoped resolver refreshes the complete tool
inventory, atomically restores every ADB-dependent Desktop service, and starts a fresh read-only
Device Engine scan. Failed verification stays visibly blocked and starts no diagnostic or phone
operation.
The bounded host-daemon executor above is the only Recovery Bay repair action in this milestone;
guided checkpoints never become device-changing commands.

The **Device Atlas** uses integrity-checked Generic Android, Xiaomi/HyperOS, Samsung/One UI,
Google Pixel, OnePlus/OxygenOS, OPPO/ColorOS, realme UI, Nothing OS, Motorola/Lenovo, Sony Xperia,
vivo/iQOO, ASUS/ROG Phone, HUAWEI, and HONOR metadata packs. ROMVERSE selects the most specific
matching OEM pack automatically while keeping all unvalidated firmware/recovery capabilities
locked. Each broader OEM Pack records checked
links to official OEM or AOSP references and shows those sources in the UI. Source-backed
read-only knowledge improves diagnosis, but Pack metadata and a manufacturer match have no
execution authority.
The Companion Atlas is generated from this same verified registry at build time; a parity test
fails if its Pack versions, SHA-256 identities, match patterns, source scopes, or safety boundaries
drift from Desktop. Sources older than the review window are visibly marked `REVIEW DUE` rather
than silently presented as current.
Desktop also shows live catalog/source health and can export a privacy-safe,
content-addressed source-audit manifest. The audit records Pack digests, official-reference
scope and review status with `execution_authority: none`; Companion displays the same generated
catalog totals in Recovery Bay and diagnostic reports.
Pack IDs must be unique and identity fields are bounded before activation. If two Packs match one
device at the same highest priority, ROMVERSE blocks OEM-specific resolution instead of relying on
file order; Companion reports the ambiguity and exposes only the Generic Android read-only context.

Desktop Device Atlas can now synchronize Google's public supported-device catalog from its fixed
official HTTPS endpoint on a managed background worker. The Device Engine reads the OEM-reported
`Build.BRAND`, `Build.DEVICE`, and model properties; ROMVERSE requires the exact brand/device pair,
uses the exact model only to narrow variants, and refuses conflicting retail names. The bounded
UTF-16 catalog is checked for route, encoding, columns, size, entry count, local file type, SHA-256,
and a strict private receipt before use. A current or still-valid stale cache may supply a retail
name only. It never supplies a partition map, firmware match, Device Pack, build/flash contract,
approval, command, or execution authority. After recognition, the ordinary Device Pack roadmap
still determines exactly what evidence and tools are missing for build planning and keeps flashing
locked until its independent signed and physically tested contracts pass.
Its four-lane **Automatic Requirements Blueprint** now consumes Forge Arsenal's current host-tool
verification instead of stopping at a declared list. For an exact build contract, the Compile lane
shows the verified count and exact missing subset, updates when the tool inventory changes, and
routes that same contract-scoped subset back to Forge Arsenal. A complete host toolchain changes
only Compile to verified; it cannot strengthen identity, source/build, physical recovery, Guardian,
or flash authority. Contradictory duplicate tool evidence fails closed as missing.
When ROM Studio opens Device Atlas, the four lanes are scoped to that exact project rather than
left on an unrelated phone-matched Pack. Device Atlas reloads the current private project manifest
and strict OTA, fastboot-super, or partition-bundle source receipt; requires the protected source,
build identity, authority, blueprint digest, plan digest, and phone codename to agree; and displays
the project build ID, partition count, and narrow source-specific tool profile. Build and Compile
route back to that same ROM Studio project and its exact Forge Arsenal context. Any changed receipt
or extracted source stops the retained route instead of silently falling back to an older Pack. A
verified project-local baseline can mark local build preparation ready, but its Flash lane stays
locked until the independent source-matched recovery, AVB, publisher, physical-test,
partition-write, artifact-binding, and approval gates pass.
Downloads are parsed and verified in memory before activation. Switching off online diagnostics
and sources cancels a pending refresh and prevents a late response from replacing the active local
mirror; any previously activated receipt-checked catalog remains available for local read-only
search and recognition.

For a connected phone, Device Atlas also produces a model-specific validation roadmap for
pack integrity, exact model/codename scope, firmware and partition contracts, publisher
attestation, stock recovery, and physical recovery testing. Every card explains its current
evidence and possible fix on hover. A privacy-safe, content-addressed maintainer request can
be exported without serials, IMEI, accounts, files, keys, or capability-enabling authority.
Exporting a request never clears a gate; only a reviewed Device Pack with the required
evidence can do that.

That roadmap now derives one prominent **Next Safe Action** from the exact current report. A build
gate opens the exact verified Archives guide; a build-ready Pack with missing stock recovery opens
Time Machine with the report/Pack identity still visible; a fully ready Pack continues to ROM
Studio. Every handoff is revalidated against the report digest before navigation and starts no
worker, approval, build, or phone action. If Time Machine has no protected-firmware project, it
refuses to invent one and connects back to ROM Studio. The genuine readiness result is also recorded
in Live Console, whose source action returns to Device Atlas. Shared dark item-view styling keeps
empty lists, trees, tables, and combo popups readable instead of inheriting a native white viewport.

The bundled exact-identity Packs map published Pixel 6 through Pixel 9a names/codenames from
Google's AOSP kernel matrix and Sony Xperia product codenames from an immutable revision of Sony's
Open Devices support table. They complement the online retail-identity catalog while deliberately
supplying no firmware build or device-changing contract.

The shared integrity-indexed manufacturer catalog also supplies read-only identity and official
update context for Xiaomi/HyperOS, Samsung/One UI, Google Pixel, OnePlus/OxygenOS, OPPO/ColorOS,
realme UI, Nothing OS, Motorola/Lenovo, Sony Xperia, vivo/iQOO, ASUS/ROG Phone, HUAWEI, HONOR,
HMD/Nokia Android, TECNO/Infinix/itel, ZTE/nubia/REDMAGIC, and Fairphone. These broad matches never
grant build, root, unlock, recovery, partition-write, or flash authority; exact model, region,
firmware, package, and physical recovery evidence remain separate requirements.

When a connected phone has reviewed OEM knowledge but no exact build contract, Device Atlas now
offers **Prepare model Pack draft**. ROMVERSE fills the exact reported model/product/codename and
the matched Pack's existing authoritative HTTPS sources, excludes the serial and private data, and
writes a private content-addressed review draft. The proposed identity remains `LIMITED` until a
maintainer corroborates it directly; every build, partition, recovery, root, unlock, wipe, and flash
capability stays locked. The same workflow remains available to maintainers through
`scripts/create_device_pack_draft.py`. Every draft carries `publication_status: draft`, so the
production registry rejects it even if it is manually added to the Pack index.

Device Atlas can export an exact physical-test challenge and import the resulting detached
Ed25519 envelope. Accepted evidence is stored in a bounded workspace vault, reverified on every
read, and shared consistently with Genesis Sequence and Forge Control. The release trust catalog
starts empty rather than inventing a publisher identity, so no local file can grant itself flash
authority.

**ROM Studio** now creates versioned `.romverse` projects and imports protected original
firmware. Imports are copied and SHA-256 hashed on a background worker, stored by content
identity under `original_roms`, marked read-only, and then bounded-inspected in the same import
operation. The UI exposes truthful weighted progress across both phases and retains manual
re-inspection for later evidence refreshes.
Project manifests and working-copy records now use private atomic schema-two storage with an exact
content digest and strict field shapes. Project discovery is bounded and ignores linked project
directories. Symbolic-link sources or pre-planted destinations are rejected, and an import is
discarded if the selected source changes while it is being copied. Valid schema-one project
history remains readable and upgrades on the next successful save; a legacy working-copy record
upgrades only after its bytes are fully hashed for a Time Machine snapshot.
Inspection reports now use the same private, bounded, strict schema-two evidence contract and bind
their complete nested findings to the protected source name and SHA-256. Tampered, oversized,
extra-field, or linked reports are rejected; schema-one reports remain reviewable but are
automatically regenerated from the already verified protected source before extraction. ROMVERSE
also detects source identity changes across inspection/extraction, rejects special or encrypted
archive entries and pre-planted tree links, and materializes the contained tree with private file
and directory modes.
Isolated-tree preparation begins with an animated preflight while ROMVERSE revalidates the source,
inspection evidence, structure, and free-space budget. Once extraction or direct-image staging
starts, the UI switches to one stable total and reports exact extracted or copied output bytes. The
old artificial 15% preflight boundary is not used, and 100% is withheld until the private staging
tree has been atomically published as the project's working tree; a failed partial staging tree is
removed.
The combined **Firmware Import → Automatic Detection** operation begins animated, switches to the
actual protected-source copy percentage when byte units are available, withholds copy completion,
and then holds at the last measured value while bounded structure inspection runs. It reaches 100
only after the strict inspection report is sealed and saved; the former hard-coded 68/32 split is
not used. Standalone Structure Inspection follows the same rule with real source-hash bytes below
completion and an animated metadata phase.
Immediately after automatic source/device detection, ROM Studio creates **Device DNA**: a
source-bound profile covering identity, firmware, partition, security, slot, root, encryption,
fastboot/recovery, evidence, and confidence without guessing unknown values. Its beginner
Capability Map uses SUPPORTED, CAUTION, UNSUPPORTED, and UNCONFIRMED. A persisted
**Compatibility Matrix** then distinguishes Verified, Strong Match, Limited Evidence, Unknown,
and Known Incompatible while keeping “technically possible” separate from “proven compatible.”
Both artifacts are advisory to Guardian and can never authorize bootloader relocking.
For recognized Xiaomi HyperOS builds, Device DNA now compares numeric version components only
after the live and imported codenames, distribution regions, and firmware branches agree. It labels
the result Upgrade Candidate, Same Firmware Version, Downgrade Candidate, Incompatible, or
Unconfirmed; this relationship never grants installation or flash authority. ROM Studio also keeps
the user-supplied firmware responsibility and risk notice visible and requires acknowledgement
before import. Users must obtain the correct package from a trusted official source for their exact
model, region, and current update path. The notice does not purport to exclude any right or
obligation that cannot legally be excluded.
The Matrix uses private bounded strict schema-two persistence and is re-derived from its exact
current Device DNA binding whenever loaded. Extra/coerced/linked records fail closed, and changing
even a correctly re-digested decision cannot override the deterministic result. Schema-one Matrix
history remains readable only while its Device DNA binding is still current and upgrades on the
next assessment.
Device DNA itself is persisted as a private, bounded, strict schema-two profile whose digest covers
every nested fact, partition, capability, warning, and evidence reference. It rejects linked files,
unknown fields, type coercion, invalid cross-references, and even a correctly re-digested attempt to
mark bootloader relocking supported. Valid schema-one profiles remain readable and upgrade on the
next evidence refresh. Structure-derived facts are accepted only from the current persisted
schema-two inspection report or the same strict project-local source blueprint consumed by Forge
readiness. A blueprint must bind the exact project and protected-source hash, preserve
`phone_changed=false`, carry its verified plan/digest, and declare only bounded local build or
inventory authority. It can strengthen source identity, adapter, tool, partition-inventory, and
local build-preparation evidence, but never grants device-write or flash authority; an in-memory
lookalike cannot strengthen the Capability Map.
Root identity follows the same evidence rule. ROMVERSE records a separately sourced root signal
and an evidence-labelled Magisk, KernelSU LKM, conflicting, absent, or unknown Manager candidate.
Companion promotes a candidate only after its full official signer pin matches; the basic Desktop
Device Engine records allowlisted package presence and Ascension performs the stronger temporary
APK signer revalidation before a Manager handoff. A normal non-root ADB shell does not prove that
the phone is unrooted, and an installed Manager does not prove that its root backend is active.
Device DNA therefore keeps root capability at CAUTION or UNCONFIRMED unless direct read-only
evidence justifies the stronger statement; a Manager name remains a candidate, not a verified
active root method.
Firmware format and adapter selection now come from bounded Android structure evidence: a genuine
`payload.bin` selects Payload Atlas even when the archive filename is unknown, a contained
`super.img` selects logical-partition tooling, and an image bundle now produces a private,
hash-backed inventory blueprint for every uniquely named partition image. That blueprint can carry
an untouched protected baseline forward, but modification/rebuild and AVB topology remain CAUTION
until an exact adapter and evidence exist. A readable ordinary ZIP remains UNCONFIRMED, and any
critical traversal/structure finding makes the detected adapter UNSUPPORTED.
Source-blueprint preparation now begins with an animated adapter/tool/metadata phase rather than
inventing milestone percentages. Fastboot/super hashing and partition-bundle inventory switch to
genuine cumulative input-byte percentages when one stable total is known; OTA payload inspection
remains animated while its bounded scan is not measurable. The former 5/42/55/72/88 and 5–90
scales are not used, and 100% appears only after the private source-bound blueprint receipt is
atomically stored. A super image that changes during hashing is rejected.
The same evidence now resolves a source-scoped Forge Arsenal profile automatically: OTA payload,
fastboot/super, and partition-bundle sources request only their relevant inspection tools, while an
exact source-bound Device Pack contract overrides that profile with its reviewed build toolchain.
Tool selection does not claim that a tool is installed and never grants build or flash authority.
For a project with no exact source contract, one unambiguous authorized phone can attach its
highest-priority OEM Pack as read-only knowledge; multiple phones remain unassociated. ROM Studio
recompiles Device DNA when device context changes, and a single phone whose codename conflicts with
the firmware remains visible as UNSUPPORTED instead of being filtered out.

**ROMVERSE Nexus** consumes current Device DNA and Compatibility Matrix evidence. Pathfinder
draws the Understand → Research → Nexus Plan → Guardian Review → Execute → Nexus Verification
route; Foresight predicts affected areas, dependencies, and required verification; Insight explains
each decision and can export a privacy-scrubbed timeline. Build, optional Ascension root preparation,
and Guardian flash-review objectives are planned without granting execution authority. When the
project or either evidence record is absent, Nexus shows the exact missing prerequisite and connects
to a verified Archives guide or ROM Studio without creating a plan, starting a worker, or touching a
phone. Native tables, lists, trees, text editors, and scrolling surfaces use explicit dark viewport
styling so the Desktop remains readable under host themes. The genuine
**Live Console** records tamper-detecting ROM Studio, Device DNA, Compatibility Matrix, and Nexus
events with real progress and explicit success/failure states instead of decorative activity.
Nexus Plans are private bounded strict schema-two records. Every load re-derives understanding,
research gaps, Pathfinder stages, Foresight predictions, Insight decisions, and Guardian
requirements from the exact current Device DNA and Compatibility Matrix; a re-digested edit cannot
advance execution or weaken the never-relock rule. Valid schema-one plans upgrade only through
genuine replanning. ROM DNA uses the same self-verifying pattern for current project/source/tree/
recipe provenance and becomes unavailable immediately when any bound input changes.

**Connected Intelligence** now has repository-tested client contracts for source-attributed online
remediation, privacy-safe Synapse promotion/demotion, provider-independent AI routing, and bounded
fair-use governance. Remediation receipts expose source authority, explicit freshness, exact scope,
independent corroboration, confidence, and the confidence reason; unknown source dates remain
unconfirmed and stale community evidence is downgraded. See
[docs/ONLINE_INTELLIGENCE.md](docs/ONLINE_INTELLIGENCE.md). The public
Synapse, AI, Members, billing, and community services remain explicit production release gates.

Verified ZIP/TAR archives can now be extracted into a contained working tree with strict path,
link, entry, and size guards. Direct `payload.bin` and recognized partition images such as
`super.img`, boot, vbmeta, ext4, and EROFS inputs are transactionally staged under their canonical
role, rehashed while copying, and rejected when the partition role is unknown or ambiguous.
For the exact Xiaomi 17 Pro Max OS4.0.0.23 contract, ROM Studio can preserve fakeroot and
SELinux evidence, generate a deterministic Device Pack plan, execute it into a versioned local
candidate, and unsparse/unpack/byte-compare every logical partition. Signing and flashing remain locked.
The plan status and detected partitions remain visible after restarting the app.
ROM Studio now identifies supported vendor/build metadata independently for every newly imported
base. A filename match is descriptive only: a source-bound Device Pack is retained only when its
immutable archive SHA-256 matches. A different base automatically drops to the best read-only OEM
knowledge Pack, records the reassociation, and keeps build/sign/flash gates locked until an exact
reviewed contract exists. Long-running Studio, Genesis Sequence, Forge Control, Time Machine,
recovery-evidence, and Forge Arsenal operations share a themed progress language. Byte-addressable
work reports real percentage; opaque external-tool stages remain animated and indeterminate rather
than fabricating completion. A shared worker relay bounds and coalesces repeated byte callbacks
before they reach Qt, Genesis, or Live Console across Studio extraction, source preparation,
Debloat, Ascension, recovery evidence, and local phone backup. Multi-gigabyte work therefore cannot
flood the interface with thousands of identical progress events, and a late phase cannot move the
visible bar backwards while the verified background operation continues.
Guardian recovery-evidence registration and refresh now use the exact selected-file bytes. When a
backup and stock-recovery file are checked together, ROMVERSE reports one cumulative total instead
of weighting the two files equally; a near-complete value is held below 100 and terminal completion
is emitted only after the private source-bound evidence record has been saved. ROMVERSE-created
phone-media backup registration likewise waits for the enhanced device-bound receipt update before
reporting completion.

For update-engine OTAs, **Partition Atlas** verifies and maps `payload.bin`,
classifies critical boot-chain/radio partitions, calculates an adaptive free-space budget,
and can selectively extract chosen images with `payload-dumper-go`. Supported ext4, EROFS,
and Android sparse images can be expanded into a contained, browsable filesystem tree.
Selected files can be handed directly to Recipe Forge. These operations are local and never
write to a connected phone. Its scan remains animated while source/tool validation and Payload
Dumper's opaque partition-list command run. Extraction also remains animated until real image files
exist, then switches to exact cumulative output-byte hashing and withholds 100 until the source-bound
manifest is committed. Existing linked or non-regular partition targets fail closed. Filesystem
expansion remains animated while its opaque extractor runs rather than pretending to know a
percentage. Fastboot `super.img` normalization and LP extraction follow the same animated rule;
once supported output images exist, ROMVERSE switches to one stable cumulative output-byte total
while hashing them. The former fixed 4/32/72 milestones are not used, and completion waits for the
source-bound unpack receipt.
Payload discovery accepts canonical filename case variants while still rejecting multiple
candidates. Its schema-two manifest is bounded, private, strict-field, content-digested, and bound
to the protected source, payload path/size/mtime/SHA-256, exact Payload Dumper SHA-256, and every
partition record. Extraction rehashes the payload and tool before using them. Genuine schema-one
records remain readable and are automatically rescanned in the same background operation before
extraction continues; users are not stranded at a technical migration prompt.

**Forge Control** turns the later pipeline into explicit evidence gates for the
workspace, build toolchain, Device Pack build contract, signing, recovery, exact live device,
battery, and boot state. It can prepare only the exact contract inputs, run a versioned local
candidate build on a background worker, run a zero-write pipeline simulation, and export a
content-addressed bundle of small provenance manifests and tool versions. Unsupported OEM
build and recovery contracts stay visibly blocked instead of reporting fake success.
Forge Control also includes ROMVERSE Autopilot. It resolves safe local prerequisites in dependency
order, installs and verifies contract-scoped tools through Forge Arsenal, and continues after each
successful operation. It pauses on one clearly explained authoritative input only when software
cannot truthfully create it; Device Pack contracts, signing identities, recovery tests, and live
device authorization are never fabricated merely to turn a card green.
The direct **Inspect AVB topology** and **Offline signing** controls use the same resolver instead of
ending at an “install this tool” message. They select only missing Payload Dumper/AVBTool evidence,
respect the verified-tool automation setting, rescan the complete tool inventory, and continue the
requested operation only after fresh verification. Private signing keys remain outside ROMVERSE.
Forge Control now applies that same rule at the end of the pipeline: a source-bound local blueprint,
matching phone, AVB/build evidence, and pristine rollback capsule are shown as useful completed local
preparation, but they leave the Device Pack flash and physical-validation cards at **ATTENTION**.
They cannot make the project Guardian-handoff-ready without the signed exact Pack contract and
physical-recovery envelope. The resolution action opens Device Atlas directly instead of restarting
Autopilot in a loop. Imported attestation envelopes are reverified and stored in private `0700`
directories as bounded atomic `0600` files; unsafe linked storage fails closed.
Device Pack build-contract schema two now defines the first machine-readable partition-to-artifact
write contract. It accepts only a bounded ordered set of unique allowed `.img` outputs, explicit
Fastboot/Fastbootd transport and slot choices, mandatory post-write verification, explicit supported
data modes, an unlocked-bootloader requirement, and one exact physical-attestation digest shared
with the flash-validated AVB policy. Userdata, metadata, relock/unlock/flashing-control targets,
implicit slot suffixes, unknown outputs, mismatched evidence, and any relock permission fail closed.
The schema is signed intent, not an executable manifest: Guardian still keeps writes and commands
empty until every declared image is bound to the current immutable build receipt.
Guardian can now perform that evidence step for future flash-certified Packs. It resolves every
declared image only from the current verified local-build or exact offline-signing receipt, rejects
stale handoffs and unsupported keep-data/wipe-data modes, rehashes every byte on a managed background
worker with real progress, and stores a strict private content-digested binding. A file change still
fails if its size and modification time are restored. The review can display each ordered partition,
image SHA-256, transport, slot and verification rule as **hash-bound for review**, while commands,
final consent, execution authority and phone changes remain absent. Running multi-gigabyte hashing
outside Qt's UI thread prevents it from producing a false “Python is not responding” freeze.
Forge Control refreshes detach stale cards immediately, preserve the scroll content's natural
height, and group build preparation separately from workflow actions. This prevents old evidence
rows or compressed footer buttons from overlapping after automatic refresh. The footer reports
blocked and attention counts separately so an amber contract cannot look complete.
For an exact flash-validated custom AVB re-chain, Forge Control can export a content-addressed
offline signing request and import the resulting `product.img` and `vbmeta_system.img`.
ROMVERSE verifies the Pack-authorized public-key fingerprint, algorithm, rollback fields,
descriptors, sizes, and hashes while keeping every private key outside the app. Reference-only
or unsigned policies cannot open this path.
Signing requests, external manifests, imported evidence, and local receipts are byte-bounded and
exact-schema. Workspace records use private atomic persistence; symlinked records, manifests,
images, or intermediate evidence directories fail closed. A returned bundle must contain the exact
content-addressed manifest ROMVERSE exported. New schema-two receipts use the import-time verified
hash plus immutable size/mtime identity for responsive reloads; a valid schema-one receipt is fully
rehashed once and migrated without losing the project.

**Guardian local-drive backup** is available directly from the Genesis backup card. It copies only
the user-selected shared-storage folders through approved read-only ADB pulls, shows real progress,
creates a ZIP with per-file hashes, and verifies the archive, sidecar, and embedded manifest. The
archive stays outside the ROMVERSE workspace. ROMVERSE-created backup evidence is privacy-safely
bound to the exact phone, so another phone's archive cannot make the connected device ready.
ADB pull phases remain animated because this transport does not provide a trustworthy total here.
After inventory, archive preparation switches to exact cumulative source-file bytes, with no fixed
55/38 or 82/18 phase weighting. Completion is withheld through archive validation and, for a
project-bound backup, through the final recovery-evidence receipt update.
App-private data, credentials, messages, eSIMs, authenticators, and secure folders remain outside
this route and require a separate provider or app-specific backup.
The final keep-data or wipe-data choice is stored as a private bounded schema-two Guardian handoff.
It is bound to a stable digest of the current readiness gates as well as the protected source and
exact connected phone, so refreshing an unchanged report does not discard the choice, while any
real evidence change returns Genesis to Guardian review. Linked, oversized, extra-field, malformed,
source-rebound, or safety-invariant-breaking records fail closed. Genuine schema-one history remains
readable for audit but cannot advance Genesis until the user creates a fresh current handoff.
An existing current handoff—or a future handoff created after a flash-certified Pack becomes
available—routes to a real **Guardian Manifest Review** instead of reopening Forge Control.
The review is command-free and binds the current readiness evidence, protected source, exact phone,
data choice, and Device Pack. It lists the checks that passed and the exact missing authority. Current
Device Packs do not yet carry a signed, physically verified partition-to-artifact write contract, so
the review truthfully shows **PARTITION WRITES: NONE AUTHORIZED**, offers no final-consent or execution
button, and keeps `execution_authority: none`. Stored review packets are bounded, private, strict
schema-two records; genuine command-free schema-one history remains readable for audit. Tampering,
source/device/Pack/binding rebinding, stale readiness, links, or oversized files fail
closed. ROMVERSE never derives write authority from image filenames or a reference-only AVB policy.
Guardian Manifest Review starts with an honest animated preflight, then displays only the genuine
artifact-binding byte percentage while declared images are rehashed. The binding phase's terminal
100 is withheld while the broader command-free manifest is compiled; the review reaches 100 only
after that final evidence exists. The former synthetic 90% and 94% milestones are not used.
Time Machine recovery records use a digested schema-two contract and bounded private atomic storage
for both the public-safe evidence and its separate `0600` absolute locator. Extra fields, oversized
or symlinked records, unsafe roles, changed project/source identity, and locators redirected into
the workspace fail closed. Schema-one evidence remains readable for compatibility but cannot make
Guardian ready until **Verify evidence** fully rehashes every registered file and writes schema two.

**Ascension Protocol** is ROM Studio's Guardian-locked root-preparation workflow. It compares the
protected firmware and live device through one exact-source identity binding, consumes the current
Device DNA digest, discovers contained `boot.img`/`init_boot.img` candidates, checks bootloader and
recovery evidence, records kernel/KMI context, and accepts only stable manager APKs from the official
Magisk and KernelSU repositories with their published SHA-256. Conflicting source identities block
the route instead of being guessed. ROMVERSE pins each official Android signing certificate and
rechecks the package signature, signer, package identity, size, and hash whenever a vaulted manager
is reused and again at Guardian phone handoff; an editable local receipt is never sufficient trust.
The automatic route and exact-kernel KernelSU support decision use bounded private atomic evidence.
Their loaders reject linked or redirected storage, oversized or extra-field records, wrong
Boolean/integer types even when the outer digest is recomputed, stale source/Device DNA/phone/kernel
bindings, and a Manager that no longer passes the official vault verifier. The UI labels the route
as private bounded evidence and keeps execution authority at `none`.
Its **Learn this stage** action pauses only when no safe operation is running, preserves verified
project evidence, and opens ROMVERSE Archives on the exact current stage of one authoritative
nine-stage beginner guide. That explanatory handoff has no execution authority and cannot approve,
unlock, root, wipe, flash, or relock a phone.
One centralized checkpoint model now owns the visible tracker, **Next Safe Action**, status copy,
Archives handoff, and Live Console stage numbers: Prerequisites, Official manager, Patch capsule,
Phone handoff, Patched image, ROM integration, Build seal, Device binding, and Guardian review. A
manually verified patched image may satisfy the phone-handoff checkpoint, but it never invents later
integration, seal, device-binding, or Guardian evidence.
The manager vault itself is a contained private boundary: tag directories are bounded and
non-linked, APKs and receipts use `0600`, directories use `0700`, and schema-two receipts require an
exact nested shape plus their digest. Redirected vault folders, linked tag directories, entry floods,
extra or mistyped fields, and a same-byte APK rebound outside its exact content-addressed path all
fail closed. Genuine schema-one receipts remain load-compatible but cannot claim online freshness.
Official Magisk and KernelSU downloads expose their declared byte total without allowing an
unfinished 99.5% transfer to round up to success. Download completion is held below 100 while
ROMVERSE validates APK structure, package identity, the pinned signing certificate, private vault
permissions, and the schema-two receipt; terminal progress is emitted only after that receipt exists.
Local patch-capsule creation also requires that freshly revalidated vault identity and refuses
caller-supplied metadata or alternate paths. The exact capsule manager and approved install plan
must still match immediately before ADB runs. Automatic online resolution begins only while the
Ascension window is visible; closing it before startup cancels the queued lookup instead of leaving
hidden network work behind.
Before that lookup, Ascension resolves and reverifies only AAPT2 and APK Signer when either is
missing, because no downloaded manager may enter the trusted vault without real package and signing
evidence. If the isolated tree is not prepared yet, Ascension can automatically stage a structurally
safe fastboot/factory archive, direct named Android boot image, or standalone payload after verifying
its source-bound inspection and extraction-space budget. Unsafe archives and renamed images without
one confirmed partition role stay blocked. When one contained `payload.bin` is then the unambiguous
source, the resolver obtains only Python and Payload Dumper, rebuilds ROM Studio's verified tool
services, and resumes the boot-image scan at the interrupted step. A cancelled or incomplete tool
resolution stops before trusting a manager or patch target and reports the exact remaining tools; it
never substitutes guessed evidence.
KernelSU's exact-phone support preflight now hashes and inspects the verified Manager APK on a
background worker with genuine byte/container progress, keeping the Ascension window responsive.
The subsequent ADB application install is shown as indeterminate because Android exposes no
trustworthy completion percentage; ROMVERSE does not manufacture one.
Local patch-capsule preparation follows the same rule: source, rollback, and Manager trust
revalidation remains animated until measurable work starts, then the pristine boot target and
official Manager copy plus independent SHA-256 rereads report genuine byte-derived progress.
Already verified content-addressed capsule files are reused rather than rewritten.
Only a genuine provider connection failure can fall back to a vaulted manager. Rejected metadata,
URL, size, digest, package, or signing-certificate evidence always fails closed instead of being
misreported as an outage. Offline fallback requires a fully revalidated cache no more than 30 days
old and a tamper-evident v2 freshness receipt; older v1 receipts remain load-compatible but cannot
claim offline freshness until ROMVERSE completes one new official online check. The Desktop card is
amber and says `ONLINE FRESHNESS PENDING` whenever that bounded cache route is active.
When no safe cache can satisfy a typed provider outage, visible Ascension performs at most two
short, bounded automatic retries and records each attempt in Live Console. The retry timer is
cancelled on close, route change, or fresh device context; exhausting it exposes a manual safe retry.
Trust-policy failures are deliberately excluded from this recovery path and never retried.
After the user finishes the physical patch in the verified manager, ROMVERSE can perform an
explicitly approved filename-only Downloads scan. Discovery is bound to the selected route: Magisk
never offers a KernelSU output and KernelSU never offers a Magisk output. The chosen file then needs
a separate exact-path Guardian approval, and the service revalidates its manager family, phone,
project staging path, and approval digest before copying it for source-bound structural inspection.
Matching phone outputs are ordered by modification time with the newest recommendation preselected.
A phone pull remains indeterminate because ADB supplies no trustworthy bounded units. Once the
candidate reaches isolated local storage and passes lineage preflight, both phone retrieval and
manual import switch to genuine byte-derived progress for the protected vault copy and independent
SHA-256 reread; fixed 8/45/62/88 milestone percentages are not used.
A manually imported file whose standard name positively identifies the other manager is rejected;
an unrecognized name remains unconfirmed and must pass the same boot-structure and capsule checks
without ROMVERSE inventing manager certainty.
Every successful filename scan now creates a tamper-evident, ten-minute discovery receipt bound to
the exact handoff, pseudonymous phone, project, and selected manager. The receipt stores counts and
SHA-256 filename references rather than raw phone filenames; retrieval refuses a candidate absent
from that fresh receipt. Found and not-found outcomes survive refresh as privacy-safe diagnostics
and are explained in ROMVERSE Live Console with execution authority remaining `none`.
Companion reads the phone-handoff and verified-manager-open receipts through execution-free evidence
loaders, rechecks their capsule/release/device binding, and advances its beginner guidance to the
actual patch stage instead of repeating an already completed handoff. These readers cannot construct
or execute ADB operations.
Patched-image receipts now use AOSP boot-layout-aware immutable lineage checks for header versions
0 through 4. ROMVERSE normalizes only manager-controlled section sizes/checksums, then compares the
remaining header identity. KernelSU LKM must preserve an existing kernel byte-for-byte because its
official route modifies the ramdisk; a mismatch is blocked. An unchanged Magisk kernel earns high
confidence, while a Magisk kernel change remains visible as caution because Magisk officially
supports specific legacy/Samsung kernel patches. Kernel-less `init_boot` evidence remains limited
rather than being presented as absolute source proof. Older structural receipts are upgraded only
after passing the stronger check. References: [AOSP boot image header](https://source.android.com/docs/core/architecture/bootloader/boot-image-header),
[Magisk patch tools](https://topjohnwu.github.io/Magisk/tools.html), and
[KernelSU LKM installation](https://github.com/tiann/KernelSU/blob/main/website/docs/guide/installation.md).
Its real nine-stage progress, explanations, pauses, and failures are recorded in ROMVERSE Live
Console and relayed to Companion. Link v6 also carries a fail-closed, privacy-bounded manager
identity: verified state, official allowlisted repository, release tag, exact asset name, and only
the first 16 SHA-256 characters. It never carries a local vault path, complete hash, approval, or
command, and Companion renders the green identity card only after Desktop revalidates the full APK.
Companion also keeps the automatic ROMVERSE work separate from the one beginner action that may
need the user: both explanations are bounded read-only text and neither grants execution authority.
Companion can then offer a user-triggered manager handoff only after Android reports the exact
allowlisted package and its complete installed certificate digest matches the pinned official signer;
the action opens the manager and has no patching or device-write capability.
Desktop now offers the same beginner handoff after the approved manager install and source-image
transfer. Guardian first resolves only the allowlisted installed package, then—with a second exact
approval—copies only its base APK into isolated temporary workspace storage, requires the complete
official SHA-256, package identity, and pinned signing certificate, deletes the temporary copy, and
opens that one package. A changed APK, changed Android install path, different phone, expired
approval, unsafe path, or alternate package blocks the launch. The privacy-safe receipt stores no
phone serial or Android install path and grants no future execution authority. Guardian-approved
Manager installation, pristine-image transfer, installed-APK retrieval, signature checking, and
Manager launch remain visibly indeterminate because ADB does not expose trustworthy bounded units
for those operations. ROMVERSE displays their real terminal receipt instead of fixed stage
percentages.
The Desktop primary action now treats that verified Manager launch as a distinct evidence-backed
stage: a completed phone handoff cannot skip straight to output discovery, and a failed or cancelled
launch remains on a truthful `Open verified Manager` retry path until a valid launch receipt exists.
Newly observed existing-root, missing-device, identity-mismatch, or other blocking route evidence
also outranks historical phone-handoff receipts. Reversible local integration may finish after a
patched image is already verified, but ROMVERSE cannot reuse stale phone preparation to bypass the
current safety assessment.
After the verified Manager opens, Ascension can start a separately approved nine-minute automatic
output watch. It polls only Downloads filenames at a bounded interval, uses the same method-bound
classifier and short-lived approval as manual discovery, displays real elapsed-time progress, and
flows a detected result into the existing exact-file review. It reads no candidate content until
that separate retrieval approval, ignores the other manager family, and stops on success, timeout,
disconnect, route/evidence change, failure, or dialog close—so no hidden polling survives Ascension.
Acquisition and integration are preparation steps; they do not unlock, wipe, root, flash, or relock
the phone.
Reversible local ROM integration begins with an honest animated revalidation phase. Once the exact
source, target, patched image, rollback path, and available space are established, ROMVERSE measures
six complete byte passes: pristine-target hashing, rollback-snapshot copy and hash, patched-image
copy and hash, and final integrated-target hashing. It reaches 100 only after the transaction and
strict receipt are committed. **Build Seal** remains animated while it rehashes the integrated
artifact and verifies the broader working tree because that full-tree freeze has no trustworthy
bounded total; it never substitutes weighted stage percentages.
Once the exact final handoff is sealed, **Guardian Consequence Review** presents the phone,
partition, slot, patched-image digest, keep-data route, rollback, boot risk, and permanent
bootloader-relock prohibition as individual acknowledgements. The user must check every item and
type `ASCEND`; the resulting exact-handoff-bound record expires after ten minutes and still carries
`execution_authority: none`, no commands, no wipe authority, and no phone-change claim.
The root plan, Guardian manifest, final handoff, and consequence review now share strict private
bounded atomic storage. Every load checks the exact record shape and primitive types before
re-deriving the complete source, Device DNA, image, backup, phone, slot, Pack, and no-authority
chain. Extra fields, sparse oversized files, links, redirected directories, and correctly
re-digested Boolean/integer substitutions are discarded. The UI explains that invalid evidence
returns Ascension to the first affected step rather than preserving stale consent.
The upstream rollback capsule, root patch capsule, patched-image receipt, reversible integration
transaction/receipt, rollback snapshot, and build seal now use the same bounded, private,
link-safe evidence boundary. Their loaders require exact schemas and primitive types, then rehash
the current protected source, manager, boot image, snapshot, integrated target, and sealed artifact.
A broken recovery transaction stops before changing the isolated ROM input; a receipt-storage
failure restores the pristine local image. These records contain no phone command, flash authority,
wipe authority, unlock authority, or bootloader-relock path.
The explicitly approved phone-preparation receipt, installed-Manager open receipt, and filename-only
patched-output discovery now use the same private bounded exact-schema store with private historical
copies. Current source capsule, official Manager, phone pseudonym and discovery set are revalidated;
extra or mistyped fields, links, redirected storage, oversized records, changed artifacts, and stale
ten-minute discoveries fail closed. These records describe already observed preparation only. They
cannot patch or flash an image, apply root, unlock, wipe, relock, or grant later execution authority.

**ROMVERSE Genesis Sequence** replaces the former Automatic Guided Setup. It is a full-size,
evidence-driven workspace covering fifteen stages from project creation and protected
firmware import through build/sign, Guardian flash, and first-boot verification. Each stage
shows plain-language instruction, live evidence, recommendations, blockers, and the exact
next outcome. Safe local stages invoke the real ROM Studio workers and resume from saved
project evidence. Failures are classified into actionable diagnoses; known incomplete
transaction files can be cleaned automatically inside tightly bounded workspace paths.
Every stage also offers **Learn this stage**, which opens ROMVERSE Archives on a bounded,
stage-specific verified guide instead of leaving a beginner to translate a technical blocker or
search the knowledge library manually. Returning to Genesis preserves the selected stage and
project state; guidance never changes evidence, approval, or Guardian authority.
Its Device DNA stage now requests a genuine fresh read-only Android scan instead of rereading a
cached result, recompiles Device DNA, displays the Capability Map summary and key source/tool
states, and cannot complete without a current profile and map. A failed ADB refresh clears ROM
Studio's stale device identity and leaves Genesis paused with the real diagnostic; it never treats
the last-seen phone as current evidence.
Verified retail naming survives a restart only for the same exact device identity. ROMVERSE can
reuse a private, bounded receipt created from an on-device property, an OEM-owned HTTPS source, or
two independent agreeing public sources. A Device Pack name is reaccepted only while the exact Pack
is still installed; malformed, rewritten, oversized, linked, redirected, or identity-mismatched
receipts are discarded and the name remains unconfirmed.
Before Nebula Debloat opens an image-based OTA, fastboot, or `super.img` source, Genesis now resolves
the narrow read-only materialization profile first: Payload Dumper or LP Unpack as appropriate,
`simg2img`, the ext4 browser, the EROFS reader, and fakeroot metadata support. Forge Arsenal selects
only missing items, uses its existing managed/operating-system authorization boundaries, rescans the complete
inventory, and opens the app review only when those tools are genuinely available. Closing or
failing setup leaves Debloat visibly blocked instead of presenting an empty inventory.
Nebula's progress now follows the same evidence rule. Unknown-size directory discovery and external
payload, LP, sparse, ext4, or EROFS materialization remain animated. Once the complete candidate set
is known, the bar switches to the exact number of app records catalogued and reaches 100 only after
the scan evidence is committed. Applying a selection remains animated through source revalidation,
full-tree hashing, rollback snapshot creation, removal, and final verification because those mixed
operations have no one trustworthy total; only the committed transaction receipt completes it.
Before Genesis asks whether the ROM should be rooted, it now resolves the current Ascension route
on a managed background worker. The decision card shows SUPPORTED, CAUTION, BLOCKED, or UNCONFIRMED;
names Magisk or KernelSU LKM only when the source, Device DNA, and exact connected-phone evidence
support it; identifies the source image target; and explains what ROMVERSE automates versus what the
user and Guardian must still approve. This preview has no commands or phone-write authority and
always states that bootloader relocking is prohibited.
The exact supported local build is marked successful only after output hashes and byte-for-byte
logical-partition verification. Offline signing verification is available only under an exact
authorized Device Pack; flash and first-boot execution remain visibly Guardian-locked until
their remaining evidence contracts exist. A stable pre-flash Boot Observatory sample remains
useful comparison evidence, but it cannot advance Genesis or be labeled verified first boot
without a matching Guardian flash receipt.
OTA/fastboot source blueprints, local-build attempts/results, super verification, and AVB topology
now share ROMVERSE's byte-bounded private atomic evidence store. Loaders reject symlinked or
non-regular paths, oversized/extra-field records, invalid nested collections, unsafe references,
missing logs/artifacts, stale project bindings, and changed source metadata. New AVB inspections
write schema-three image size/mtime identity so reload stays bounded without hashing multi-gigabyte
images on the UI thread; legacy schema two remains readable for project history but cannot create a
new connected `verified working` outcome.
The offline signing ceremony applies the same producer-side trust boundary to its request,
manifest, evidence, and receipt chain; it cannot treat detached signed files as an authorized
response merely because AVBTool can parse them.
Genesis also publishes a genuine 15-stage lifecycle to ROMVERSE Live Console and Companion:
evidence-derived overall progress, real safe-operation percentage, the current blocker and next
recommendation, project-switch isolation, and explicit paused/failed states. Completion appears
only after every stage—including a successful Guardian flash receipt and stable first-boot
observation—is backed by current evidence.
Genesis crash-resume state now uses one private atomic schema-five record with an exact bounded
shape and content digest. ROM Studio project cards consume that same authoritative record and show
the real saved stage, an earlier evidence-required stage, or Attention; the obsolete seven-step guided summary and duplicate
wizard have been removed. Strict schema-two through schema-four history remains readable and upgrades
only on the next intentional save. A linked, oversized, altered, extra-field or type-coerced state
fails closed, and Genesis explains the safe recovery instead of navigating away without saving.
Before each ROM Studio project operation, a bounded background recovery pass now removes only
recognized interrupted ROMVERSE transaction artifacts. It shallowly checks the import, project,
working-copy, payload, filesystem, Time Machine, Recipe, Forge, and build-verification staging
locations without recursively searching a completed ROM tree. Linked or overfull transaction roots
are contained, outside targets and protected originals remain untouched, and the visible recovery
message records that no phone state or execution authority changed and relocking remains forbidden.
Recipe Forger publishes the same truthful lifecycle for its six design stages. Live Console shows
the current validation requirement, preserves forward progress during multi-step refinement, marks
an unfinished design as paused rather than failed, and reports success only after the contained
targets and conflict scan pass and the execution-locked `recipe.romverse` manifest is saved.

ROM Studio can also perform bounded **Structure Inspection** after re-verifying the
protected original. It identifies common Android containers, inventories archive metadata
and partition signals, and flags traversal paths, links, encryption, entry limits, and
extreme compression without extracting or mounting content.

**ROMVERSE Recipe Forge** gives Recipe creation the same full-size guided treatment as
Genesis Sequence. It walks through identity, operation selection, a lazy contained-tree
browser, context-sensitive configuration, Guardian review, and a final digest receipt.
Every stage includes **Learn this stage**, opening the matching section of one authoritative
six-stage Archives guide in place. The active name, purpose, operation, target, parameters, and
draft steps remain untouched while the guide is open, so learning cannot discard or silently alter
an unfinished Recipe.
Unfinished designs are also autosaved as private, bounded, source-bound and digest-checked draft
records. Reopening Recipe Forger restores the safe fields and exact stage with a visible
`DRAFT RESUMED` marker. Targets are revalidated against the current isolated tree; a missing,
redirected, or linked target automatically moves the user back to selection, and a completed saved
Recipe removes the obsolete draft. A draft is never a Recipe, approval, or execution receipt.
The final Recipe manifest now uses a separate private atomic schema-two storage envelope with a
strict top-level and step shape, bounded size/count/text fields, safe relative targets, a content
digest, preserved Recipe digest, and mandatory `execution_locked: true`. Recipe Forger reloads and
reverifies the stored bytes before showing completion. Genuine schema-one manifests remain readable
through the same bounded no-link loader and upgrade on their next intentional save without changing
their Recipe digest or weakening Guardian.
Inspect, replace-file, set-property, and remove-path operations are explained in place;
unsafe or incomplete inputs cannot advance. The resulting Recipe remains execution-locked
until target preview and explicit Guardian approval. Recipes may contain multiple bounded
steps; Recipe Forge detects duplicate/overlapping mutations and presents a bounded,
read-only change preview, including unified diffs for property edits.

**ROMVERSE Recipes** now run real local transformations inside extracted working trees.
Supported bounded steps are inspect, replace file, set property, and remove package/path.
Approval binds the recipe digest, complete tree hash, and replacement-file contents. Before
any change, ROMVERSE snapshots every affected target outside the working tree. Multi-step
runs use atomic writes and post-step verification; a failure restores all snapshotted
targets automatically. Verified snapshots can also be restored later from ROM Studio.
Protected originals and connected phones are never recipe targets.
Execution begins with an animated approval/tree/snapshot preflight, then switches to a real
completed-step count for multi-step Recipes. The former fixed 3/25/95 milestones are not used;
final tree hashing stays below completion, and 100% is emitted only after the private project-level
execution receipt has been saved.
Recipe execution evidence now follows the same fail-closed boundary as the authored manifest.
New run receipts and rollback snapshots use private atomic schema-two records with exact bounded
shapes and content digests. Readiness re-derives the Recipe step identities, original tree hash,
snapshot identity, affected-target set and rollback hashes before a mutating Recipe can become
verified. Linked, oversized, renamed, extra-field, re-bound or altered records are rejected and are
excluded from exported evidence bundles. Strict schema-one run receipts and snapshots remain
readable through the bounded loader, but they cannot bypass those current Recipe/rollback checks.

**App Launchpad** now provides the first intentionally state-changing Guardian workflow.
ROMVERSE inspects the APK container without extracting it, streams a SHA-256 identity,
checks battery and free-space evidence, binds approval to the exact APK plan and selected
device, then revalidates the file immediately before executing the bounded `adb install`
form. Work runs off the UI thread and produces privacy-safe local preflight and result
receipts. Those receipts use atomic replacement and SHA-256 integrity fingerprints; Guardian
verifies both the preflight and the actual install outcome before displaying them. If the
preflight receipt cannot be persisted, approval stays locked. If Android reports success but
the result receipt cannot be saved, ROMVERSE reports that evidence failure honestly while the
append-only Guardian operation audit remains authoritative. Installation never begins without
two explicit user confirmations. APK hashing and bounded container inspection now report real,
monotonic measured progress in App Launchpad. The final Android install remains visibly
indeterminate because ADB does not provide a dependable completion percentage; ROMVERSE never
invents one.
If the APK and phone pass but ADB is unavailable, App Launchpad presents **Resolve Platform
Tools** instead of a disabled approval dead end. The scoped resolver publishes its freshly
verified inventory to MainWindow, which atomically activates Device Engine and every dependent
Desktop service. Only then does the button return to **Review and approve exact plan**; failed
verification retains the local inspection while keeping approval and phone changes locked.
When package identity or signer evidence is partial, App Launchpad exposes **Improve APK identity
verification**. It resolves only AAPT2 and APK Signer, then automatically re-inspects the same
selected APK with those freshly verified executables. If either tool remains unavailable, the
existing bounded inspection is retained and no approval or phone operation starts.
When Android rejects an install with one recognized Package Manager failure identity, App
Launchpad stores only that bounded code plus a workspace-key-bound receipt identity—never raw
command output—and deterministically selects the matching verified Archives fix. Conflicting or
unknown codes are not guessed, a superseded or altered receipt fails the handoff visibly, and
opening guidance never retries the install. Archives preserves a navigation-only source banner so
the user can return to the unchanged App Launchpad workflow after reviewing the guide. App
Launchpad itself uses a dark responsive scrolling surface so complete APK identity and failure
evidence remain readable at supported window sizes.

**ROMVERSE Galaxy Community Lab** replaces the former Desktop placeholder and Companion
single-note prototype. Desktop topics, comments, votes, search, deletion, and portable JSON
export are stored atomically under the local workspace. Companion provides matching durable
local topics, replies, votes, search, deletion, and share-copy actions. Both stores validate
collection-wide topic/reply identity, timestamp and size boundaries and bind each successful
save to a SHA-256 integrity fingerprint. Tampered or corrupt data is preserved and rejected
rather than silently replaced; valid legacy data remains readable and upgrades only on the
next successful save. Both surfaces display verified, legacy, or rejected evidence states and
state clearly that they are offline and private: no account, public user, moderation status,
or network synchronization is simulated. Online publishing remains locked until the future
Galaxy service has authentication, privacy, moderation, abuse prevention, and secure sync.

**Time Machine** now has a functional local ROM recovery console. It inventories ROM Studio
working-baseline snapshots, verifies their SHA-256 identities off the UI thread, and restores
only after a typed digest-bound approval. A restore preserves the current baseline first,
uses an atomic replacement, verifies the final hash, updates the working-copy record, and
writes a versioned receipt. Snapshot verification reports genuine byte-derived progress through
the shared bounded UI relay. The multi-phase restore remains honestly indeterminate instead of
showing a fabricated percentage. New snapshots use bounded private schema-two records bound to their
exact project path, size, mtime, and digest. Symlinked/oversized/extra-field records, redirected
working targets, and changed artifacts fail closed. Legacy snapshots remain visible with a clear
**Verify** action but cannot satisfy Genesis or restore readiness until a background full hash
upgrades them. Rollback planning reads bounded metadata on the UI path; the background restore
worker rehashes the selected bytes and binds the pre-restore safety snapshot before replacement.
Connected-device recovery-readiness plans are written atomically,
use a pseudonymous device key, carry a tamper-evident digest, and state `phone_data_copied: false`
and `execution_authority: none`. Guardian verifies the digest before displaying the evidence;
legacy plans remain reviewable but are labeled unverified. Separately, **Back up phone to local
drive** copies only the user-selected Camera, Pictures, Videos, Downloads, and Documents folders
through Guardian's exact read-only ADB pull form. It creates a private ZIP with per-file hashes,
an embedded bounded manifest, and a private integrity-bound sidecar; it does not claim app-private
data, contacts, messages, credentials, eSIMs, secure folders, or partition coverage. If Platform
Tools are unavailable, Time Machine resolves them in place and continues only after the shared
runtime is freshly verified. One immutable reviewed backup plan authorizes the session, while each
exact folder transfer receives a fresh short-lived child approval immediately before it runs so a
large earlier folder cannot expire later reviewed scopes. ROMVERSE still does not restore phone
data or partitions.

**Health Timeline** stores redacted diagnostic snapshots as atomic, integrity-bound evidence.
Each new snapshot carries a SHA-256 fingerprint and a pseudonymous device key; raw serials and
build fingerprints are rejected before persistence. The timeline distinguishes verified evidence
from readable legacy snapshots, preserves damaged or tampered files for diagnosis, excludes them
from trends, and explains every rejection instead of silently hiding it. Exports reverify the exact
selected content before writing an atomic copy.

## Current safety boundary

The current build does **not** flash, unlock, reboot, push arbitrary files, delete, remount,
root, downgrade applications, or modify firmware. The only enabled device mutation is an
explicitly reviewed APK installation bound to an unchanged file hash and the selected
authorized device. Guardian denies everything outside its read-only probe allowlist and
this exact approval-gated install form. ADB serials are masked in the UI by default and all
subprocesses use argument arrays without a shell.

The **Command Console** uses that same Guardian gateway and append-only audit chain. Its
device probes are bound to the selected authorized device, visible output masks the serial,
and host platform/Python details are collected in-process. It has no direct subprocess
escape hatch and accepts only its exact read-only presets. A genuine indeterminate operation bar
remains visible while a probe runs, and a single-operation lock prevents a second check from
overwriting the active worker or its Companion Live Console evidence binding.
Selecting an ADB probe without an active runtime changes the action to **Resolve Platform Tools**.
ROMVERSE completes the scoped verification first and runs the requested probe only if the shared
Guardian/ADB runtime was genuinely activated; otherwise it reports that nothing ran and no phone
data changed. Command Deck uses the same in-place resolver at startup, so missing Platform Tools no
longer require an application restart before Device Engine can scan.

Command Deck's **Repair Phone** mission now subscribes to the current Quantum Optimizer report. When
an actionable finding has an exact deterministic route, the card is visually promoted and names the
topic-specific plan (for example, **STORAGE PLAN READY**); opening it preserves that finding in
Recovery Bay. A healthy report opens an explicit general intake instead, while mismatched/stale
Recovery evidence shows a refresh boundary. None of these navigation paths starts a session, worker,
research lookup, approval, or phone operation.

Command Deck's **Guardian** mission is now owned by Guardian Core rather than a static “safety
active” label. It begins at **VERIFY REQUIRED**, mirrors the genuine background verification,
shows **INTEGRITY VERIFIED** only after both audit and approval chains pass, and changes to
**REVERIFY REQUIRED** when the active ledger, a verified archive, or approval evidence changes.
The destination displays the same lifecycle in a visible handoff and navigation starts no approval,
command, build, flash, or phone action.

Desktop navigation also has a keyboard-first **Ctrl+K command palette**. It searches every
canonical sidebar page plus every registered implemented internal feature, including Device Portal,
Device Engine, System Scan, Genesis Sequence, Ascension Protocol, Device DNA, Compatibility Matrix,
Pre-Build Simulation, Partition Atlas, Recipe Forge, Forge Control, ROM DNA, Boot Observatory,
Recovery Autopilot, ROMVERSE Intelligence, ROMVERSE Synapse, Health Review, Pathfinder, Foresight,
and Insight—including familiar earlier feature names. Each internal result opens its exact Command
Deck, ROM Studio, Quantum Optimizer, Recovery Bay, Archives, or Nexus owner and displays the current
feature evidence or prerequisite without clicking it. Every visible Command Deck launch-card label
is searchable. Pathfinder, Foresight, and Insight reveal their matching current-plan panels without
generating or adapting a plan, and Synapse source events return to Archives rather than Nexus.
Live Console and legacy Activity source actions preserve the producer's exact nested identity: an
Ascension, Forge Control, Device DNA, System Scan, Recovery Autopilot, or Synapse event restores its
current project when available and opens that precise evidence/prerequisite handoff rather than only
the containing page. Unknown or stale sources still stop visibly, and source navigation runs nothing.
Guided Mode keeps Architect-only destinations out of results; Expert Mode reveals them. The ROM
Studio Architect control changes and persists that same authoritative Desktop experience rather
than showing a decorative status. Neither transition can run a tool, open an operation dialog,
start a device operation, grant approval, or bypass Guardian.

The Desktop shell can collapse that same authoritative navigation into a permanent icon rail with
**Ctrl+B**, preserving the current page, active highlight, tooltips, and accessible names. A
reversible **Focus workspace** (`Ctrl+Shift+F`, `Esc` to leave) hides the rail and connection footer
without recreating the page or disturbing its evidence, workers, project, or Guardian state. The
top workspace bar keeps the canonical group/page breadcrumb, connectivity state, and a visible
navigation-only search action available in every layout.

The **ROMVERSE Activity Center** replaces decorative dashboard history with a connected, searchable
view of durable local events from completed device scans, saved diagnostics, ROM Studio work, Time
Machine, Recovery Bay planning, Quantum Optimizer cleanup, App Launchpad, and the offline Galaxy
lab. Outcome/category filters, truthful counts, evidence details, and canonical source-page handoffs
make each summary useful without duplicating the source feature. Health Timeline now stays focused
on saved diagnostic snapshots and health change.

The underlying ledger is byte-bounded, strict-schema, atomic, private, and exportable as redacted
JSON. Raw serials, console output, build fingerprints, and Galaxy message text remain excluded.
Linked, oversized, malformed, or extra-field data fails closed and is preserved rather than
overwritten; an Activity Center handoff navigates only and grants no operation authority.

Desktop **Command Deck Settings** now exposes only controls with current runtime consumers: device
scan cadence, verified online/community research, Synapse contribution policy, Forge Arsenal tool
acquisition, meaningful Desktop notifications, reduced motion, local backup destination, and Members
endpoints. Foreground milestones and attention states use a non-blocking glass alert inside ROMVERSE;
when ROMVERSE is in the background and the platform supports it, the same bounded alert uses the
desktop notification area instead of being duplicated in both places. Repeated identical events are
temporarily deduplicated, and notifications can be disabled without affecting Live Console or
operation evidence. Historical AI budget and update-channel values remain readable and preserved for
settings-file compatibility but are not presented as working switches. The dialog states that public
AI provider policy and signed automatic updates remain unavailable until their production services
exist.

Desktop **Members** browser authorization and polling now use the same honest background-operation
language: the card displays an indeterminate bar only while contacting the configured HTTPS service,
locks duplicate actions, and clears the busy state on every success or visible failure. The client
still accepts membership only from the configured server response and never invents entitlement.

Companion keeps a separate bounded private activity history in Android app-private storage.
It survives restarts, deduplicates routine health refreshes, supports a privacy-safe clipboard
report and explicit local clearing, and preserves unreadable source data for diagnosis. APK
filenames, fingerprints, device identifiers, and Galaxy message text are excluded.

Companion now uses the approved Galaxy navigation shell: a true Android edge-swipe glass drawer,
a persistent glass bottom bar with one bottom-left Home route, and a fixed top status bar with the
live online/offline indicator. The Home command deck displays genuine read-only health, battery,
storage, and RAM gauges, while the existing Link, Live Console, Vitalis, Lifeline, App Launchpad,
Device DNA, Ascension Protocol, Members, Galaxy, Settings, About, Pulse, Nexus telemetry, and
Guardian behavior remain routed inside the same shell. Device DNA and Ascension now have distinct
drawer icons and direct routes; an unlinked Ascension page explicitly says it is awaiting Desktop
Link and never claims synchronization. A Kotlin navigation contract prevents duplicate Home paths
or dropped functional destinations.

Companion Settings includes an optional local **Privacy Curtain**. It covers device, project, and
session content whenever Companion opens or returns from the background and applies Android secure
window protection against screenshots and screen recording. A deliberate foreground-session reveal
uncovers the interface without lowering capture protection. It does not disconnect ROMVERSE Link,
alter Guardian, or grant device-changing authority.

The same Settings surface now provides a genuine **OLED mode**. Its centralized display policy uses
true black for primary content, sections, cards, drawer, bars, and inactive navigation while keeping
the approved ROMVERSE accents and stars. Android recreates the Activity after a change and restores
the exact route, so the switch applies immediately without losing the user's place. It has no effect
on evidence or operational authority.

Companion's public identity surface is evidence-backed and beginner-readable. The Home greeting is
local/member personalization rather than a hardcoded developer name. Exact marketing identities are
generated from verified Desktop Device Packs with build contracts; Companion shows the matching Pack
and truncated evidence hash alongside the Android-reported model/codename, while every unmatched or
ambiguous identity remains explicitly unconfirmed. These identity records have no execution authority
and can never justify flashing or bootloader relocking.

An authenticated Link v6 session can also show the selected Desktop project's privacy-bounded
**Device DNA Capability Map** on Companion Home and in a dedicated detail panel. Companion receives
only the scrubbed project label, a 16-character profile reference, warning count, and at most twelve
bounded capability decisions; source paths, full hashes, commands, approvals, and device-changing
authority are excluded. `UNCONFIRMED` evidence remains visible, the permanent no-relock rule is not
misreported as a project fault, and the mobile parser fails closed on malformed or authority-bearing
profiles.

Companion **Lifeline** can now start a private guided session from a real local diagnostic,
derive bounded beginner checkpoints from the actual findings, and compare a later fresh scan
against the saved score and finding set. It reports improved, unchanged, unconfirmed, or needs
more attention and explicitly states that evidence comparison is not certification of a repair.
Its Live Console shows genuine baseline, checkpoint, and comparison progress with what/why/next
guidance; it never changes Android settings or other apps as part of this workflow.
New Lifeline sessions use strict content-digested schema three. Each status is cross-bound to its
checkpoint and comparison evidence, the comparison summary is re-derived from the saved before/after
facts, future timestamps and extra fields fail closed, and a fresh comparison cannot start until all
guided checkpoints are genuinely reviewed. Valid schema-two sessions are verified and migrated;
genuine complete comparisons remain complete, while an older premature completion is backed up and
returned to checkpoint review without inventing progress. Schema-one sessions remain readable;
checkpoint or comparison corruption is preserved for diagnosis and rejected rather than shown as
trusted progress.

Companion's Vitalis assessment, Lifeline checkpoint, and evidence-comparison rules live in
Qt/Android-independent Kotlin domain modules. Missing core evidence remains unconfirmed instead
of becoming a false zero or healthy score, and new findings cannot be masked by a higher numeric
score. Vitalis also requires fresh battery-temperature and validated-network evidence before it
publishes a numeric score; known critical evidence remains prominent even when another measurement
is missing, and readings outside the two-minute freshness boundary are not scored. JVM tests cover
healthy, critical, missing, stale, far-future, improved, unchanged, needs-attention, and invalid
evidence states. The
Gradle `testDebugUnitTest` gate therefore executes real tests rather than a `NO-SOURCE` task.
Activity-history and offline Galaxy rules are isolated and JVM-tested as well, including
bounded persistence, deduplication, validation, search, and vote state. The desktop now treats
wireless ROMVERSE Link as an optional capability: a firewall or restricted account can deny
local sockets without preventing ROMVERSE from opening or disabling USB/read-only workflows.

Wireless ROMVERSE Link protocol v3 uses TLS 1.2 or newer with a persistent per-workspace ECDSA
identity. Companion accepts only HTTPS local/private, link-local, or loopback endpoints and pins
the desktop's exact SHA-256 certificate fingerprint. Discovery supplies the endpoint and identity,
but the user must compare the same human-readable safety code on PC and phone before Desktop can
approve the request. A correct short-lived code creates an opaque request identity; explicit
desktop approval issues a separate 30-day bearer token, telemetry requires that token, reset or
expiry revokes it, and failed codes are throttled per client. The Desktop stores only its SHA-256
verifier. Companion can adopt a changed DHCP address automatically only after the advertisement
matches the saved certificate and the new endpoint proves the pinned TLS identity with that active
approval; bounded discovery continues across receive timeouts and reconnect failures. Legacy
protocol-v2 HTTP sessions are
discarded and must pair again. USB read-only behavior remains available if encrypted wireless Link
cannot start.
The Desktop's remembered-session verifier now uses a byte-bounded, exact-schema, content-digested,
private atomic record. It rejects extra fields, Boolean/number confusion, oversized files, linked
targets and redirected directories; an unsafe record is never authorized or followed outside the
Link identity root. Genuine schema-one digest-only records migrate to schema two after full expiry,
hash and lifetime validation. Reset and expiry remove only a contained regular record.

Live Console records genuine pairing-opened, pending-safety-check, and approved states. These events
explain what happened and what the user should do next, expose no certificate private key or bearer
token, and carry no command, approval, or device-changing authority to Companion.

ROMVERSE Link schema v6 adds **Raw Terminal** to Companion Live Console as a one-way technical
feed. It accepts only completed Guardian-approved Command Console probes for ADB version, model,
Android version, battery, storage, and Verified Boot. Desktop removes device identifiers, private
host paths, full hashes, credentials, control characters, and excessive output before publishing a
bounded content-digested record. Device enumeration, host platform/Python details, arbitrary
commands, approvals, and all execution authority remain excluded; Companion cannot send terminal
input back to Desktop. The same schema carries the read-only Device DNA Capability Map described
above, with explicit `execution_authority: none` and `bootloader_relock: never` constraints.

An approved Companion can also submit a bounded health-only snapshot back to Desktop. The
snapshot contains the visible device model/codename, Android and Companion versions, battery,
temperature, storage, memory, network/USB evidence, and the locally calculated Guardian health
score. Schema four binds that score, Vitalis state, and evidence percentage to the exact submitted
measurements; Desktop re-derives all three, rejects contradictory claims, and rejects observations
older than two minutes or implausibly far in the future. The receiver also limits request size,
validates every range and identity field, rejects serial/IMEI/account/file/package/command/approval
fields, and clears the snapshot when pairing is reset. This return channel
cannot execute commands or authorize device work. Companion renders the same live evidence as
orbital gauges and a bounded trend graph; absent measurements stay visibly unavailable. The
schema-three/four snapshot may additionally send one bounded root-Manager candidate derived locally
from a full official certificate-signature match. It does not send a package inventory, serial,
path, command, approval, or device-changing authority, and older schema-two snapshots remain
readable with the candidate explicitly unknown. The
Companion graph now persists battery, storage, RAM, score, and timestamp as one aligned atomic
timeline rather than three independent preference strings. Its 24-sample history is SHA-256
verified, suppresses duplicate page-open samples, migrates valid legacy graph data, preserves
failed evidence without overwriting it, and offers an explicit local-only reset when recovery is
needed.

Companion **safe cache cleanup** now mirrors Desktop's evidence-first optimizer boundary. It
previews only regular app-private cache files older than 24 hours, limits scan/file/byte scope,
preserves links, recent files, oversized files, and anything changed after preview, then asks for
explicit confirmation before background deletion. The exact cache root and candidate identities
are bound into the plan fingerprint. Every result writes an atomic privacy-safe receipt and verifies
it immediately; if receipt persistence fails after deletion, Companion reports that evidence failure
honestly with a failed-evidence terminal state rather than claiming a completed or fully verified
outcome. Receipt loading is byte-bounded and re-derives the evidence identifier and result-count
invariants even when a local record is correctly re-digested. Preview and verified-clean phases show a
real indeterminate progress bar, keep the trigger locked through the confirmation decision, and expose
terminal success, cancellation, or failure only after the corresponding operation actually returns.
ROMVERSE does not invent a percentage because Android's filesystem traversal does not provide one.

**Forge Arsenal managed downloads** are bounded and content-addressed. Official ZIP packages
download to partial files, enforce archive/expanded-size and entry-count limits, reject path
traversal and symbolic links, validate CRCs and required files, extract through an atomic
staging directory, require one unambiguous copy of every executable, and record executable
SHA-256 hashes. Receipts use exact bounded schemas and atomic private writes; managed package
directories and executable sets are bound to their approved identity and official source.
ROMVERSE rebuilds its managed `PATH` entries after every scan, so a tool that is changed after
activation is removed immediately rather than remaining available through a stale path. Redirected
or linked storage, linked binaries, altered receipts, unapproved file sets, and candidate floods
all fail closed. Newly installed POSIX directories/files use private `0700`/`0600` modes.
The setup dialog never estimates completion from a fixed stage list. When an approved server
provides a bounded content length, it reports coalesced downloaded-byte progress; pinned partition
tools report their real completed-file count. Release discovery, archive validation/extraction,
receipt activation, unknown-length transfers, and operating-system authorization remain visibly
indeterminate until they genuinely finish.

Payload Dumper uses a stricter release flow: ROMVERSE resolves the current host asset only from
the official `ssut/payload-dumper-go` GitHub API, requires GitHub's asset SHA-256, restricts the
download URL to the official release path, rejects unsafe TAR members and links, extracts only
the single bounded executable, and activates it atomically with a hash-bound version receipt.
When a prepared OTA already exposes `payload.bin` but Payload Dumper is missing, ROM Studio no
longer leaves Partition Atlas disabled. The control becomes **Resolve Partition tools**, opens a
one-tool Forge Arsenal plan, respects the verified-tool automation setting, rescans the complete
tool inventory, and enters Partition Atlas only after the executable is genuinely available.
Switching to another project also clears every Recipe and Partition action that the prior project
enabled, preventing stale working-tree state from crossing project boundaries.
Partition activation now reads the private sealed working-tree display index, so nested or
case-variant `PAYLOAD.BIN` sources use the same path without recursively walking a large tree on the
UI thread. After partition extraction, a missing ext4, EROFS, or sparse-image reader changes the
filesystem action into **Resolve filesystem tools**. ROMVERSE selects the format-scoped readers,
freshly verifies them, and resumes expansion only when the resulting plan is genuinely safe;
critical images, unsupported formats, and insufficient-space findings remain explicitly blocked.

Genesis Sequence now derives its install plan from the active Device Pack's exact tool profile.
It does not install unrelated optional Forge Arsenal tools. Safe
managed tools are downloaded and verified inside the workspace; allowlisted Ubuntu and Fedora
packages use the operating system's visible administrator prompt; requirements without an approved bounded
installer remain manual. After setup closes, ROMVERSE reactivates only receipt-verified tools,
rescans the complete profile, and refreshes the active Genesis stage. The Android logical
partition tools are pinned to the exact commit and SHA-256 values validated by the successful
Android 15 HyperOS reference build rather than silently tracking mutable binaries.

## Linux quick start

Ubuntu 24.04+, Fedora 44, and Python 3.11–3.14 are supported for development.

Ubuntu:

```bash
sudo apt update
sudo apt install python3-venv adb libegl1 libxkbcommon-x11-0
./scripts/bootstrap.sh
source .venv/bin/activate
romverse
```

Fedora:

```bash
sudo dnf install python3 android-tools mesa-libEGL libxkbcommon-x11
./scripts/bootstrap.sh
source .venv/bin/activate
romverse
```

To connect a phone, enable Android **Developer options → USB debugging**, connect by USB,
accept the fingerprint prompt on the phone, then open **Device Portal** and select **Scan now**. On Linux, a missing
USB permission may require the distribution's Android udev rules package or an OEM rule;
restart ADB after changing rules.

```bash
adb kill-server
adb start-server
adb devices -l
```

## Windows quick start

Install Python 3.11+ and the Android SDK Platform Tools, ensuring `adb.exe` is on `PATH`.
In PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\.venv\Scripts\Activate.ps1
romverse
```

An OEM USB driver may also be required on Windows. ROMVERSE verifies tools but does not
silently install system packages or drivers.

## Desktop release candidates

The release pipeline builds self-contained one-folder ROMVERSE applications for Linux x86-64 and
Windows x86-64, launches each frozen executable against a disposable workspace, packages each app
directory as a verified ZIP, and combines both exact archives in one unsigned release manifest.
The extracted application does not require a separate Python installation. CI output remains an
unsigned candidate until the external-key ceremony in
[docs/DESKTOP_RELEASE.md](docs/DESKTOP_RELEASE.md) succeeds.

For a local Linux candidate:

```bash
python -m pip install -e '.[release]'
python scripts/build_desktop_executable.py \
  --output-directory build/frozen \
  --work-directory build/pyinstaller
python scripts/smoke_frozen_desktop.py \
  build/frozen/ROMVERSE/ROMVERSE /tmp/romverse-frozen-smoke
python scripts/package_desktop_bundle.py \
  build/frozen/ROMVERSE \
  --platform linux-x86_64 \
  --output dist/ROMVERSE-Desktop-0.1.0-linux-x86_64.zip
```

## Development

```bash
source .venv/bin/activate
pytest
ruff check .
python -m romverse --skip-onboarding
```

The default data root follows each OS convention:

- Linux: `~/.local/share/ROMVERSE`
- Windows: `%LOCALAPPDATA%\ROMVERSE`

Override it for development with `ROMVERSE_HOME=/some/path` or `--workspace /some/path`.
See [docs/MASTER_SPECIFICATION.md](docs/MASTER_SPECIFICATION.md) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Public builds must also satisfy the explicit
[release-readiness gates](docs/RELEASE_READINESS.md) and the fail-closed
[Desktop release process](docs/DESKTOP_RELEASE.md). CI candidates are deliberately unsigned;
production Ed25519 keys remain outside the repository and application workspace.
