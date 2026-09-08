# ROMVERSE Knowledge Coverage & Value Gate

ROMVERSE acquires evidence only when it closes a specific evidence gap for a named product feature.
A public source's existence, popularity, search ranking, or apparent technical detail is not a
reason to retain it.

## Required source proposal

Before adding an adapter or parser, record all of the following:

1. Named ROMVERSE consumer and exact evidence gap.
2. Fields expected and the testable capability they unlock.
3. Exact source authority, URL/scope, revision/date, and freshness rule.
4. Parser identity, byte/item limits, validation and independent-corroboration method.
5. Conflict behavior and explicit stop condition.
6. Privacy filtering, licensing/terms basis, and minimum retention.
7. Why this source is higher value than the available alternatives.

If any item is missing, acquisition does not begin. Each approved slice adds only one bounded source
family and stops when its named fields are obtained, its scope changes, validation conflicts, terms
are unclear, or its limits are reached.

## Coverage matrix

| Data category and expected fields | Named consumers | Authority, freshness, validation and conflict path | Privacy, licensing and retention | Capability unlocked and stop condition |
|---|---|---|---|---|
| Device identity and variants: manufacturer, brand, model, codename, retail names, regional variants | Device DNA, Compatibility Matrix, Device Atlas, Nexus, Insight | Official device catalogs/OEM records; exact normalized identifiers; scope; dated digest; ambiguity remains conflicting/unconfirmed | Public identifiers only; retain matched claims, not catalogs | Accurate identity label and research scope; stop on ambiguity or no exact match |
| Firmware/build identity: official package/manifest URL, build/branch/region, release date, digest, dependencies and predecessor | Device DNA, Compatibility Matrix, Pathfinder, Guardian, Recovery, Nexus, Foresight, Knowledge Archives | Official OEM index/manifest first; freshness per channel; exact device/build/package comparison; conflicting versions remain visible | No account/private download data; retain metadata/excerpts/digests under source terms, never package bulk | Candidate update relationship and required evidence; stop before download/install authority |
| Partition topology: dynamic/super layout, sizes, filesystems, slots and mount roles | Device DNA, Compatibility Matrix, Pathfinder, Guardian, Recovery, First Light, Device Atlas, Simulation Lab | Firmware-derived structured metadata plus official platform requirements; exact artifact hash; live read-only comparison may strengthen or conflict | Local artifact metadata only; exclude private paths; retain normalized values/digests | Model safe inspection/build/recovery prerequisites; stop on missing exact firmware or topology conflict |
| SoC/architecture and boot formats: platform/ABI, kernel/device-tree, boot, init_boot, vendor_boot and dtbo format/version | Device DNA, Compatibility Matrix, Pathfinder, First Light, Foresight, Device Atlas, Simulation Lab | Official specifications and maintained public trees bound to revision; firmware structure corroboration; version drift marks outdated | Retain small structured facts and revision links under repository licenses | Select compatible analysis/build simulation requirements; stop on variant/revision uncertainty |
| AVB/unlock/rollback evidence: chain, keys/digests, rollback indexes, bootloader/unlock/critical state and verified-boot requirements | Device DNA, Compatibility Matrix, Pathfinder, Guardian, Recovery, First Light, Foresight, Simulation Lab | Official Android/OEM requirements plus exact firmware/live read-only evidence; conflicts block consequential planning | Never retain secrets/private keys; retain public requirements and local digests only | Explain verification and recovery gates; never authorizes unlock, flash or relock; stop on any conflict |
| Read-only device modes: supported ADB, Fastboot, Fastbootd and Recovery observations and declared transitions | Device DNA, Pathfinder, Guardian, Recovery, Nexus, Insight, Device Atlas, Simulation Lab | Official protocol/OEM documentation and exact read-only observations; transition claims remain descriptive until observed | Exclude serials/IMEI/account data; retain pseudonymous bounded observations | Identify current mode and next safe evidence check; stop before issuing a device-changing command |
| Host tools/drivers/platform compatibility: tool/version, operating system, driver/interface requirement and known limitation | Compatibility Matrix, Pathfinder, Guardian, Recovery, First Light, Nexus, Knowledge Archives | Official Android/OEM/tool-maintainer documentation bound to version; verified local host receipt may corroborate | No host usernames/private paths/secrets; honor tool documentation licenses | Resolve inspection prerequisites and explain missing host capability; stop before arbitrary installation |
| Recovery/backup/restore routes and failure modes: prerequisites, affected state, expected result, rollback route and known failure | Pathfinder, Guardian, Recovery, Nexus, Foresight, Knowledge Archives, Simulation Lab | Official/OEM/maintainer sources first; exact device/firmware scope; simulation or observed outcome required for promotion | No user data/backups/log dumps; retain bounded descriptions and outcome digests | Compare recovery options and rehearse non-consequentially; stop on absent exact scope or recovery evidence |
| Diagnostics: symptoms, error identifiers, safe observations, affected builds and expected findings | Device DNA, Pathfinder, Recovery, Nexus, Insight, Knowledge Archives | Official or maintained technical guidance; exact heading/revision/digest; conflicts stay visible; stale guidance requests research | Retain short excerpts and ROMVERSE-authored descriptions only; exclude logs/PII and bulk page content | Explain a focused read-only investigation and one next action; never execute source prose |
| ROM/root/debloat compatibility: exact prerequisites, risks, affected firmware, expected outcome and rollback | Compatibility Matrix, Pathfinder, Guardian, Recovery, First Light, Nexus, Foresight, Knowledge Archives, Simulation Lab | Official project/maintainer repositories with signed/tagged revision where available; exact device/firmware outcome required beyond source-reported | No binaries, credentials or personal telemetry; license-aware metadata/excerpts only | Form candidate plans and simulations; stop before build/install/root/debloat or when scope is not exact |
| Guide/fix claims: exact scope, symptoms/errors, prerequisites, descriptive non-executable procedure, expected result, failure and rollback evidence | Pathfinder, Guardian, Recovery, Nexus, Insight, Knowledge Archives, Simulation Lab | Guide is officially documented or source-reported; fix becomes independently corroborated only across independent publishers; conflict lowers confidence | Short reviewed excerpt plus provenance; no commands/code/scripts or copyrighted bulk copy | Offer evidence-backed explanation and review path; stop before automatic action or unsupported promotion |
| Privacy-safe outcomes: exact device/firmware binding, observed pre/post state, result, failure and recovery provenance | Compatibility Matrix, Guardian, Recovery, First Light, Nexus, Insight, Foresight, Knowledge Archives, Device Atlas, Simulation Lab | Exact local read-only/outcome receipts; independent publishers may corroborate; only exact observed results can live-confirm/ROMVERSE-verify | Strip serials, IMEI, accounts, paths, secrets and personal data; retain digests and minimum normalized observations | Strengthen or retire a scoped claim and improve simulation; never bypass Guardian or consent |

## Prioritized acquisition order

1. Exact official OEM firmware indexes, manifests, support records, and service documentation that
   close a named device/build gap.
2. Official Android/AOSP specifications, compatibility requirements, and narrowly scoped public
   issue evidence needed by a named consumer.
3. Maintained public device, kernel, recovery, and host-tool repositories at an exact revision.
4. Reputable technical guides and diagnostic/error references for an already identified gap.
5. Technical community reports only when technically specific and useful, always retained as
   low-confidence `source-reported` evidence until independently corroborated.

This order is not a crawl queue. Each new source family requires a separate reviewed proposal and
approval, and acquisition stops after the approved fields are obtained or a stop condition fires.

## Evidence status and authority rules

- Community evidence remains low-confidence `source-reported` unless it is technically specific,
  potentially useful, and independently corroborated by a genuinely separate publisher.
- Votes, repetition, mirrors, a source's own success claim, and internal consistency are not
  corroboration or outcome proof.
- Official documentation is not a confirmed fix. `live-confirmed` and ROMVERSE-verified require an
  exact device/firmware observed outcome with revalidated provenance.
- Source prose is never a command. Evidence may inform planning, but Guardian remains the only
  consequential authority and requires the exact current operation contract plus fresh consent.
- Uncertainty remains `UNCONFIRMED`; conflicts trigger focused investigation. Bootloader relocking
  remains permanently prohibited.

## Permanently excluded acquisition

Do not retain generic news, reviews, marketing, SEO summaries, duplicated mirrors, uncited or
scope-free tips, arbitrary crawls, bulk copyrighted page copies, raw response archives, personal
identifiers, credentials, unrelated telemetry, popularity/votes as proof, private/authenticated
sources, or material obtained by bypassing access or anti-bot controls. Evidence that cannot improve
identity, compatibility, diagnosis, planning, recovery, simulation, or safety fails the value gate.
