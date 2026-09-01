# ROMVERSE Approved Commitments

This is the repository-side ledger for decisions explicitly approved in **ROMVERSE Plans and
Ideas**. A requirement appearing here does not prove that it is implemented or verified.

## Status and supersession rules

- `CONFIRMED` is a product decision, not implementation evidence.
- `IMPLEMENTED` requires repository evidence.
- `VERIFIED` requires relevant automated and/or runtime evidence.
- Unknown or conflicting evidence remains explicitly unconfirmed.
- Later explicit decisions supersede conflicting earlier decisions.
- ROMVERSE is online-first/online-required. Earlier Strict Offline Mode requirements are retired.
- Launch is A$14.99 AUD monthly with a seven-day trial. Earlier tier, paid add-on, advertising,
  and annual-launch-plan ideas are retired.

## Product and Guardian invariants

- Make ROM work understandable to beginners without hiding technical truth from experts.
- Preserve projects, protected sources, recipes, builds, backups, and user data by default.
- Never simulate progress, completion, diagnosis, verification, or device state.
- Apply an automatic fix only when its prerequisites, scope, safety, and outcome are verifiable.
- Require informed consent for destructive operations.
- Never authorize bootloader relocking.
- Rooting, flashing, unlocking, wiping, and partition writes remain Guardian-controlled.
- Performance is measured throughout development rather than treated as release-only polish.

## Approved workflows

- ROM Studio
- Genesis Sequence
- Recipe Forger
- Ascension Protocol: optional Magisk/KernelSU root route within Genesis Sequence
- Guardian Readiness and Guardian Flash
- Local-drive backup before flashing
- Preserve Data/Dirty Flash and Wipe Data/Clean Flash choices with clear consequences
- Functional Safe/Caution/Protected debloat classification
- Real progress, evidence cards, explanations, and safe automatic resolution
- Remembered ROMVERSE Link with certificate-bound automatic reconnect and explicit revocation

## M1 pipeline

Firmware Import
→ Automatic Detection
→ Device Identification
→ Device DNA
→ Capability Map
→ Tool Resolution
→ Workspace Creation

### Device DNA

Create one authoritative evidence-backed device/firmware profile for ROM Studio, Genesis,
Recipe Forger, Ascension Protocol, Guardian, and later Companion. V1 covers identity and retail
name, SoC/platform, Android/ROM/build/region/security data, package format, partition and A/B
architecture, filesystems, bootloader/slot/root/encryption/Verified Boot evidence, partition sizes,
fastboot/recovery capabilities, compatibility warnings, sources, and confidence.

The beginner Capability Map uses exactly `SUPPORTED`, `CAUTION`, `UNSUPPORTED`, and
`UNCONFIRMED`. Device DNA never manufactures certainty and never authorizes relocking.
The persisted profile uses bounded private atomic schema-two storage, strict nested shapes and
cross-references, exact protected-source binding, and a digest over the normalized profile. Valid
schema-one evidence remains readable and refreshes forward. Structure-backed facts consume only the
current persisted schema-two inspection report, and bootloader relocking remains UNSUPPORTED even
if a modified local document is re-digested.
Package detection is structure-backed rather than extension-backed: inspected payload, super, and
partition-image signals select or constrain the matching local source adapter. A readable archive
without Android structure remains unconfirmed, while critical containment findings are unsupported.
One unambiguous live device may add only read-only OEM knowledge to an unassociated project; multiple
devices never trigger a guessed association. A connected device/firmware codename conflict stays
visible and unsupported, and no knowledge Pack grants build or flash authority.
Tool resolution consumes the same structural evidence: payload, super, and partition-bundle inputs
select bounded source-scoped Forge Arsenal requirements, while an exact source contract supplies its
reviewed tool list. Selection and host availability remain separate evidence, and neither grants
build or flash authority.

### Compatibility Matrix

- Consume Device DNA and distinguish Verified, Strong Match, Limited Evidence, Unknown, and
  Known Incompatible.
- Persist a bounded private strict schema-two Matrix and re-derive every saved decision from the
  exact current Device DNA binding on load; a re-digested local edit cannot change the result.
- Expose evidence, confidence, freshness, and scope.
- Do not confuse technically possible with proven compatible.
- Community telemetry is opt-in and privacy-preserving; reports are not automatically trusted.
- Inform Guardian without bypassing Guardian.

## Intelligence architecture

### ROMVERSE Nexus

Nexus is the central orchestrator and retires the temporary Mission Control name:

Nexus Mission
→ Understand
→ Research
→ Nexus Plan
→ Guardian Review
→ Execute
→ Nexus Adaptation when evidence requires it
→ Nexus Verification

Approved terms are Nexus Mission, Nexus Plan, Nexus Adaptation, Nexus Verification, and Nexus
History. Nexus coordinates other systems rather than duplicating them.
Persisted Nexus Plans use bounded private strict schema-two storage and are fully re-derived from
current Device DNA and Compatibility Matrix evidence on every load. ROM DNA independently re-derives
its project/Pack/source/tree/Recipe provenance. Re-digested edits, stale bindings and schema tricks
cannot grant execution or bootloader relocking; valid schema-one evidence upgrades only at a genuine
replanning or verified-save boundary.

### Pathfinder, Foresight, and Insight

- **Pathfinder** determines the best evidence-backed route and powers a visual Route Map with
  current position, upcoming stages, branches, failures, and adaptations.
- **Foresight** predicts change impact and dependencies in a Predict → Execute → Verify → Learn
  loop. Guardian remains the safety authority.
- **Insight** provides lightweight Why explanations, source/confidence views, a Nexus Decision
  Timeline, and privacy-scrubbed exports. It reuses recorded evidence instead of rerunning analysis.

### Online intelligence

Use current online evidence for diagnosis, planning, compatibility, research, tool resolution,
safe fixing, and verification. Show source, freshness, corroboration, scope, and confidence.
Connectivity grants no destructive authority and losing it never lowers Guardian policy.

## Synapse and AI

### ROMVERSE Synapse

Synapse is the server-side verified-solution network. Approved terms are Synapse Query, Synapse
Match, Synapse Contribution, Synapse Confidence, and Synapse Network. Knowledge progresses from
Candidate → Verified Success → Strong/Corroborated → Trusted. Failures and version drift can
downgrade or retire knowledge. Contributions must be privacy-scrubbed.

### AI Usage Governor and AI Gateway

- Prefer deterministic processing, Synapse, cached knowledge, and Compatibility Matrix rules.
- Use AI for genuinely new reasoning or research.
- Support budgets, concurrency, rate limits, abuse controls, and fair-use throttling.
- Cost control never overrides safety: investigate uncertainty or stop with an explanation.
- The AI Gateway is provider-independent. OpenAI is the preferred initial provider, with future
  Claude, Gemini, Mistral, or other routing and optional independent corroboration.
- Members do not provide separate provider accounts or API keys.
- AI output still requires evidence validation and Guardian review.
- Desktop does not expose editable AI budgets until a production provider/usage service consumes
  them. Stored legacy values remain compatibility data, not evidence that a public AI service runs.

## Companion architecture

Companion is a first-class half of ROMVERSE, organized around:

Home → Device → Nexus → Guardian → Tools → Community/Account

Use touch-appropriate cosmic glass design, progressive disclosure, accessible controls, crisp
icons, and reduced effects on slower hardware.

### About ROMVERSE and The Origin

Desktop and Companion About pages are the canonical public brand/story surface: ROMVERSE hero and
real build channel, concise vision, ROMVERSE Promise, SteveTheRad as Founding Creator, RadForge Labs,
ecosystem, genuine service status, membership boundary, credits, trust, legal/open-source notices,
changelog direction, the official `https://romverse.app/` and `https://radforgelabs.com/` website
destinations, official Facebook and Reddit destinations, community gratitude, and the quiet
`27.08.2026` founding signature. The website destinations appear in their own balanced glass
section with crisp, accessible actions. Facebook uses `ROMVERSEOfficial`; Reddit uses the clean
canonical `https://www.reddit.com/user/ROMVERSE/` address without tracking parameters.
Desktop uses the byte-exact production `romverse-icon.png` from `romverse.app` for its window and
top-left sidebar identity, and the byte-exact production `romverse-logo.png` for the About hero.
Their Qt presentation is native to the cosmic glass shell and mirrors the website's restrained
crest float, rotating cyan orbit, scan sweep, hover shimmer, and reduced-motion contract rather
than displaying an unstyled pasted image.

Desktop additionally presents the approved ROMVERSE product and RadForge Labs company identities
together in one responsive hero. Its build/safety facts are explicit, and its ROMVERSE, Guardian,
Companion, and Galaxy family cards route to the canonical Desktop pages. Official external actions
surface browser failure without claiming a device or application state change. These About actions
remain navigation-only and never inherit Guardian or execution authority.

Double-clicking the R on Desktop or double-tapping it on Companion discovers **ROMVERSE: The
Origin**. Discovery is remembered locally and enables replay. The first genuine discovery records
**Beyond the Verse** locally, but no XP, account entitlement, or server award may be simulated before
the production Progression service exists. The scene-led experience covers The Beginning, Vision,
Promise, SteveTheRad's message, Community, Future, and Finale. It has immediate exit, previous/next,
pause, skip-to-finale, runtime Reduced Effects, readable automatic pacing, progress, and an optional
locally packaged ambient sound identity that is off by default. Companion uses a purpose-built
vertical/OLED composition with restrained haptic transitions rather than cropping Desktop. The story
describes why ROMVERSE exists without exposing proprietary internals, and personal recognition stays
absent until genuine account evidence exists. Desktop persists discovery as one private, bounded,
atomic exact-schema record; symbolic links, non-regular files, oversize content, malformed values,
and additional authority-like fields are rejected.

The approved Galaxy shell is now represented in the Android runtime by a real edge-swipe drawer,
persistent glass top and bottom navigation, a single bottom-left Home route, and a live read-only
gauge deck. Link, Live Console, Vitalis, Lifeline, App Launchpad, Members, Galaxy, Settings, and
About remain real destinations inside the shared shell. JVM structure tests, a forced offline APK
rebuild, and Android lint protect this navigation contract; visual/on-device acceptance remains a
separate gate for each iterative panel polish pass.

Companion personalization and device identity are now public-safe: no hardcoded developer greeting,
a bounded local display name with temporary server-verified Members precedence, and exact identity-only
records generated from Desktop Packs that contain a build contract. The Xiaomi 17 Pro Max record shows
its raw model/codename and Pack hash evidence; unknown or ambiguous devices remain unconfirmed. Identity
display carries no execution authority and never supports a bootloader-relock decision. Companion
Settings exposes only enforced mobile policies; public HTTPS can be disabled without disabling local
Link, and unrelated preference saves do not silently discard a valid Members session.
Authenticated Link v6 now renders the selected Desktop project's bounded Device DNA Capability Map
on Companion Home and in a dedicated detail panel. The mobile contract accepts only a scrubbed project
label, truncated profile reference, warning count, and up to twelve capability decisions; it rejects
malformed evidence, any execution authority, and any bootloader-relock policy other than `never`.
Vitalis safe-cache preview and cleanup expose genuine indeterminate progress while their bounded
filesystem operations run, prevent duplicate activation through the approval decision, and report
terminal state only from returned evidence rather than an invented percentage.

- **Connected identity:** show a verified retail name and trusted cached exact-device image; use
  a generic silhouette rather than a wrong image.
- **Pulse:** collect useful technical telemetry, timelines, baselines, post-change verification,
  and ROM impact comparisons without unnecessary access to personal content.
- **ROMVERSE Link:** migrate the existing Companion connection stack in place. Verify pairing,
  persisted trust, reconnect, revocation, checksums, interruption recovery, and PC/Android behavior
  before retiring old labels or compatibility paths. Local Link comes first.
- **Vitalis:** absorb overlapping Companion health/diagnostics behavior after migration.
- **Lifeline:** absorb Guided Recovery into a beginner recovery/rescue experience, prepare the PC
  rescue route, and state honestly when Android cannot run and the PC must take over.
- **Live Console:** show genuine Nexus mission progress, Pathfinder/Foresight/Guardian state,
  route events, warnings, counters, gauges, technical output, and Raw Terminal data received through
  ROMVERSE Link. Decorative or invented operation state is prohibited.

## Conflict-safe product naming

- `Device Nexus` → **Device Portal**, reserving Nexus for central orchestration.
- `Companion Link` → **ROMVERSE Link**, retaining compatibility aliases during migration.
- Companion health/Quantum diagnostics → **Vitalis** after behavior is mapped.
- Companion Guided Recovery → **Lifeline** after behavior is mapped.
- Existing health telemetry internals become the **Pulse** data layer without needless rewrites.
- **Ascension Protocol**, Device Atlas, Guardian, Genesis Sequence, and Recipe Forger remain.

## Membership and infrastructure

- A$14.99 AUD monthly; seven-day full-access trial; month-to-month; cancel anytime.
- PC, Companion, Nexus/online intelligence, Guardian, community, updates, and normal current/future
  features included.
- No launch annual plan, tiers, paid add-ons, advertising, or sponsored placements.
- One initial VPS may host the site, forum, accounts, subscriptions, API, and Synapse as separate
  services/containers.
- Use object storage/CDN for installers, APKs, updates, and large assets.
- Maintain automated off-server backups in another failure domain.
- Treat 4–8 vCPU, 8–16 GB RAM, and NVMe as a planning estimate; size from measured workloads.

## ROMVERSE Excellence Programme — confirmed 2026-08-30

This programme improves the approved systems before adding more headline subsystems. It is a
roadmap commitment, not an implementation claim. Delivery stays incremental and compatibility-safe:

Design System/performance foundations → ROM Studio/Genesis workflow →
Nexus/Guardian/Device DNA/Pathfinder/Foresight → Twin/SimBoot/Continuum →
Companion health/UX → account/progression/community → production backend.

### Guided and Expert experiences

- **Guided Mode · ROMVERSE Arcana:** plain-language goals, one obvious next action, contextual
  guidance, progressive disclosure, automatic routine work, and technical evidence on request.
- **Expert Mode · Architect workspace:** specialist navigation, technical evidence by default,
  developer workspaces, deep inspection, and advanced Nexus/ROM tooling.
- Both modes consume the same authoritative projects and evidence. Switching must not discard the
  active project or weaken Guardian. Approval rules and the bootloader-relock prohibition are
  identical in both modes.
- Complicated screens follow **Essential → Details → Engineering**. Public copy uses restrained
  plain language; subsystem names appear when they help rather than to advertise complexity.

### Shared Design System and Desktop excellence

- Formalize typography, spacing/grid, strategic glass depth, surfaces, iconography, semantic
  status symbols plus text, motion/easing, micro-interactions, graphs, dialogs, tooltips, empty
  states, responsive breakpoints, accessibility, Guided/Expert density, and Prestige theme tokens.
- Target premium craftsmanship without visual overload: fast acknowledgement, interruptible short
  transitions, responsive 4K/ultrawide layouts, scalable effects presets, and no effect that makes
  engineering work noticeably slower.
- Evolve Desktop toward a contextual Command Center, collapsible navigation, Focus/Zen workspace,
  adaptive multi-pane Project Explorer/Workspace/Inspector, dockable Live Console, breadcrumbs,
  useful peeks/pins, a Ctrl+K command palette, Activity Center, and one clear primary action per
  screen. Drag-and-drop recognition and technical visualizations must remain evidence-backed.
- Keep one permanent, professionally grouped Desktop sidebar and one canonical page for each major
  feature. The Command Deck provides contextual shortcuts rather than duplicate implementations and
  reflects genuine connected-device and active-ROM-workspace state. Its approved mission cards cover
  Build ROM, Pre-Build Simulation, Device DNA, Recipes, Health, Repair, Guardian, Rescue/Backup,
  Timeline, Live Operations, Wireless Transfer, and ROMVERSE Lab; cards remain navigable when a
  prerequisite is absent so the destination can explain the next safe step.
- Replace duplicate upper health gauges with a Genesis Flight Plan backed by the exact guided
  mission assessment. It must display the real resume stage and progress, root choice, recovery and
  Guardian readiness, explain current blockers, and route directly into Genesis. Device-health
  gauges remain in the lower telemetry bay as the single canonical health surface.
- Use one consistent status language: Verified, Ready, Working, Attention, Blocked, and
  Unconfirmed. Color reinforces the label and never carries meaning alone.

### Reliability, recovery, performance, onboarding, and trust

- **Project & Session Excellence:** transactional autosave, crash-safe resume, recent sessions,
  meaningful Continuum checkpoints, safe cancellation, project thumbnails, and exact Expert
  workspace restoration where supported.
- **Error & Recovery UX Excellence:** failures become managed workflow states that explain what
  failed, what remains safe, what evidence exists, and which verified alternatives are available.
  ROMVERSE stops rather than guessing when no reliable fix exists.
- **Performance Excellence:** measured budgets, safe caching, incremental recomputation, background
  workers, lazy loading, virtualized large data sets, and sensible prefetching. Never make a user
  wait twice for reusable verified work.
- **First-Run Excellence:** Install → Account/Trial → Guided or Expert → Connect Device →
  USB/ADB help → Device DNA → Arcana → first useful result. Any demonstration environment is
  conspicuously labelled and never presented as real device evidence.
- **Trust, Privacy & Update Excellence:** clearly show local versus online processing, sanitized
  contribution previews, trusted Link relationships, account sessions, tool integrity, diagnostic
  controls, signed/integrity-verified updates, preserved projects, release notes, and safe update
  recovery/rollback boundaries.

### Companion Experience Excellence

Companion follows: **Glanceable first. Detailed when needed. Powerful without feeling crowded.**
Within three seconds of opening it, the user should understand device health, Link state, active
mission state, and whether attention is required.

- One contextual Home hero: normal ROM Health, a live Nexus mission, Vitalis attention, or Lifeline
  recovery—whichever genuinely matters now. Keep a strict one-purpose/one-primary-action screen
  complexity budget.
- Develop an evidence-backed segmented ROM Health Orb, a persistent collapsible Nexus mission strip,
  graceful Link loss/restoration, navigation memory, Device Hero-to-Device-DNA continuity,
  interactive Pulse/Continuum scrubbing, and Arcana explanations/bottom sheets.
- Keep the left-edge drawer finger-tracked with vertical-scroll discrimination and button fallback;
  use mobile dark-crystal glass, OLED mode, optional reachability, touch illumination, restrained
  haptics, refresh-rate-aware motion, and accessibility preview without forcing high refresh rate.
- Add optional Privacy Curtain, meaningful grouped notifications, restrained Guardian transitions,
  privacy-respecting Member identity cards, and quiet progression/award presentation.
- Companion must remain lightweight; polish and monitoring must not create material heat, battery,
  or background-resource cost.

### Membership, recognition, and pricing promise

- Progression supports uncapped levels, named/legacy/contribution/loyalty Awards, optional public
  presence, a featured Award, developer recognition, and restrained Prestige theme unlocks every
  50 levels through Level 300. Engineering screens remain free from intrusive gamification.
- After twelve consecutive paid months, the planned loyalty recognition includes One Year in the
  Verse, Unbroken Orbit, Stellar Anniversary presentation, profile recognition, XP, an anniversary
  collectible, a 50% next-renewal discount, and a personal gratitude message, subject to production
  billing implementation and published terms.
- Pricing changes are never casual: give clear advance notice, honest reasoning, old/new pricing,
  and the effective date. Prefer preserving the A$14.99 continuous-member founding rate while it
  remains economically sustainable; if that cannot continue, provide advance notice and practical
  preferential treatment. No ads, surprise charges, or paid feature tiers.

None of these items becomes **Implemented and Verified** merely because it appears in this section.

## Verification order

1. Device DNA and Capability Map
2. Compatibility Matrix evidence model
3. Nexus, Pathfinder, Foresight, and Insight deterministic interfaces
4. ROM Studio, Genesis, and Ascension integration
5. Companion migration map, Pulse, and local ROMVERSE Link
6. Vitalis, Lifeline, and genuine Live Console data
7. Synapse, AI Gateway, Usage Governor, accounts, and membership backend
8. Security, accessibility, recovery, production infrastructure, and release hardening

Nothing becomes Implemented and Verified merely because it is listed here.

## Repository evidence status — 2026-08-30

- **IMPLEMENTED AND VERIFIED:** Device DNA and Capability Map client model/private bounded strict
  schema-two persistence, legacy refresh, persisted-inspection binding, relock invariant/Desktop UI,
  plus deterministic Device-DNA-bound schema-two Compatibility Matrix persistence and legacy
  reassessment, and privacy-bounded read-only Companion Link v6 Capability Map parsing and UI;
  integrity-indexed shared Desktop/Companion Device Atlas coverage for Generic Android,
  Xiaomi/HyperOS, Samsung/One UI, Google Pixel, OnePlus/OxygenOS, OPPO/ColorOS, realme UI,
  Nothing OS, Motorola/Lenovo, Sony Xperia, vivo/iQOO, ASUS/ROG Phone, HUAWEI, HONOR, HMD/Nokia,
  TECNO/Infinix/itel, ZTE/nubia/REDMAGIC, and Fairphone, with current official-source metadata and
  no build, root, unlock, recovery, or flash authority from an OEM manufacturer match; one-click
  Device Atlas exact-model review drafts that exclude serial/private data, inherit only the matched
  Pack's reviewed HTTPS source starting points, mark proposed identity limited, use bounded no-link
  input and private atomic output, and remain registry-rejected until separately reviewed/published;
  Genesis Device DNA stage with a progress-visible fresh read-only scan, current profile/map gate,
  beginner identity and key capability evidence, automatic profile refresh, and fail-closed removal
  of stale ROM Studio device identity after an ADB refresh failure;
  Recovery Bay category selection that round-trips every concern reliably plus Recovery Autopilot's
  exact Guardian-approved host ADB daemon recovery, binary revalidation, restoration attempt,
  read-only verification, indeterminate progress, automatic rescan, Live Console lifecycle, and
  privacy-safe tamper-evident receipts, with no `adb -s` surface or phone-changing authority;
  Recovery Bay automatic source-attributed remediation research for real error evidence, optional
  exact symptom input, privacy-scrubbed fingerprints, settings-change rejection, explicit
  authority/freshness/scope/corroboration/confidence UI, and verified-outcome promotion only from a
  matching successful built-in typed receipt while remote text remains guidance-only, plus
  byte/count-bounded strict-schema private atomic receipt/outcome persistence, workspace-anchored
  symlink/non-regular-file rejection, content-addressed local outcome filenames, provider action-ID
  rejection, and a locally validated-outcome requirement that prevents providers from self-asserting
  `confirmed working`; schema-two outcomes additionally bind the exact persisted error-fingerprint
  candidate to a format-specific ADB-host, exact-toolchain, OTA-source, or AVB receipt, revalidate
  that evidence on load, and deny promotion to legacy digest-only outcomes;
  Desktop ROMVERSE Archives expanded into a validated 110-guide, ten-category local catalog with 60
  structured known-fix records, 34 official-source-linked records, bounded ranked retrieval, weak-
  match rejection, category filtering, source visibility, and canonical workspace handoffs;
  a deterministic Archives Advisor now maps every Recovery Bay concern and typed actionable
  diagnostic finding to stable structured article identities, distinguishes exact ADB states,
  prioritizes full error-code matches, exports its source/reason/automation boundary, and opens the
  exact guide without starting research, approval, repair, build, or device work, while existing ROM
  Studio/Genesis/Ascension/Recipe handoffs preserve their stages and drafts; Recovery Bay keeps
  disabled online research in an accessible compact drawer, automatically expands real evidence,
  and keeps the exact local Advisor action visible without changing workflow state;
  Quantum Optimizer's exact actionable finding identity now selects the deterministic matching
  Recovery Bay concern only when the finding remains present in Recovery Bay's current report,
  displays a source-context/no-action-started boundary, clears that context on manual category
  change, returns to and visually focuses the unchanged exact Quantum Optimizer source finding, and
  fails closed in both directions on stale or unknown evidence without starting a session or worker;
  Command Deck consumes that same severity-ranked actionable selector, visually promotes Repair
  Phone with a topic-specific ready state, opens the exact matching plan, labels a healthy general
  intake honestly, and exposes mismatched Recovery evidence as refresh-required rather than guessing;
  guided repair sessions now use a strict private schema-two integrity envelope, bind the primary
  evidence-matched Archives article, re-derive comparison direction and finding deltas, reject
  hostile/altered/re-digested evidence, and feed only integrity-verified fresh comparisons into an
  exact-article local Resolution Memory that is explicitly correlation-only and grants no authority;
  shared read-only root-identity review that separates an observed root signal from an
  evidence-labelled Manager candidate, keeps a normal ADB shell explicitly insufficient to prove an
  unrooted phone, uses a full official signer pin for the Companion candidate while basic Desktop
  detection remains labelled package-presence evidence, preserves CAUTION/UNCONFIRMED Device DNA
  certainty, and carries only the bounded candidate through backward-compatible Companion health
  schemas three and four with no package inventory or execution authority;
  Compatibility Matrix evidence model; deterministic Nexus/Pathfinder/Foresight/Insight planning
  with strict private schema-two plan persistence, complete route re-derivation, legacy replanning,
  and self-verifying schema-two ROM DNA provenance;
  Desktop and Companion Link v6 Live Console telemetry, including bounded privacy-filtered Raw
  Terminal records from Guardian-approved read-only probes; local Synapse evidence promotion,
  downgrade, retirement, and privacy boundary; provider-independent AI Gateway contract; in-process
  AI Usage Governor; passwordless HTTPS Members client and server-issued entitlement parsing;
  Ascension exact-source/Device-DNA binding, a tamper-evident automatic route record consumed by
  Desktop and Companion and invalidated when its source, Device DNA, phone, or kernel context
  changes, with no command authority and permanent bootloader-relock prohibition; Genesis now
  resolves that route in a managed background preflight before optional-root consent and presents
  beginner-readable SUPPORTED/CAUTION/BLOCKED/UNCONFIRMED guidance, exact Magisk or KernelSU LKM
  method only when evidenced, source-image target, confidence, automation/user boundaries, and the
  invariant `phone changed: no / execution authority: none / bootloader relock: never`; the route
  record and exact-kernel KernelSU support observation use bounded private atomic evidence with
  strict field types, hostile linked/redirected/oversized record rejection, and complete current
  source/Device DNA/phone/kernel/official-Manager revalidation;
  responsive large-tree ROM Studio refresh through constant-time contained-tree presence checks and
  a private digest-checked extraction display index generated on the background worker; the index is
  explicitly non-authoritative, legacy projects never need a UI-thread migration scan, and every
  build plan still refreshes the complete real tree inventory before deriving inputs or hashes;
  bounded automatic ROM Studio workspace recovery before every project operation, with shallow
  enumeration of recognized import, working-copy, extraction, payload, filesystem, Time Machine,
  Recipe, Forge, and build-verification transaction artifacts; interrupted files, directories, and
  links are handled on the background worker without recursively scanning a completed ROM tree,
  overfull or linked roots fail contained, protected originals and outside targets remain unchanged,
  and the UI reports the recovery with `phone changed: no / execution authority: none / relock:
  never` before continuing the real operation;
  Ascension current-stage learning handoff into one authoritative bounded nine-stage Archives guide,
  with safe-operation completion required before navigation and no readiness or execution authority;
  one canonical Ascension checkpoint model shared by the visible tracker, Next Safe Action, status
  copy, Archives handoff, and Live Console so stage numbering cannot drift; it recognizes a manually
  verified patched image as a valid phone-handoff bypass without manufacturing any later evidence;
  its overall progress bar and Live Console percentage count only checkpoints that currently reload
  from verified evidence, never the ordinal number of the page being viewed, so a blocked first
  stage remains `0%` and a pending final Guardian handoff cannot display `100%`;
  one shared deterministic Ascension prerequisite-resolution plan for Desktop and Companion that
  deduplicates dependency-equivalent gates, ranks safety stops before automation, auto-chains only
  an unambiguous contained payload scan/extraction, and explains the smallest remaining verified-tool
  or genuine user/device action; Desktop Ascension now also opens a scoped Forge Arsenal resolver
  for AAPT2/APK Signer before Manager trust and Python/Payload Dumper before that exact OTA scan,
  reverifies the complete host inventory, prepares source-inspected and space-budgeted fastboot,
  OTA, or directly named Android boot inputs in the isolated tree, and resumes only after the
  required evidence and services exist; unsafe archives and role-ambiguous renamed images fail closed;
  execution-free Companion readers for tamper-checked phone-handoff and Manager-open receipts so its
  shared nine-stage guidance advances only when the capsule, official release, and exact-device
  evidence still match, without constructing an ADB gateway or command;
  official Magisk/KernelSU signer pinning with strict private content-addressed manager-vault
  containment, bounded non-linked tag enumeration, exact schema-two receipt shapes, atomic `0600`
  evidence/APKs, `0700` directories, re-digested path/shape substitution rejection, future-release
  rejection, schema-one load compatibility without offline-freshness authority, exact declared-
  byte download progress that cannot round unfinished work to 100, and terminal completion only
  after APK/package/pinned-signer validation, vault permission enforcement, and receipt storage; plus
  responsive background KernelSU Manager install-plan hashing/container inspection with genuine
  measured progress, exact phone/release/path revalidation after the worker returns, and an honestly
  indeterminate ADB install phase rather than a fabricated percentage; every Manager-install,
  patch-capsule, phone-handoff, and patched-output-discovery completion is accepted only as its exact
  typed terminal record and must match the independently reloaded source/method/project/phone-bound
  persisted evidence; arbitrary worker values, changed receipts, or mismatched filename references
  fail closed and cannot advance Ascension; detailed local failure text remains on the Ascension card,
  while shared Live Console explanations exclude raw paths, serials, and provider diagnostics; the
  same measured-or-
  indeterminate contract now covers the complete Guardian-approved Ascension phone preparation and
  Manager-open path, so Manager install, pristine-image push, installed-APK pull, signer validation,
  and package launch expose no fixed milestone percentages and complete only from their real receipts;
  Ascension patched-output retrieval and manual import keep ADB pull and lineage preflight honestly
  indeterminate, then publish coalesced byte-derived progress for the protected local vault copy and
  independent SHA-256 reread before any verified patched-image receipt is created;
  Ascension patch-capsule preparation keeps source/rollback/Manager trust revalidation indeterminate,
  then measures actual pristine-target and official-Manager copy/rehash bytes while retaining
  content-addressed reuse and the existing no-phone-change authority boundary;
  Ascension local ROM integration keeps safety/evidence revalidation indeterminate, then measures
  the complete pristine hash, rollback copy/hash, patched copy/hash, and integrated-target hash byte
  passes before reaching 100 only after receipt commit; Build Seal remains honestly indeterminate
  while its artifact rehash and broader full-tree freeze lack one trustworthy bounded total;
  signature revalidation on every vault reuse, mandatory exact-vault binding for local patch-capsule
  creation, content-aware root-target resolution that collapses identical copies and blocks
  byte-distinct ambiguity, verifies boot-header/ramdisk structure, performs explained Magisk
  fallback, prohibits KernelSU recovery fallback, and content-resolves duplicate stock-recovery
  rollback sources, with semantic boot-fact and exact-vault revalidation on reuse; safe separation of locked-bootloader local preparation from the
  explicitly-unlocked Guardian write gate, revalidation at Guardian phone handoff, exact capsule/install-plan binding before ADB,
  method-bound patched-output discovery and service-level transfer-plan revalidation before an
  exact-path approved read-only phone copy, newest-first matching output recommendation, and
  evidence-based rejection of a standard local filename that identifies the other manager,
  connectivity-only official-tool cache fallback with a 30-day limit, tamper-evident freshness
  receipts, explicit amber UI, two visible-only bounded connection retries with Live Console
  diagnosis and lifecycle cancellation, and fail-closed upstream metadata/digest/signer rejection,
  plus redacted tamper-evident output-discovery receipts bound to the exact handoff and a fresh
  ten-minute selection window with persistent Live Console found/not-found diagnosis,
  AOSP boot-header v0-v4 immutable-lineage verification, exact unchanged-kernel enforcement for
  KernelSU LKM, confidence-graded Magisk/kernel-less evidence, transparent legacy receipt upgrade,
  and a dedicated Guardian manifest lineage check,
  genuine nine-stage Live Console lifecycle, privacy-bounded Link v6 manager provenance with
  allowlisted repository/method binding and no full hash/path/authority, Companion installed-package
  guidance that explicitly separates ROMVERSE's automatic work from the user's next safe action,
  plus full-certificate pin verification before a user-triggered open-only manager handoff,
  Desktop exact-device installed-Manager path resolution plus temporary installed-APK
  hash/package/signer revalidation before its separately approved allowlisted open-only handoff,
  with cleanup and a serial/path-free zero-authority receipt; the Desktop state resolver requires
  that receipt before output discovery and preserves the exact Manager-open retry after failure or
  cancellation, while newly blocking existing-root or live source/device evidence outranks every
  historical phone-handoff action, plus a separately approved bounded
  filename-only output watcher with real elapsed progress and close/disconnect/timeout cancellation,
  and
  short-lived exact-handoff Guardian consequence review with zero execution authority; the root
  plan, Guardian manifest, final handoff, and consequence review all use private bounded atomic
  evidence, exact field/type validation, hostile link/redirect/oversize rejection, and complete
  current-chain revalidation before any review state is restored;
  upstream rollback, patch-capsule, patched-image, reversible integration transaction/receipt,
  rollback-snapshot, and build-seal evidence now use the same private bounded exact-shape storage,
  current artifact rehashing, hostile link/redirect/oversize/type-confusion rejection, and automatic
  pristine local-input restoration when integration evidence cannot be committed;
  approved phone-preparation, installed-Manager-open, and filename-only output-discovery receipts
  use the same private bounded exact-shape store with private history, current capsule/official
  Manager/pseudonymous-phone/candidate-set rebinding, stale-discovery rejection, and permanently
  absent root/flash/unlock/wipe/relock or continuing execution authority;
  Nebula Debloat automatic OTA/fastboot/super filesystem materialization, nested partition-layout
  discovery, conservative Safe/Caution/Protected classification, reversible transactional removals,
  and a tamper-evident discovery report that explains APKs examined/recognized/excluded,
  contributing partitions, image-materialization attempts, and the zero-phone-change boundary even
  when no reviewable inventory can be produced, plus pre-scan source-shaped Forge Arsenal resolution
  for the exact payload/LP/sparse/ext4/EROFS/fakeroot readers so missing tools block honestly instead
  of producing a false empty list; its unknown-size discovery/materialization remains indeterminate,
  exact app-record cataloguing switches to monotonic measured progress, and the mixed full-tree
  revalidation/snapshot/removal transaction remains indeterminate until its strict receipt commits;
  the visible inventory must exactly equal the independently reloaded persisted scan, and terminal
  completion must exactly equal the pending plan plus independently reloaded persisted receipt;
  short-lived exact-plan Guardian approvals with SHA-256 chain validation and audit-only legacy
  compatibility; Guardian Core background verification of audit, approval, APK, and recovery
  evidence with duplicate-refresh locking, visibility-aware deferred refresh, rapid-navigation
  cancellation, and visible indeterminate progress, plus fail-closed audit
  file/entry/line bounds before parsing or appending so hostile history cannot block the UI thread,
  lossless verified capacity rollover with full archived-file and prior-tail binding, recursive
  archive-chain verification, same-process archive-tamper detection, and bounded migration of a
  valid legacy oversized ledger while every unverified oversized ledger still fails closed;
  Genesis local-drive shared-storage backup with Guardian-approved read-only pulls, verified ZIP
  manifest/sidecar integrity, explicit coverage limits, exact-phone-bound readiness evidence,
  indeterminate ADB transfer phases, exact cumulative source-file byte progress after inventory,
  no fixed 55/38 or 82/18 weighting, and terminal completion only after all required backup and
  project-evidence receipts are stored;
  private bounded strict schema-two Guardian flash-mode handoffs bound to stable current readiness
  facts, the protected source and exact phone, with no execution authority, permanent relock
  prohibition, hostile-file rejection and audit-only schema-one compatibility;
  a post-handoff Guardian Manifest Review bound to that exact current handoff, readiness digest,
  protected source, phone, data choice and Device Pack, with strict private persistence, explicit
  PASS/BLOCKED evidence rows, no inferred partition writes, no consent or execution control, and an
  honest `blocked-missing-exact-write-contract` result until a signed exact-build, physically
  recovery-tested Device Pack write contract exists;
  one readiness policy across Forge Control and Guardian Manifest Review: local source, phone, AVB,
  build and rollback preparation remains visible as completed evidence but cannot turn the Pack
  flash/physical cards green or create a new handoff without exact signed certification; the
  required-evidence action routes to Device Atlas rather than restarting Autopilot, and imported
  attestation envelopes use bounded atomic `0600` storage inside non-linked `0700` directories;
  fail-closed Device Pack build-contract schema two for signed partition-to-artifact intent, with
  bounded unique allowed-image mappings, explicit Fastboot/Fastbootd transport and target slots,
  mandatory verification, exact source/AVB/physical-attestation binding, explicit data-mode support,
  unlocked-bootloader requirements, destructive target rejection and permanent relock prohibition;
  Guardian continues to expose zero writes, commands and execution authority until every declared
  artifact is separately bound to the current immutable build receipt;
  Guardian background artifact binding with real byte progress, exact local-build/offline-signing
  receipt selection, full current SHA-256 verification, strict private persistence, exact handoff/
  phone/data-mode/source/Pack/contract provenance, same-size/same-mtime tamper detection, signed
  composite-image rejection when unprovable, and hash-bound review rows that still grant no command,
  final-consent, execution or phone-changing authority; Guardian Review begins indeterminately,
  relays only genuine binding percentages below completion, emits no synthetic 90/94 manifest
  milestones, and reaches 100 only after the full command-free review is compiled;
  Forge Control stale-card detachment and natural-height scrolling, two aligned footer action rows,
  and separate blocked/attention counts so repeated evidence refreshes cannot jumble controls or
  make an amber certification requirement appear complete;
  local ROMVERSE Link protocol v3 with per-workspace ECDSA identity, TLS 1.2+, exact Android
  certificate pinning, two-screen safety-code confirmation, cleartext rejection, legacy-session
  migration, a 30-day explicitly approved remembered session that persists only a mode-0600 token
  digest on Desktop through a bounded private atomic strict schema-two record with validated
  schema-one migration and hostile link/redirect/oversize/extra-field/type-confusion rejection,
  automatic foreground/network reconnect with bounded backoff, certificate-bound
  DHCP rediscovery, explicit Reset Pairing revocation, and genuine Link state in Live Console with
  zero execution authority;
  Genesis genuine 15-stage Live Console/Companion lifecycle with evidence-derived progress, plus
  a stage-preserving Learn this stage route into bounded, context-selected verified Archives
  guidance that cannot advance readiness or weaken Guardian; one private atomic strict schema-five
  Genesis crash-resume record shared by ROM Studio project cards, bounded no-link schema-two through
  schema-four compatibility, hostile shape/type/digest rejection, explicit save-failure recovery,
  and removal of the obsolete seven-step progress file and duplicate guided wizard;
  Desktop settings schema-v4 Guided · Arcana and Expert · Architect experience persistence,
  specialist navigation/Command Console progressive disclosure that preserves the active route,
  keeps Live Console and Guardian visible, and never changes approval policy; accessible Desktop
  Ctrl+K navigation-only command palette populated from the canonical sidebar routes and shared
  feature vocabulary, with legacy-name search, stable relevance ranking, Guided/Expert disclosure,
  and no operation or device authority; one authoritative grouped navigation registry with live
  canonical breadcrumbs, Ctrl+B compact icon rail, and reversible Ctrl+Shift+F/Escape Focus
  workspace that preserves the exact active page, prior rail choice, workers, evidence, projects,
  and Guardian state while keeping visible search and connectivity context; canonical Desktop
  Activity Center with cross-feature search,
  outcome/category filters, truthful counts, evidence detail, redacted export, source-page handoffs,
  and private byte-bounded strict-schema atomic ledger storage while Health Timeline remains focused
  on diagnostic history; Companion persisted
  experience selection with Guided Device DNA overflow disclosure and Expert full-map presentation,
  runtime-verified across Android process restart; Guided Vitalis, Live Console Raw Terminal, and
  Ascension technical-evidence disclosure that never folds warnings, blockers, next safe actions, or
  Guardian boundaries, with Expert opening the same accepted evidence immediately and
  `bootloader_relock: never` unchanged; centered two-line Companion Home identity lockup; deterministic three-second Companion
  Home hero with Guardian > live mission > Vitalis attention > ROM Health priority, explicit
  Link/USB/mission certainty, and runtime-verified routing to Vitalis; optional Companion Privacy
  Curtain with content-area concealment on foreground return, persistent Android capture protection,
  foreground-session reveal, Android 15 lifecycle verification, and no change to Link, Guardian,
  or device authority; Companion OLED display policy with true-black primary surfaces, retained
  ROMVERSE accents, ambient-nebula suppression, immediate application, exact-route restoration,
  and Android 15 runtime verification;
  shared bounded, monotonic duplicate-percentage coalescing before Qt/Genesis/Live Console delivery
  for responsive multi-gigabyte extraction, partition hashing, Debloat, Ascension, recovery
  evidence, source preparation, and local phone backup; producer-owned privacy-safe Time Machine and
  Forge Control Live Console missions for snapshot verify/restore, local backup, external backup,
  and recovery-evidence revalidation, with raw failure paths/identifiers excluded and success
  impossible before the producing service commits evidence; the same typed producer lifecycle for
  ROM Studio and Genesis operation completions, where operation/result type, exact project and
  independently reloaded persisted evidence must agree before Genesis may clear an error or advance;
  source blueprints, rebuild inputs, local candidates, AVB topology, and offline-signing export/
  import, including explicit rejection of unexpected completion payloads; Forge Arsenal byte-measured official
  downloads and completed-file-measured pinned tool sets, with release lookup, verification,
  extraction, activation, unknown-length transfer and Ubuntu authorization kept honestly
  indeterminate instead of using fixed stage percentages; bounded private atomic and
  strict-schema OTA/fastboot/partition-bundle source blueprints, local-build attempts/results,
  super verification, and AVB topology, including indeterminate adapter/tool/metadata phases,
  genuine cumulative fastboot/super and partition-image hashing bytes when a stable total exists,
  removal of the fixed 5/42/55/72/88 and 5–90 scales, terminal completion only after the source-
  bound receipt is stored, and source-mutation rejection; including
  contained log/artifact validation and schema-three AVB image size/mtime identity while legacy
  schema two remains readable but cannot promote online verified-fix evidence;
  Payload Atlas schema-two manifests with case-tolerant canonical discovery, bounded private atomic
  persistence, strict top-level and partition schemas, source/payload/tool SHA-256 binding,
  extraction-time payload and tool rehashing, and readable schema-one history that is automatically
  rescanned in the same background operation before extraction continues; scan and opaque extraction
  phases remain honestly indeterminate, verified output images switch to cumulative measured bytes,
  terminal 100 waits for manifest commit, and linked pre-existing partition targets fail closed;
  fastboot super normalization/LP extraction remains indeterminate, then switches to exact
  cumulative produced-image hash bytes without fixed 4/32/72 milestones and completes only after
  the source-bound unpack receipt is stored;
  exact-contract offline signing with no private-key ingestion, exact returned-manifest binding,
  bounded private atomic request/receipt persistence, strict nested schemas, symlink and redirected
  evidence rejection, import-time artifact/policy hashing, responsive schema-two metadata identity,
  and one-time full-hash migration of valid schema-one receipts;
  Time Machine schema-two recovery evidence with a content digest, separate bounded private atomic
  locators, strict role/project/source binding, symlink/oversize/extra-field/workspace-redirection
  rejection, preserved schema-one history that requires full re-verification before readiness,
  and exact cumulative selected-file byte progress across backup/recovery roles with terminal
  completion withheld until the private evidence record is stored;
  Time Machine local schema-two snapshot and restore receipts with bounded enumeration, exact
  project/artifact/working-target containment, UI-thread metadata planning, background full hashes,
  byte-measured snapshot verification progress, honest indeterminate multi-phase restore,
  pre-restore safety-snapshot binding, hostile-file rejection, and verify-to-upgrade legacy UX;
  Partition Atlas shared accessible progress presentation with measured output-byte percentages and
  honest indeterminate states for payload scan, opaque extraction, or filesystem-tool phases;
  ROM Studio schema-two project and working-copy provenance with strict digests, bounded non-linked
  project discovery, private atomic storage, protected-original source-race and pre-planted-target
  rejection, canonical artifact containment, and schema-one read/verified-upgrade compatibility;
  combined Firmware Import and Automatic Detection with indeterminate startup, genuine protected-
  source copy percentages below completion, no fixed 68/32 weighting, and terminal completion only
  after the source-bound inspection report is sealed; standalone inspection exposes only genuine
  hash progress below completion while unbounded structure metadata remains animated;
  schema-two source inspection evidence with strict nested findings, bounded private atomic storage,
  exact source-name/hash binding, legacy refresh before extraction, source-identity race detection,
  special/encrypted-entry rejection, private staging, and linked/pre-planted tree refusal; isolated-
  tree extraction now keeps source/report/budget preflight honestly indeterminate, switches to one
  stable total with exact extracted/copied output bytes, removes the artificial 15% boundary, and
  reaches 100 only after atomic publication of the final working tree;
  Recipe Forger genuine six-stage design/save lifecycle with execution explicitly locked, plus an
  in-place stage-specific Archives guide that preserves every unsaved draft field and cannot create
  validation, approval, or execution authority, and private bounded source-bound digest-checked
  draft autosave/resume with stale-target downgrade and completed-draft cleanup; strict private
  atomic schema-two final Recipe persistence with stable Recipe digests, post-save reread,
  safe-target/locked-execution enforcement, and bounded no-link schema-one compatibility; private
  atomic schema-two Recipe run receipts and rollback snapshots with strict legacy loading,
  Recipe/step/tree/snapshot/target re-derivation, hostile-link/size/shape/rebinding rejection, and
  invalid-receipt exclusion from readiness and exported evidence; Recipe execution keeps approval,
  snapshot, and final-tree hashing indeterminate, switches only to genuine completed-step counts,
  removes fixed 3/25/95 milestones, and reaches 100 only after the private project receipt is saved;
  Companion Vitalis fresh/missing-evidence assessment, schema-four cross-device score re-derivation,
  stale-replay rejection, and Lifeline finding-specific checkpoint/fresh-scan
  comparison domain rules, including genuine local Live Console progress, strict state/evidence-bound
  schema-three private session state, verified schema-two migration, premature-completion recovery,
  and schema-one read compatibility; Companion stable route restoration across Activity recreation
  and fail-closed Android-emulator identity that never claims physical-device compatibility, backed
  by a connected Android 15 Activity gate for single status/Home ownership, primary navigation,
  About/community actions, and recreation persistence; a contained TLS-pinned Android-to-Desktop
  Link fixture that proves schema-six Live Console/Device DNA/Ascension display, the schema-four
  health return channel, remembered-session refresh, one-time evidence-panel hydration after Activity
  recreation, and the Ascension no-authority/permanent-no-relock boundary; direct distinct Device DNA
  and Ascension drawer routes plus explicit awaiting-Link wording that cannot falsely claim synchronization;
  Companion Android-Keystore AES-GCM storage for the reusable Link token with one-way legacy migration,
  tamper rejection, and plaintext-preference removal; emulator-only previous-to-current APK update
  continuity for private Settings, Activity, Galaxy, Vitalis trend, encrypted Link credential and
  Lifeline integrity evidence, with a host runner that refuses non-emulator Android targets;
  Desktop App Launchpad measured monotonic APK hash/container-inspection progress with duplicate
  actions locked, while the ADB installation phase remains honestly indeterminate rather than
  presenting a fabricated percentage;
  Desktop Members and Command Console
  background-operation progress with duplicate-probe locking; Companion single-owner persistent
  top-right connectivity status with duplicate page/drawer indicators removed;
  Desktop About ROMVERSE V3 and Companion About ROMVERSE V2 with live build metadata,
  Promise/creator/ecosystem/trust story, exact clean ROMVERSE/RadForge Labs website and
  Facebook/Reddit actions with crisp standalone icons; Desktop V3 also preserves both approved
  identities in one responsive hero, connects all four product-family cards to canonical Desktop
  routes, exposes external-launch failure honestly, and stores Origin discovery in a private,
  bounded, exact-schema atomic record; both experiences retain locally persistent
  double-click/double-tap Origin discovery and replay, seven-chapter Origin story, honest Beyond the
  Verse discovery state, functional off-by-default cinematic ambience, immediate exit, pause,
  navigation, skip-to-finale, Reduced Effects handling, progress, and responsive scrolling.
- **PARTIAL:** Genesis/Ascension/Guardian integration, Companion Vitalis/Lifeline, connected online
  remediation, and local Link are functional foundations but still need broader hardware testing.
  Connected remediation V2 preserves tamper-detecting receipts and presents source, explicit
  freshness (including unconfirmed dates), exact scope, independent corroboration, confidence,
  and its confidence reason; all remote text remains guidance-only.
  Link v3 has repository restart/reconnect/identity-binding tests and a verified APK install, but its
  two-screen safety-code pairing, 30-day expiry lifecycle, DHCP-change recovery, and hostile-network
  behavior still require physical runtime validation before a public safety claim.
- **NOT YET IMPLEMENTED OR VERIFIED:** public Synapse and AI services, production Members/billing,
  public forum/community backend, signed release infrastructure, encrypted remote Link, full
  multi-OEM device coverage, and production disaster recovery.
