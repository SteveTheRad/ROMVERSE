# ROMVERSE Product Assurance

## Authorization verdict — Device Intelligence canonical firmware-identity projection

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed authoritative checkpoint: `7144fbb4325e4ea12f7c28e37d58c04302fe9ba0`
- Exact approved code/evidence base: `7144fbb4325e4ea12f7c28e37d58c04302fe9ba0`
- Approved implementation branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **AUTHORIZED — PURE CORRELATED-EVIDENCE-TO-CANONICAL-FIRMWARE-IDENTITY PROJECTION**

### Decision

One further foundation checkpoint is justified, useful and non-overlapping. ROMVERSE now has an
approved strict evidence-correlation report, an approved research-evidence projection into its
existing `CanonicalDeviceIdentity`, and an existing but otherwise unbridged
`CanonicalFirmwareIdentity`. The smallest necessary continuation is a pure firmware projection
that binds already-correlated firmware metadata to the approved canonical device projection and
reuses the existing canonical firmware constructor. It creates the evidence contract needed before
any later Device DNA or compatibility consumer can be considered; it does not wire such a consumer.

The branch is clean at the exact approved head and Forgejo and GitHub are identical. Other Linux,
Windows, UI, Recovery and Companion worktrees remain separate and protected. This authorization
does not approve acquisition, a source adapter, runtime integration or a consequential action.

### Exact authorized scope

Implement one immutable, deterministic, side-effect-free projection that consumes only:

- one strictly parsed `EvidenceIdentityProjection` containing a formed canonical device identity;
- one strictly parsed `EvidenceCorrelationReport` and the exact `OnlineEvidenceClaim` records
  bound by that report; and
- no unbound caller metadata, inferred device relationship or external instruction.

The projection must either return one existing `CanonicalFirmwareIdentity` or an immutable,
content-digested `UNCONFIRMED` result with deterministic reasons. It must:

1. revalidate the device projection, correlation report, claims, exact source/key/domain/artifact
   bindings, active lifecycle use, canonical ordering and all zero-authority fields;
2. accept exactly one required `firmware.build-identity` claim under
   `ClaimAuthorityDomain.FIRMWARE_IDENTITY` and `ClaimKind.IDENTITY`; its structured value must be
   strict canonical JSON containing only `model_variant`, `region`, `build_id`,
   `firmware_version`, `android_version`, `security_patch` and `artifact_sha256`, with exact
   model/build/artifact values mandatory and optional values remaining empty when unproved;
3. distinguish the evidence source's content digest from the firmware artifact SHA-256. The former
   proves which source artifact supplied the claim; it must never be substituted for the latter;
4. require the build claim's exact manufacturer, model, codename, build, firmware-version,
   Android-version and region scope to agree field-for-field with the structured metadata and the
   projected canonical device identity where applicable. Similar names, families, aliases,
   case-insensitive guesses, omitted consequential scope or adjacent models must remain
   `UNCONFIRMED`;
5. optionally accept exactly one `firmware.partition.layout` claim only under
   `ClaimAuthorityDomain.PARTITION_LAYOUT`, with one exact SHA-256 value and the same exact device,
   model, build, firmware, Android and region scope. Absence leaves the layout digest empty;
   duplicate, differently scoped, contradictory or malformed layout evidence blocks identity;
6. retain and block on every correlation investigation. Missing, duplicate, retained, stale,
   unconfirmed, unsupported, contradictory, differently scoped or privacy-unsafe evidence must
   produce no firmware identity, except malformed/tampered/private input may be rejected outright;
7. call the existing `create_canonical_firmware_identity()` implementation without modifying or
   duplicating its identity algorithm. The resulting evidence claim IDs must equal exactly the
   selected active claims and the canonical device ID must equal the device projection's identity;
8. strictly parse stored projections and reject extra fields, unsupported schema, malformed types,
   non-canonical ordering, changed digests, inconsistent device/report/claim bindings and any
   re-digested internal substitution; and
9. preserve input-order independence, compatibility `UNCONFIRMED`, execution authority `none`, and
   phone action, Guardian approval and bootloader relocking as false in construction and parsing.

The projection is research/firmware-derived identity evidence only. It must not claim that an
artifact fits a live phone, represents the phone's installed build, can be flashed, is recoverable,
or is compatible.

### Exact file ownership

Engineering may modify only:

- `src/romverse/device/evidence_firmware.py`, new pure projection contract;
- `tests/test_device_intelligence_firmware_projection.py`, new focused deterministic tests;
- `src/romverse/device/__init__.py`, only to export the approved projection API;
- `docs/DEVICE-INTELLIGENCE-FOUNDATION.md`, only to describe this projection and exclusions; and
- `docs/sync/BUILD-STATUS.md`, only for the implementation handoff.

The existing canonical device/firmware identity constructors, evidence identity/correlation,
Online Evidence, source adapters, coverage allowlist, persistence, Knowledge/Synapse, Device DNA,
Compatibility Matrix, Nexus/Pathfinder/Foresight/Insight, First Light, Guardian/Recovery,
firmware inspection/build/install, platform/UI/Companion, packaging, signing and release files are
protected.

### Required focused verification

Tests must cover:

- exact successful device/build/artifact binding and input-order independence;
- strict build JSON shape and the required model, build and firmware-artifact digest;
- exact distinction between source-content and firmware-artifact digests;
- exact device manufacturer/model/codename and all supplied firmware scope matches;
- absent optional metadata remaining empty with no inference;
- an optional exact same-scope partition-layout digest;
- missing, duplicate, retained, stale, unconfirmed, unsupported, wrong-kind, wrong-domain,
  contradicted, investigated and differently scoped evidence returning deterministic
  `UNCONFIRMED` with no identity;
- rejection of claim/report/device-projection substitution, dangling or extra claims, private
  values, extra JSON/stored fields, malformed types, unsupported schema and changed digests;
- strict stored semantic checks after all ordinary nested and projection digests are recomputed;
- reuse of `CanonicalFirmwareIdentity`, exact evidence-claim IDs and canonical-device binding; and
- inability to promote compatibility, Device DNA/live-device state, execution, phone action,
  Guardian approval or bootloader relocking.

Rerun the established **181-test** Device Intelligence selection approved at `59b9860`, plus every
new focused firmware-projection test. Run Ruff check and format verification only on the three
owned Python files and run `git diff --check` from exact base `7144fbb`. No full suite, live
acquisition, hardware test, application launch or hosted CI is authorized or required.

### Exclusions and stop condition

No source acquisition, crawling, network use, adapter change, persistence/backend, protected
artifact read, phone/emulator/ADB/Fastboot, firmware extraction/mutation/build/flash/root/debloat,
Device DNA/Matrix/Nexus/First Light/runtime/UI integration, Guardian/Recovery change,
platform/UI/Companion work, hosted CI, Forgejo Actions, signing, publication, release, bootloader
lock or relock is authorized.

Engineering must implement one coherent checkpoint only in the owned paths, run the focused
verification, commit, push Forgejo first, verify the exact Forgejo SHA, mirror the identical commit
to GitHub and stop for independent Product Assurance. No consumer wiring, source adapter or later
Device Intelligence slice may begin automatically.

### Gate status

- Evidence correlation and canonical device-identity projection: **APPROVED**
- Pure canonical firmware-identity projection: **AUTHORIZED**
- Device DNA/runtime/compatibility integration and later Device Intelligence: **CLOSED**
- Acquisition, persistence/backend, device/consequential, signing/publication/release: **CLOSED**

## Reviewed correction checkpoint: 59b9860 — Device Intelligence identity-projection integrity

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed checkpoint: `59b986060d65cf8d6b7e54ae8dc73e1992a915d5`
- Correcting verdict: `700750e6704707631c6d22013e6b37948f732f72`
- Original authorization: `a0d3b3050093227c0540061e80e4b4db64277919`
- Exact original approved base: `79446b7d44bc3e2149064fec323048cb25e296f5`
- Branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **APPROVED — CORRECTION COMPLETE; SAFE STOP**

### Decision and repository evidence

The checkpoint is the direct child of the correction verdict, is identical on Forgejo and GitHub,
and changes exactly the four correction-owned paths: the pure identity-projection contract, its
focused tests, the foundation description and Build Status. The worktree was clean before and after
review. No other production, test, evidence, platform, Device DNA, Matrix, Nexus, First Light,
Synapse, Guardian/Recovery, source-acquisition, firmware, UI/Companion, backend, CI, signing,
publication or release file changed.

The minimum correction is complete:

1. projection now begins with the validated correlation report's exact investigation reasons, so
   any correlation investigation deterministically retains those reasons and prevents canonical
   identity formation;
2. strict parsing now requires projection-level and nested marketing names to agree exactly; and
3. strict parsing rejects any nested brand, region, OEM identifier, alias, family ID, SoC or
   platform inference, including a record whose nested identity and projection digests were both
   recomputed consistently.

Product Assurance independently replayed all three former failure classes and they now reject or
remain `UNCONFIRMED` as required. The established 162-test selection plus all 19 focused
identity-projection tests passed: **181/181**. The three explicit correction regressions passed
again independently. Ruff 0.16.6 check and format verification passed the two owned Python files,
and `git diff --check` passed from the correction verdict. Input-order independence, strict
report/claim/source/key/domain/artifact binding, privacy rejection, reuse of the existing
`CanonicalDeviceIdentity`, deterministic `UNCONFIRMED` results and all zero-authority fields remain
covered and passing.

A formed research-derived identity still confers no compatibility, live-device, Device DNA,
Guardian, execution, phone-action or relock authority. External evidence remains evidence only;
unknown, conflicting or investigated evidence remains `UNCONFIRMED`. The permanent bootloader
lock/relock prohibition is unchanged.

### Stop and gate status

This verdict approves only the corrected canonical device-identity projection checkpoint. It does
not authorize another Device Intelligence slice. A next foundation or integration checkpoint needs
a separate repository-based Product Assurance authorization from this approved head.

- Evidence-correlation contracts: **APPROVED**
- Canonical device-identity projection and integrity correction: **APPROVED**
- Any subsequent Device Intelligence implementation: **CLOSED — SAFE STOP**
- Acquisition, persistence/backend, firmware identity, Device DNA/runtime integration,
  Matrix/Nexus/First Light, Guardian/Recovery, platform/UI/Companion, hosted CI, consequential,
  signing, publication and release work: **CLOSED**

## Reviewed checkpoint: d42ab06 — Device Intelligence canonical identity projection

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed checkpoint: `d42ab0644a93c9f6b47077398d96807cd4026577`
- Authorizing verdict: `a0d3b3050093227c0540061e80e4b4db64277919`
- Exact approved base: `79446b7d44bc3e2149064fec323048cb25e296f5`
- Branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **CORRECTION REQUIRED — STORED PROJECTION PARSING DOES NOT ENFORCE THE PROJECTION'S OWN NON-INFERENCE BOUNDARY**

### Decision and verified scope

The checkpoint is the direct child of its authorization, changes exactly the five owned paths and
is identical on Forgejo and GitHub. The implementation is pure and acquisition-inert: it introduces
no filesystem write, persistence, network call, device query, subprocess action, runtime wiring or
compatibility/planning/execution path. It reuses the existing `create_canonical_device_identity()`
algorithm rather than creating a competing device ID, exactly binds the input report to its complete
claim set, validates claim identities, requires active exact manufacturer/model/codename evidence,
preserves deterministic ordering and fixes compatibility, execution, phone, Guardian and relock
authority to their safe values.

Product Assurance independently ran the exact established 162-test selection plus all 16 new
focused tests: **178/178 passed**. Ruff 0.16.6 check and format verification passed the three owned
Python files, and `git diff --check` passed. The worktree remained clean. No firmware identity,
Device DNA, Matrix, Nexus, First Light, Synapse, Guardian/Recovery, source acquisition,
platform/UI/Companion, backend, hosted-CI, signing, publication or release file changed.

The checkpoint is not approvable yet because its stored-record parser accepts internally
inconsistent or projection-forbidden identities after a caller recomputes the ordinary content
digest:

1. `marketing_names` is stored both at projection level and inside the nested
   `CanonicalDeviceIdentity`, but parsing checks only claim IDs. Product Assurance changed the
   top-level marketing name, recomputed the projection digest and observed successful parsing while
   the nested identity retained the original name.
2. The parser accepts a correctly self-digested nested canonical identity containing non-empty
   brand and region even though this projection is explicitly forbidden to infer those fields.
   The same omission applies to OEM identifiers, aliases, family IDs, SoC and platform.
3. Construction ignores correlation-level investigation when it involves the optional marketing
   key. Product Assurance supplied two explicitly contradictory, active marketing-name claims.
   The correlation report truthfully required investigation, but the projection formed an identity,
   embedded both conflicting names and emitted no reason.

These are deterministic integrity/boundary defects, not a claim that SHA-256 provides protection
against a same-user rewrite. Strict parsing must nevertheless enforce the record's internal semantic
invariants, and conflicting evidence must remain `UNCONFIRMED` rather than being copied into a
formed identity.

### Minimum exact correction authorized

Correct only this projection contract and its focused evidence:

1. When the validated correlation report requires investigation, return no canonical identity and
   retain deterministic correlation investigation reasons in the `UNCONFIRMED` projection. At
   minimum, explicitly contradictory or conflicting active marketing-name evidence must never enter
   a formed identity.
2. During strict parsing of a formed projection, require projection-level `marketing_names` to equal
   the nested identity's marketing names exactly and require nested brand, region, OEM identifiers,
   aliases, family IDs, SoC and platform to remain empty. Reject any mismatch even when every
   ordinary content digest has been recomputed consistently.
3. Add focused regressions reproducing both re-digested stored-record substitutions and the
   correlation-investigation case above. Preserve the existing exact report/claim binding,
   deterministic ordering, privacy checks, existing canonical identity constructor and all zero-
   authority values.

Correction ownership is limited to:

- `src/romverse/device/evidence_identity.py`;
- `tests/test_device_intelligence_identity_projection.py`;
- `docs/DEVICE-INTELLIGENCE-FOUNDATION.md`, only if its description requires exact correction;
- `docs/sync/BUILD-STATUS.md`, only for the corrected handoff.

`src/romverse/device/__init__.py` and every other file are protected. Rerun the established
**162-test** selection plus every focused identity-projection test, including the new correction
regressions; run focused Ruff check/format on the two changed Python files and `git diff --check`
from `a0d3b30`. Commit one coherent correction, push Forgejo first, mirror the identical commit to
GitHub and stop for independent Product Assurance.

No further Device Intelligence slice is authorized. No acquisition, crawling, persistence,
canonical firmware projection, Device DNA/runtime integration, network, phone/emulator/ADB/
Fastboot, firmware mutation/build/flash/root/debloat, Matrix/Nexus/First Light, Guardian/Recovery,
platform/UI/Companion, backend, hosted CI, signing, publication, release, bootloader lock or relock
may occur.

### Gate status

- Evidence-correlation contracts: **APPROVED**
- Canonical device-identity projection checkpoint: **CORRECTION REQUIRED**
- Minimum parser/investigation correction above: **AUTHORIZED**
- Any subsequent Device Intelligence or consequential work: **CLOSED**

## Authorization verdict — Device Intelligence canonical device-identity projection slice

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed authoritative checkpoint: `79446b7d44bc3e2149064fec323048cb25e296f5`
- Exact approved code/evidence base: `79446b7d44bc3e2149064fec323048cb25e296f5`
- Approved implementation branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **AUTHORIZED — PURE EVIDENCE-TO-CANONICAL-DEVICE-IDENTITY PROJECTION CONTRACT**

### Decision

One further foundation checkpoint is safe, high-value and non-overlapping. The repository now has
strict canonical device/firmware identity records, claim-specific authority and lifecycle records,
and an approved deterministic correlation report, but no code consumes that correlation report to
form an existing `CanonicalDeviceIdentity`. The smallest useful next seam is therefore a pure
device-identity projection. Firmware identity, Device DNA persistence and runtime consumers remain
separate later boundaries.

This authorization is consistent with the creator-approved unfamiliar-device direction in
`docs/APPROVED_COMMITMENTS.md`, the identity-first Device Intelligence goal in
`docs/ROMVERSE-20-STAGE-MASTER-GOAL.md`, and the evidence/Device DNA boundaries in
`docs/MASTER_SPECIFICATION.md` and `docs/ARCHITECTURE.md`. There is no `docs/ROADMAP.md` at this
checkpoint; the master specification and 20-stage goal are the applicable repository roadmap.
The direction documents remain product intent rather than blanket implementation authority, so
this verdict authorizes only the exact contract below.

Forgejo and GitHub expose identical `79446b7` heads with zero divergence. The existing Device
Intelligence worktree is clean and remains owned by this same handoff stream, although its local
checkout is still at implementation commit `f1f0606` and must fast-forward through this published
authorization before work begins. Other Linux, Windows, UI, Recovery and Companion worktrees are
separate and protected. No relevant uncommitted file is owned by another task.

### Exact authorized scope

Implement one deterministic, local, side-effect-free projection contract that consumes only an
existing validated `EvidenceCorrelationReport` and the exact `OnlineEvidenceClaim` objects bound
by that report, and either returns one existing `CanonicalDeviceIdentity` candidate or a strictly
bounded immutable `UNCONFIRMED` projection result explaining why no identity can be formed.

The contract must:

1. revalidate the exact correlation schema, digest, zero-authority fields and canonical ordering,
   then bind every consumed claim by claim ID, source ID, claim key, authority domain and source
   artifact digest to an `ACTIVE` correlation record;
2. use only the already allowlisted structured identity keys
   `device.identity.manufacturer`, `device.identity.model`, `device.identity.codename`, and the
   optional discovery-only `device.identity.marketing-name`; require their existing exact authority
   domains and `ClaimKind.IDENTITY`;
3. require exactly one non-empty manufacturer, model and codename value with one exact mutually
   consistent scope. Missing, duplicate, retained, stale, unconfirmed, contradictory,
   similar-but-not-exact, substituted or differently scoped required evidence must produce
   `UNCONFIRMED` with deterministic reasons and no canonical identity;
4. invoke the existing `create_canonical_device_identity()` implementation for an exact result;
   do not create a parallel identity algorithm, modify its digest rules or reinterpret the legacy
   `DeviceIdentityResolver` receipt;
5. bind the resulting identity to exactly the consumed claim IDs. Marketing names may remain
   discovery metadata only. Do not infer brand, region, OEM identifiers, family, aliases, SoC or
   platform from a source category, marketing name, scope, filename or similarity;
6. return an immutable, strictly parsed and content-digested projection record that retains the
   correlation report digest, selected claim IDs and deterministic missing/conflict/investigation
   reasons; input ordering must not change the result; and
7. fix compatibility to `UNCONFIRMED`, execution authority to `none`, and phone action, Guardian
   approval and bootloader relocking to `false` in construction and parsing. A successfully formed
   canonical identity is still research-derived identity evidence, not a live-device match,
   compatibility decision, Device DNA promotion or permission to act.

The projection must perform no filesystem write, persistence, acquisition, network call, device
query, subprocess action, planning, compatibility assessment, confidence promotion or execution.

### Exact file ownership

Engineering may modify only:

- `src/romverse/device/evidence_identity.py`, new pure projection contract;
- `tests/test_device_intelligence_identity_projection.py`, new deterministic focused tests;
- `src/romverse/device/__init__.py`, only to export the approved projection types/functions;
- `docs/DEVICE-INTELLIGENCE-FOUNDATION.md`, only to document this checkpoint and its exclusions;
- `docs/sync/BUILD-STATUS.md`, only for the implementation handoff.

No other production, test, fixture, documentation or configuration file is owned. In particular,
the existing canonical identity implementation, firmware source identity, Online Evidence,
evidence correlation, evidence persistence, Synapse, Knowledge store/lookup/Archives, Device DNA,
Compatibility Matrix, Nexus/Pathfinder/Foresight/Insight, First Light, Guardian/Recovery,
source adapters/acquisition, local-store infrastructure, UI/platform/Companion, packaging,
signing and release files are protected.

### Required focused verification

The new tests must cover:

- exact manufacturer/model/codename projection and input-order independence;
- exact report/claim/source/key/domain/artifact binding and rejection of claim substitution;
- missing, duplicate, retained, stale, unconfirmed and non-identity required claims;
- one-sided or two-sided contradiction, conflicting values and conflicting/similar scope;
- strict required-key allowlisting and optional marketing-name discovery metadata;
- no inference of brand, region, OEM identifiers, aliases/family, SoC or platform;
- privacy rejection for serial, IMEI, account/user, credential/token and personal-path material;
- deterministic `UNCONFIRMED` reasons with no identity on every unresolved case;
- strict parse rejection for extra fields, unsupported schema, changed digest, malformed types and
  reordered/non-canonical collections; and
- inability of construction, parsing or a formed identity to promote confidence, compatibility,
  execution, phone, Guardian or relock authority.

Rerun the established **162-test** Device Intelligence selection approved at `79446b7` plus the
new focused module. Run Ruff check and format verification only on the three owned Python files,
and `git diff --check` from the exact approved base. No full suite, live acquisition, hardware test,
application launch or hosted CI is authorized or required.

### Exclusions and stop condition

No canonical firmware projection, Device DNA/Matrix/Nexus/First Light/runtime/UI integration,
persistence backend, source acquisition, crawling, network use, PostgreSQL/object storage,
phone/emulator/ADB/Fastboot, firmware mutation/build/flash/root/debloat, Guardian/Recovery change,
platform/Companion work, hosted CI, Forgejo Actions, signing, publication, release, bootloader lock
or relock is authorized.

Engineering must fast-forward the clean existing branch through this authorization, implement one
coherent checkpoint only in the owned paths, run the focused verification, commit, push Forgejo
first, verify the exact Forgejo SHA, mirror the identical commit to GitHub, update Build Status and
stop for independent Product Assurance. Do not create a new branch, acquire evidence, wire the
projection into a consumer or begin another Device Intelligence slice.

### Gate status

- Device Intelligence schema, Synapse lifecycle and evidence correlation: **APPROVED**
- Pure evidence-to-canonical-device-identity projection: **AUTHORIZED**
- Firmware identity projection, Device DNA/runtime integration and broader Device Intelligence:
  **CLOSED**
- Acquisition/backend/device/consequential/signing/publication/release work: **CLOSED**

## Reviewed checkpoint: f1f0606 — Device Intelligence evidence-correlation contracts

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed checkpoint: `f1f0606419664e94f1cbaf43d1c47defc25838b6`
- Authorizing verdict: `a010d4a923558e101c5ba520eaa0a8c9fbee9b77`
- Approved implementation base: `bf8091c5d40ad0d1007d757aaa61db8eebc4c50b`
- Branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **APPROVED — DETERMINISTIC EVIDENCE-CORRELATION CONTRACT COMPLETE; SAFE STOP**

### Decision and independent evidence

The checkpoint is approved. The implementation changes only the five paths authorized for this
slice: one new pure correlation module, its focused test module, bounded Knowledge exports, the
foundation contract document and Build Status. No existing Online Evidence, persistence, Device
DNA, identity, firmware, Synapse, Matrix, Nexus, First Light, Guardian/Recovery, acquisition,
platform, UI, Companion, packaging or release implementation changed.

The pure contract accepts the existing typed claim, claim-specific authority and lifecycle
records and binds them by exact claim/source identity, claim key/domain, artifact digest, scope and
support/contradiction relationships. It rejects duplicate, dangling, self-invalid, one-sided
contradiction and mismatched lifecycle bindings. Its canonical ordering makes the immutable report
and SHA-256 digest independent of input ordering.

Active applicable evidence is separated from retained superseded, quarantined and expired
evidence without deletion. Missing lifecycle or applicable domain authority, stale or unconfirmed
freshness and unusable claim states remain retained as `UNCONFIRMED`. Explicit contradictions are
preserved on both claims, and conflicting active values or scopes require investigation. Source
authority only establishes applicability; the report does not carry or raise source confidence,
claim confidence or compatibility.

Stored parsing requires an exact schema and field set, canonical record/reason/relationship order,
strict bounded identifiers and digests, and the exact recomputed report digest. It rejects private
serial, IMEI, account/user, credential/token and personal-path material. Compatibility is fixed to
`UNCONFIRMED`, execution authority to `none`, and phone action, Guardian approval and bootloader
relocking to `false` in both construction and parsing.

Product Assurance independently reran the exact authorized selection: **162/162 passed**, formed
from the established 146-test Device Intelligence baseline plus the 16 focused correlation tests.
Focused Ruff 0.16.6 check and format verification passed on all three owned Python files, and Git
diff/whitespace validation passed. The worktree remained clean. Forgejo and GitHub exposed the
identical implementation checkpoint with zero divergence before this verdict was published.

No filesystem write or persistence backend is present in the new module. No network acquisition,
live source, device/emulator/ADB/Fastboot, firmware/build/flash/root/debloat action, runtime or UI
wiring, Guardian/Recovery change, database/object storage, hosted CI, signing, publication,
release, bootloader lock or relock occurred.

### Authorization boundary and stop

No next Device Intelligence checkpoint is explicitly authorized. Engineering must stop this
branch after recording this verdict. Runtime consumer wiring, canonical identity/compatibility
promotion, persistence implementation, acquisition and broader Device Intelligence remain
**NOT AUTHORIZED**. Any next slice requires a new repository-based Product Assurance request that
names its exact purpose, approved base, branch, owned files, tests, exclusions and stop condition.

### Gate status

- Device Intelligence foundation Checkpoints 1 and 2: **APPROVED**
- Pure evidence-correlation contract checkpoint: **APPROVED**
- Any subsequent Device Intelligence implementation/integration: **CLOSED / NOT AUTHORIZED**
- Acquisition/backend/device/consequential/signing/publication/release work: **CLOSED**

## Authorization verdict — Device Intelligence evidence-correlation contract slice

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed authoritative checkpoint: `bf8091c5d40ad0d1007d757aaa61db8eebc4c50b`
- Exact approved code/evidence base: `bf8091c5d40ad0d1007d757aaa61db8eebc4c50b`
- Approved implementation branch: `device-intelligence/evidence-correlation-contracts`
- Review status: **AUTHORIZED — DEVICE INTELLIGENCE EVIDENCE-CORRELATION CONTRACT SLICE**

### Decision

One additional foundation checkpoint is safe and high-value now. Checkpoints 1 and 2 can represent
exact evidence claims, claim-specific source authority, lifecycle status, canonical identities and
Synapse retention, but there is not yet one deterministic acquisition-inert boundary that
correlates an existing claim with its exact authority and lifecycle records. Adding that pure
contract closes the next architectural seam without wiring Device Intelligence into Device DNA,
Compatibility Matrix, Nexus, First Light, Guardian, Recovery or any runtime consumer.

This is not authorization for broader Device Intelligence, a new database, a source harvester, an
identity resolver, a compatibility decision engine or a user-facing feature. It must extend and
consume the existing Checkpoint 1 contracts and must not replace `merge_claims()`,
`project_evidence()`, Knowledge lookup, Device DNA or Compatibility Matrix.

Repository inspection found no active owner or uncommitted work on the new correlation paths.
The main checkout's pre-existing Companion, Recovery-runtime and Windows-launch-contract changes,
the active Linux/Windows branches and the uncommitted UI Design Lab remain unrelated and protected.

### Exact authorized scope

Implement one deterministic, local, side-effect-free evidence-correlation contract that:

1. accepts only existing validated `OnlineEvidenceClaim`, `ClaimSourceAuthority` and
   `EvidenceLifecycle` objects and binds each relationship by exact claim ID, source ID, claim key,
   authority domain and source artifact digest;
2. separates active applicable evidence from retained-but-unusable superseded, quarantined and
   expired evidence without deleting or overwriting either side;
3. preserves explicit supporting and contradicting relationships, rejects dangling/self-invalid
   relationships and duplicates, and makes conflicting values or scopes require investigation;
4. treats missing or non-applicable claim-domain authority, stale/unconfirmed freshness, absent
   lifecycle data and any identity/firmware ambiguity as `UNCONFIRMED`; source authority metadata
   may describe applicability but may not raise an evidence claim's state or confidence;
5. produces one immutable, strictly validated, content-digested correlation report whose canonical
   representation is independent of input ordering and contains only bounded IDs, states, reasons
   and evidence references—not raw pages, logs, instructions, paths or device identifiers; and
6. fixes compatibility to `UNCONFIRMED`, execution authority to `none`, phone action and Guardian
   approval to `false`, and bootloader relocking to `false`.

The checkpoint may add no storage implementation and perform no filesystem write, network call,
device query, subprocess action, planning, compatibility promotion or execution. It may not create
canonical device/firmware identities from the correlated result; that remains a later separately
reviewed boundary.

### Exact file ownership

Engineering may modify only:

- `src/romverse/knowledge/evidence_correlation.py`, new pure contract module;
- `tests/test_device_intelligence_evidence_correlation.py`, new deterministic tests;
- `src/romverse/knowledge/__init__.py`, only to export the new approved contract types/functions;
- `docs/DEVICE-INTELLIGENCE-FOUNDATION.md`, only to document this checkpoint and its exclusions;
- `docs/sync/BUILD-STATUS.md`, only for the implementation handoff.

No other production, test, fixture, documentation or configuration file is owned. In particular,
`src/romverse/knowledge/online_evidence.py`, `evidence_persistence.py`, Device DNA, canonical
identity/source-identity modules, Synapse, Knowledge store/lookup/Archives, Matrix, Nexus, First
Light, Guardian/Recovery, infrastructure/local-store, source adapters/acquisition, all UI/platform/
Companion files, packaging, signing and release configuration are protected.

### Required focused verification

The new deterministic tests must cover:

- exact active claim/source/authority/lifecycle binding and input-order-independent digest;
- exact source ID, claim key/domain and artifact-digest mismatch;
- missing, duplicate, dangling and malformed records;
- similar-but-not-exact scope and authority non-applicability;
- stale and unconfirmed evidence;
- retained superseded, quarantined and expired evidence excluded from the active set;
- supporting evidence and explicit two-sided contradiction preservation;
- conflicting values/scopes and unresolved identity/firmware evidence remaining `UNCONFIRMED`;
- privacy rejection for serial, IMEI, account/user, credential and personal-path material;
- inability of any input or parsed output to promote confidence, compatibility, execution, phone,
  Guardian or relock authority; and
- strict parse rejection for extra fields, unsupported schema, changed digest and malformed types.

Rerun the established **146-test** Device Intelligence baseline from Checkpoint 2 plus the new
focused module. Run Ruff check/format on the owned Python files and `git diff --check` from the
approved base. No full suite, live acquisition, hardware test or hosted CI is authorized or
required.

### Exclusions and stop condition

No live/web acquisition, crawling, new source family, persistence/backend implementation,
PostgreSQL/object storage, runtime/consumer/UI wiring, Device DNA or canonical identity promotion,
Compatibility Matrix/Nexus/Pathfinder/Foresight/First Light change, Guardian/Recovery change,
phone/emulator/ADB/Fastboot, firmware/build/flash/root/debloat, platform/Companion work, hosted CI,
Forgejo Actions, signing, publication, release, bootloader lock or relock is authorized.

Engineering must create the approved branch from the exact base only after this authorization is
published, implement one coherent checkpoint within the owned paths, run the focused verification,
commit, push Forgejo first, verify the exact Forgejo SHA, mirror the identical commit to GitHub,
update Build Status and stop for independent Product Assurance. No later Device Intelligence slice
is pre-authorized.

### Gate status

- Device Intelligence foundation Checkpoints 1 and 2: **APPROVED**
- Pure evidence-correlation contract checkpoint: **AUTHORIZED**
- Runtime wiring, identity/compatibility promotion and broader Device Intelligence: **CLOSED**
- Acquisition/backend/device/consequential/signing/publication/release work: **CLOSED**

## Reviewed checkpoint: b46099d — Device Intelligence Synapse lifecycle contracts

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed checkpoint: `b46099d59f24c612fcda856d81acd72ec433a1a5`
- Authorizing verdict: `1cbda8c9bc1f600f0a81429476b8b0aa47645522`
- Branch: `device-intelligence/foundation-schema-contracts`
- Review status: **APPROVED — CHECKPOINT 2 COMPLETE; SAFE STOP**

### Decision and independent evidence

Checkpoint 2 is approved. The complete authorization-to-checkpoint diff changes only
`src/romverse/intelligence/synapse.py`, `tests/test_synapse.py`,
`docs/DEVICE-INTELLIGENCE-FOUNDATION.md` and Build Status, exactly matching the authorized
ownership. No persistence backend, acquisition, runtime consumer, Matrix/Nexus/First Light,
Guardian/Recovery, UI/platform/Companion, packaging or release path changed.

The additive lifecycle states preserve the existing Candidate → Verified Success → Strong →
Trusted progression, evidence-driven downgrades and retirement. Quarantined, superseded, expired
and retired records compile with zero confidence and are excluded from query results, while
`list_knowledge()` retains them with deterministic lifecycle explanations for Archives review.

Supersession is bound to one exact content-addressed knowledge identifier. Only a currently usable
replacement can suppress that exact predecessor; an unusable replacement cannot do so. A record
that targets itself, or whose contributions contain conflicting replacement targets, is
quarantined rather than reused. Expiry timestamps are normalized to timezone-aware UTC, cannot
precede contribution time and expire conservatively without deleting the underlying evidence.

Legacy schema-one caches that lack the three additive contribution fields continue to validate
against their original ledger digest and load with active defaults. Existing cache tamper,
privacy, exact-scope and independently verified-outcome checks remain in force. All resulting
knowledge remains `guidance-only`; no record gains compatibility, execution, phone, Guardian or
bootloader authority, and permanent no-relock is unchanged.

Product Assurance independently collected and ran the exact authorized baseline: **146/146
passed** across device identity, firmware source identity, Online Evidence, evidence persistence,
Knowledge coverage, Device DNA, Compatibility Matrix, Nexus planning, First Light, Synapse and
Guardian policy. Focused Ruff check passed, both changed Python files were already formatted, and
Git whitespace validation passed. The worktree was clean after review. Forgejo and GitHub exposed
the identical implementation checkpoint with zero divergence before this verdict was published.

No physical device, emulator, network acquisition, database/object-store deployment, hosted CI,
application execution, firmware/build/flash/root/debloat action, signing, publication, release,
bootloader lock or relock occurred.

### Authorization boundary and stop

Checkpoint 2 completes the two-part Device Intelligence foundation schema-contract authorization.
There is no explicit subsequent Device Intelligence implementation checkpoint in the existing
authorization. Broader Device Intelligence, live acquisition, persistence implementation,
runtime wiring and consumer/UI integration therefore remain **NOT AUTHORIZED**.

Engineering must stop this branch after recording this verdict. Any next slice requires a new
repository-based Product Assurance request naming its exact purpose, base, ownership, tests and
exclusions. This approval does not infer that authorization.

### Gate status

- Device Intelligence Checkpoint 1 schema contracts: **APPROVED**
- Device Intelligence Checkpoint 2 Synapse lifecycle: **APPROVED**
- Broader Device Intelligence implementation or integration: **CLOSED**
- Device/network/backend/consequential/signing/publication/release work: **CLOSED**

## Reviewed checkpoint: 63928f7 — Device Intelligence foundation schema contracts

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Corrected implementation checkpoint: `63928f7aeb6588189b6f9b53a16b13f9a695f70e`
- Original implementation checkpoint: `ffaa5c6af25b24ec884daa4a828f1b5093c2042c`
- Product Assurance authorization record: `d335bcf5c7308b5bcbebf3b8a7e3560e4c757f0e`
- Approved implementation base: `eac08f4d5c142380aa67588aee2be7faa5b64051`
- Branch: `device-intelligence/foundation-schema-contracts`
- Review status: **APPROVED — CHECKPOINT 1 COMPLETE; CHECKPOINT 2 EXPLICITLY AUTHORIZED**

### Decision and independent evidence

Checkpoint 1 is approved. Product Assurance independently inspected the authorization, full
authorization-base-to-checkpoint diff, corrected source, tests, contract documentation and Build
handoff. The complete implementation changes only the twelve paths authorized for Checkpoint 1.
The correction from `ffaa5c6` changes eight paths within that same set. No protected local-store,
Device DNA, Matrix, Nexus, First Light, Synapse, Guardian/Recovery, acquisition, platform, UI,
Companion, packaging, signing or release path changed.

The corrected privacy boundaries reject or sanitize a standalone 15-digit IMEI-like numeric value
without accepting a surrounding label as a prerequisite. The same fail-closed pattern is applied to
canonical device identity, canonical firmware identity and retained Online Evidence text. Product
Assurance also exercised exact, embedded, 14-digit and 16-digit boundary cases independently.

Lifecycle construction and strict parsing now normalize observation, retrieval, revalidation and
history times to timezone-aware UTC. They reject `observed_at > retrieved_at`, reject
`revalidated_at < retrieved_at`, reject every history timestamp earlier than `observed_at`, and
reject a non-empty history whose final status differs from the current lifecycle status. Exact
boundary equality remains valid. Lifecycle content addressing includes the normalized chronology,
current status and complete ordered history, so accepted tampering changes the expected digest and
non-canonical stored representations fail closed.

Product Assurance independently collected and ran the exact authorized baseline: **141/141
passed** across device identity, firmware source identity, Online Evidence, evidence persistence,
Knowledge coverage, Device DNA, Compatibility Matrix, Nexus planning, First Light, Synapse and
Guardian policy. Focused Ruff check passed, all 16 reviewed Python files passed Ruff format check,
and the authorization-base-to-checkpoint Git whitespace check passed. Sixteen additional direct
edge assertions for the corrected privacy and chronology boundaries passed.

The worktree was clean before review and remained clean after verification. Live `ls-remote`
inspection confirmed that local, Forgejo and GitHub branch heads were identical at
`63928f7aeb6588189b6f9b53a16b13f9a695f70e`. Compatibility remains `UNCONFIRMED`; execution
authority remains `none`; phone action, Guardian approval and bootloader relocking remain `false`.
No physical device, emulator, network acquisition, hosted CI or application execution was used.

### Checkpoint 2 — explicitly authorized now

The prior Product Assurance authorization explicitly permits this gate to open after independent
Checkpoint 1 approval. Product Assurance therefore authorizes only the already-bounded additive
Synapse lifecycle checkpoint:

- modify only `src/romverse/intelligence/synapse.py`, `tests/test_synapse.py`,
  `docs/DEVICE-INTELLIGENCE-FOUNDATION.md` and `docs/sync/BUILD-STATUS.md`;
- add explicit quarantine, supersession and expiry contracts while preserving Candidate → Verified
  Success → Strong → Trusted, existing downgrade and retirement semantics;
- hide unusable lifecycle states from query results while retaining them for Archives explanation;
  and
- remain guidance-only with compatibility `UNCONFIRMED`, execution authority `none`, phone action
  and Guardian approval `false`, and bootloader relocking permanently `false`.

No other Device Intelligence, persistence backend, acquisition, runtime wiring, Matrix, Nexus,
First Light, Guardian/Recovery, UI/platform/Companion, phone/emulator, firmware, build, flash, root,
debloat, signing, publication or release work is authorized. Engineering must begin from the final
dual-remote Product Assurance head containing this verdict, implement one bounded checkpoint,
update Build Status, commit and push Forgejo first, mirror the identical commit to GitHub, and stop
for independent Product Assurance review.

## Authorization verdict — Device Intelligence foundation schema-contract slice

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Reviewed request anchor: `de263d2c3638690711369e15e309361c0552e7b3`
- Review status: **AUTHORIZED — DEVICE INTELLIGENCE FOUNDATION SCHEMA-CONTRACT SLICE**
- Approved implementation branch: `device-intelligence/foundation-schema-contracts`
- Approved implementation base: this Product Assurance authorization commit; its exact SHA must
  be recorded and verified on Forgejo and GitHub before the branch is created.

### Decision

The minimum additive foundation is safe to begin as a deterministic, local, fixture-driven
contract correction. Existing Device DNA, device identity, firmware source identity, online
evidence, Compatibility Matrix, Nexus/Pathfinder/Foresight, First Light, Synapse and Guardian
contracts already establish the right separation between evidence, planning and execution. The
requested work must extend those contracts; it must not introduce a parallel Device Intelligence
store, identity system, compatibility system or execution path.

The repository currently has a universal `IdentityAuthority` for retail-name resolution, a
claim-level online-evidence model with provenance, freshness and preserved conflict links, a
filename-derived `FirmwareSourceIdentity`, and a Synapse maturity sequence with downgrade and
retirement. It does not yet have a complete claim-domain authority contract, canonical device and
firmware identity records, explicit artifact/lifecycle history fields, or a storage abstraction for
future evidence persistence. Those are foundation correctness gaps, not new product features.

This authorization is deliberately split into two Product Assurance-gated checkpoints. Only
Checkpoint 1 below is authorized to start. Checkpoint 2 is bounded in advance so ownership is
clear, but implementation of it requires an explicit Product Assurance approval of Checkpoint 1.
This prevents simultaneous schema migration and Synapse state-machine changes from obscuring a
regression or silently strengthening evidence.

### Checkpoint 1 — authorized now

Implement only additive, backward-compatible contracts for:

- claim-specific source authority domains, with explicit applicability to a claim type and no
  universal trust inheritance;
- immutable, privacy-safe canonical device identity covering manufacturer, brand, exact model,
  codename, explicit regional/OEM identifiers, SoC/platform, aliases and family relationships only
  when supported by evidence;
- canonical firmware identity bound beneath one canonical device identity, covering exact
  model/variant, region, build, version, Android version, security patch, artifact SHA-256 and a
  bounded partition/layout identity;
- evidence observation and retrieval time, freshness/revalidation state, exact artifact digest,
  device/model/firmware/region scope, supporting and contradicting relationships, and immutable
  lifecycle/history status;
- deterministic privacy sanitization for serials, IMEI, account identifiers, usernames, personal
  paths, credentials/authentication material, unrelated logs and personal files;
- storage interfaces only, without a database/filesystem/object-store implementation; and
- explicit backward-compatible loading/migration or fail-closed conservative rejection. Migration
  must preserve every prior confidence/state/authority value and may never strengthen it.

Retail name or similarity may not establish identity. Aliases and family membership do not establish
exact-device equivalence. Two firmware versions, models or regions may not inherit compatibility
from one another. Missing or conflicting consequential facts remain `UNCONFIRMED`.

### Exact Checkpoint 1 ownership

The implementation task may modify only:

- `src/romverse/device/identity.py`
- `src/romverse/rom/source_identity.py`
- `src/romverse/knowledge/online_evidence.py`
- `src/romverse/knowledge/__init__.py`, only for exports of the authorized contracts
- `src/romverse/knowledge/evidence_persistence.py`, new interface-only module
- `tests/test_device_identity.py`
- `tests/test_source_identity.py`
- `tests/test_online_device_evidence.py`
- `tests/test_knowledge_evidence_persistence.py`, new
- `tests/fixtures/device_intelligence/`, new deterministic fixtures only
- `docs/DEVICE-INTELLIGENCE-FOUNDATION.md`, new bounded contract documentation
- `docs/sync/BUILD-STATUS.md`, only for the implementation handoff

No other production, test, fixture, documentation or configuration file is owned by this task.
If an implementation need appears outside this exact list, stop for Product Assurance rather than
expanding ownership.

### Protected and conflicting ownership

`src/romverse/infrastructure/local_store.py` is explicitly protected. The active Windows lines have
independent changes to that shared module. The approved storage abstraction must therefore be a new
protocol/interface in `src/romverse/knowledge/evidence_persistence.py`; it may not modify, wrap,
replace or migrate `local_store.py` in this slice.

Also protected are:

- `src/romverse/device/dna.py`
- `src/romverse/nexus/`
- `src/romverse/rom/first_light.py`
- `src/romverse/intelligence/synapse.py` during Checkpoint 1
- `src/romverse/guardian/` and every Guardian/Recovery execution contract
- all source acquisition/adapters and the completed Knowledge coverage contract
- `src/romverse/infrastructure/`, `pyproject.toml`, packaging, signing and release configuration
- all UI, Windows, Linux and Companion files
- every existing evidence receipt/archive and Device Pack

The primary checkout's pre-existing Companion, Recovery and Windows changes and every other
worktree remain unrelated and must be preserved byte-for-byte.

### Checkpoint 1 verification and acceptance

Add focused deterministic coverage for exact canonical identity, aliases, wrong model, wrong
firmware, wrong region, similar-but-non-identical devices, missing fields, claim-domain authority,
conflicts, stale and duplicate evidence, supersession representation, privacy sanitization,
malformed/corrupt records, legacy loading/migration, `UNCONFIRMED` preservation, zero Guardian or
execution authority, and permanent bootloader no-relock preservation.

Rerun the existing baseline suites for device identity, firmware source identity, online evidence,
Knowledge coverage, Device DNA, Compatibility Matrix, Nexus planning, First Light, Synapse and
Guardian policy. Run focused Ruff check/format and `git diff --check`. No full-suite requirement,
physical-device verification or hosted CI is added by this authorization.

Acceptance requires that legacy schema-one identity/evidence and schema-one/two Device DNA, Matrix
and Nexus records retain their prior meaning; malformed or unsupported schema data fails closed;
all new IDs and digests are deterministic; contradictions remain visible; and every new research
record retains execution authority `none`, phone action `false`, Guardian approval `false` and
bootloader relocking `false`.

Documentation and Checkpoint 1 production-contract changes may ship in one implementation
checkpoint because the work is inert and fixture-driven. Commit and push Forgejo first, verify the
exact remote SHA, mirror that identical SHA to GitHub, update Build Status and stop for independent
Product Assurance review.

### Checkpoint 2 — not yet authorized

After Checkpoint 1 is independently approved, Product Assurance may authorize an additive Synapse
lifecycle checkpoint limited to explicit quarantine, supersession and expiry contracts in
`src/romverse/intelligence/synapse.py`, `tests/test_synapse.py`, the same bounded foundation document
and Build Status. It must preserve Candidate → Verified Success → Strong → Trusted, downgrade and
retirement, hide unusable states from query results, retain them for Archives explanation, and
remain guidance-only. Do not implement Checkpoint 2 under this verdict.

### Absolute exclusions and invariants

This authorization excludes live acquisition, crawling, new external sources, Google Play or Pixel
requests, OEM retrieval, phone/emulator/ADB/Fastboot activity, device writes or transitions,
firmware modification/download/redistribution, ROM build, flash, root, debloat, unlock, any lock or
relock, runtime consumer wiring, compatibility promotion, Guardian/Recovery changes, UI, platform
or Companion work, PostgreSQL/database deployment, object upload, server infrastructure, new
dependencies, hosted CI/Actions, signing, publication and release.

External and firmware-derived information remains evidence, not physical-device verification and
not execution authority. `SUPPORTED`, `CAUTION`, `UNSUPPORTED` and `UNCONFIRMED` remain distinct.
Nexus/Pathfinder/Foresight may reason over evidence, but Guardian remains the only consequential
authorization gate. No source, AI response, Knowledge/Synapse record, adapter or evidence claim may
authorize execution. Bootloader relocking remains permanently prohibited.

### Hard stop

No implementation branch existed at review time. After this authorization is published and both
remotes are verified identical, engineering may create only the named branch from the exact
authorization commit and implement Checkpoint 1. Stop after its one committed, dual-remote handoff
for independent Product Assurance. Do not begin Checkpoint 2 or any broader Device Intelligence
work without a new explicit verdict.

## Reviewed checkpoint: 34584a6 — feature-bound Knowledge coverage and Xiaomi identity

- Ownership/reference: `ROMVERSE DEVICE INTELLIGENCE — FORGEJO-FIRST ENGINEERING HANDOFF`
- Implementation/evidence checkpoint: `34584a6fe1d7a8fb72ce67c481d63af63ce05af0`
- Product Assurance authorization/base: `59ee3ea546092c4b5e9d20f05aec60d43c51f6c1`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — AUTHORIZED ADAPTIVE WORK COMPLETE; SAFE STOP**

### Decision and independent evidence

The checkpoint implements the exact authorized feature-to-data allowlist and uses the existing
fixed Google Play catalog adapter once for only `Xiaomi / 2509FPN0BC / popsicle`. The strict typed
coverage contract maps every approved retained field to one exact claim key, named current ROMVERSE
consumers, and a concrete decision it improves. Unknown fields, mismatched keys, and consumer drift
fail closed. Google Play claim formation now resolves its four authorized identity fields through
that contract.

The single retained result is one exact catalog row: `Xiaomi / Xiaomi 17 Pro Max / 2509FPN0BC /
popsicle`. Product Assurance inspected the sanitized archive and receipt. They retain four exact
official identity claims, source/retrieval/parser provenance, source SHA-256
`24a97f5dca51a62ab44d418219d668674c6e08359618d42322bf50ca15cfd5c3`, archive digest
`9b98671827cf67340877b132e83266732eae8f9bbfbcd963d1e96e1056e77ed4`, and receipt digest
`9c942463404461b86cbdfb32f8dc3c2bd5ff877be31ff294e26c321d62af06b9`.
The raw catalog and nonmatching rows were not retained.

Compatibility remains `UNCONFIRMED`. Every retained record preserves execution authority `none`,
phone action `false`, Guardian approval `false`, and bootloader relocking `false`. No research text
became a command, no compatibility or confirmed-outcome promotion occurred, and no second source,
Pixel query/retry, crawl, phone/emulator, ADB/Fastboot, firmware, build, flash, root, debloat,
Guardian/Recovery, platform, Companion, database/object-storage, hosted CI, signing, publication,
release, or relock work entered the checkpoint.

Product Assurance independently reran the exact focused Knowledge set: **185/185 passed** across
the coverage contract, Google Play acquisition, online evidence, local store, online remediation,
Android guide, Pixel factory-index, and AOSP build-reference regressions. Focused Ruff check and
format check passed, and the authorization-to-checkpoint Git whitespace check passed. The full
suite and live request were not repeated.

### Authorization boundary and next step

The currently authorized adaptive work is complete. Stop this branch at this reviewed checkpoint.
Do not repeat the Google Play request, acquire another source, revise a Pixel adapter, or begin a
broader Device Intelligence foundation slice.

A dedicated Device Intelligence foundation branch is **NOT AUTHORIZED** by the current repository
authority. No approved implementation base commit exists for that branch. This review approves
`34584a6fe1d7a8fb72ce67c481d63af63ce05af0` only as the completed adaptive checkpoint; it must not
be inferred to authorize a new branch or a broader production change. The originating Device
Intelligence task may prepare a separate, exact Product Assurance authorization request identifying
the minimum additive slice, file ownership, exclusions, tests, branch name, and proposed base.
Implementation must wait for an explicit subsequent verdict that authorizes that slice and names
its exact base commit.

## Reviewed checkpoint: fa97ad9 — AOSP build-reference safe stop

- Handoff/receipt commit: `fa97ad987ce5f27f68705915345b9608740fcbc9`
- Implementation commit: `61b09118b8a24ca87c4d9754f73f3cb973d1f8c5`
- Product Assurance authorization/base: `623905ba201bf8263eda33c799c5414ae636b311`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — SAFE STOP; PIXEL CONCENTRATION CLOSED**

### Decision

The AOSP adapter preserves the approved exact-source, bounded-field, privacy, conflict and
zero-authority contracts. Its single live request stopped because the candidate Android-version
field did not satisfy the reviewed syntax. No claim, raw page, command, download, inferred codename,
compatibility or execution authority was retained. Product Assurance independently reran the
complete focused Knowledge set: **181/181 passed**; Ruff and whitespace checks passed.

Do not revise or retry this parser now and do not start another Pixel/Google checkpoint. The two
safe stops are useful source-shape evidence, but further concentration would not advance a current
ROMVERSE feature.

### Required feature-to-data gate

Every future retained field must identify both its current ROMVERSE consumer and the concrete
decision it improves. The allowed current-product coverage is:

- Device DNA: exact public identity, hardware/board components, current firmware/build identity and
  boot/security capabilities.
- Compatibility Matrix and Pathfinder: partition/slot/dynamic layout, boot and AVB topology,
  supported transport/artifact types, prerequisites, incompatibilities and recovery route.
- Guardian and Recovery: exact hazards, irreversible conditions, recovery availability, required
  evidence and known failure outcomes.
- First Light: expected boot, service and hardware-subsystem observations.
- Nexus and Knowledge Archives: provenance, freshness, conflicts, corroboration and exact observed
  outcomes for the fields above.

Marketing copy, reviews, popularity, benchmarks, generic specifications without a consumer,
duplicate facts, bulk page text, personal identifiers and source instructions are outside scope.
Unknown or conflicting facts remain useful as `UNCONFIRMED`; they grant no action authority.

### Approved next bounded task

Add this allowlist as a strict, tested Knowledge coverage contract, then use the existing verified
Google Play public-device catalog acquisition once for the exact connected-device identity
`Xiaomi / 2509FPN0BC / popsicle`. Retain only explicit manufacturer, marketing name, model and
device codename claims that pass exact matching and name Device DNA/Compatibility Matrix as their
consumers. If the source uses a different manufacturer value, lacks the row or is ambiguous, record
one sanitized no-match result and stop; do not loosen matching, retry, choose Pixel, or query an
adjacent device.

This task may record the Samsung `SM-S928B / e3qxxx` table supplied by Steve only as a field-coverage
example pending source provenance; it must not promote it into sourced fact or execution evidence.
Linux owns local firmware-package inspection and Windows owns launcher/process integration, so this
branch must not duplicate or edit either surface.

No crawling, second online source, bulk catalog retention, binary download, UI/background worker,
phone access, build/flash/root/debloat action, compatibility promotion, Guardian approval,
publication, or bootloader relocking. Run focused tests, commit/push the evidence/status, then stop
for Product Assurance.

## Reviewed checkpoint: 81bb3bd — Pixel factory-index stop condition

- Handoff/receipt commit: `81bb3bd506d2128d340b8d434e8222bd52ff2ce7`
- Implementation commit: `977da29c741ef9ca1e0ebd43284e1bf81858d3bd`
- Product Assurance authorization/base: `0e51b025d300b1a2c3f9635501c41942325816ae`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — USEFUL ADAPTER; LIVE SOURCE FAILED CLOSED**

### Decision and independent evidence

The exact-URL Pixel factory-index adapter enforces the approved metadata-only, identity, terms,
download, privacy and zero-authority boundaries. Its single live request returned HTTP 200 but did
not contain one unambiguous reviewed Pixel 6/oriole table in the static response. The authorized
missing-section stop condition fired: no retry, script execution, terms acceptance, link traversal,
binary download, raw-page retention or claim creation occurred. This is the correct result and must
not be weakened merely to extract data from a gated or changed page.

Product Assurance inspected the implementation, sanitized validation-failure receipt and status.
It independently reran the exact focused set: **154/154 passed**; Ruff and whitespace passed. All
compatibility, command, phone, Guardian, execution, download, terms and relock authority remains
false/none. The adapter remains useful for deterministic validation if the canonical source later
exposes the reviewed metadata again, but no live Pixel firmware fact is claimed today.

### Approved next bounded task

Do not revise or retry the factory-image parser now. Apply the value gate to one accessible official
AOSP source that closes the next highest-value portion of the same build-identity gap:
`https://source.android.com/docs/setup/reference/build-numbers`. Query only rows whose explicit
supported-device field includes `Pixel 6`; do not infer `oriole` from this page alone. Retain only
the exact build ID, AOSP tag, Android version, explicit supported-device list and security patch
level, plus page revision/retrieval/content/parser provenance.

Implement one exact-URL canonical-English, metadata-only adapter with strict table headings, row and
byte limits, duplicate/conflict preservation, freshness and sanitized receipt rules. Exclude page
instructions, navigation, code, downloads, unrelated device rows and raw HTML. Add focused tests for
ambiguous/duplicate build IDs, missing supported-device/version/tag/patch fields, changed layout,
localization/query/redirect rejection, stale rows, executable/private text, limits and receipt
tampering. Perform at most one live retrieval after deterministic tests pass. Facts remain official
AOSP build-reference evidence only: they do not prove an OEM package hash, exact codename mapping,
firmware compatibility, a flash route, outcome or Guardian authority.

Update status, commit/push and stop for independent review. Do not add crawling, binary downloads,
UI/background scheduling, phone/emulator access, build/flash/root/debloat work, Guardian approval,
production trust, publication, other product branches or relock.

### Gate status

- Pixel factory-index adapter and safe stop behavior: **VERIFIED**
- Live factory-image metadata: **NOT RETAINED — SOURCE DID NOT PASS REVIEWED SHAPE**
- Next Knowledge milestone: **ONE OFFICIAL AOSP PIXEL 6 BUILD-REFERENCE SOURCE**
- Compatibility, confirmed outcome and consequential authority: **NOT AUTHORIZED**

## Reviewed checkpoint: 438f287 — official Android guide evidence and value gate

- Handoff/evidence commit: `438f28759b76986aa7b178e650f6f3fa07eadd10`
- Implementation commit: `655e4578342f6cc55bccc6b6de9ef3c6786de5ec`
- Product Assurance authorization/base: `7b58c8be04754b9adecbe75d50686ffa8aebdcbb`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — TYPED GUIDE EVIDENCE AND VALUE-GATED PLAN VERIFIED**

### Decision and independent evidence

The checkpoint conservatively extends the existing schema with typed identity, diagnostic, guide,
fix-claim and outcome fields while preserving legacy identity records and their original evidence
state. The fixed canonical Android Developers adapter retains three short, heading-bound connection
guidance claims from one official page. The retained archive contains only eight quoted source
words, typed ROMVERSE-authored descriptions and exact provenance; it contains no raw HTML, code,
script, navigation or source-derived command.

Product Assurance inspected the implementation, strict sanitized live receipt/archive and the new
Knowledge Coverage & Value Gate. The gate maps useful evidence categories to named ROMVERSE
consumers, required fields, source authority, freshness, validation, conflicts, privacy/licensing,
minimum retention, capability benefit and stop conditions. It permanently excludes generic,
duplicative, private, irrelevant or popularity-derived material. Product Assurance independently
reran the exact focused set: **125/125 passed**; Ruff and whitespace checks passed. The branch is
clean.

Each live claim remains `officially-documented`, exact-device/build scope remains unconfirmed, and
all execution, phone, Guardian and relock authority fields remain false/none. This information can
inform investigation but cannot become an action or confirmed fix without independent or exact
observed outcome evidence.

### Approved next bounded task

Apply the new value gate to one high-value official OEM firmware-metadata source: the canonical
Google Pixel factory-image index at `https://developers.google.com/android/images`, queried only
for the already retained `Google / Pixel 6 / oriole` identity. First record the required source
proposal in the Knowledge status: consumers/evidence gap, exact fields, authority, freshness,
parser and limits, conflicts, privacy/licensing/minimum retention, benefit and stop conditions.

If the proposal passes the gate, implement one exact-URL, canonical-English, metadata-only adapter.
Retain only Pixel 6/oriole release/build identifiers, dates, Android-version or carrier/region scope
when explicit, official image URL identity and published SHA-256 values. Do not download image
archives, click/accept terms, retain page bulk, parse instructions into procedures, or infer missing
scope. The source page contains destructive flashing and bootloader-relock guidance: explicitly
exclude all such instructions and add regressions proving that relock text, commands and page
scripts cannot enter claims. ROMVERSE's permanent no-relock policy overrides any source statement.

Classify retained facts as official firmware-index metadata only. They do not prove compatibility,
safe flashing, an installation route, a confirmed outcome or Guardian authority. Add focused tests
for exact identity/build matching, duplicate/ambiguous rows, missing hashes/dates, changed layout,
redirect/localization/query rejection, executable/relock text exclusion, terms boundary, size and
privacy limits, stale/conflicting builds and tampered receipts. Perform at most one bounded live
metadata retrieval after deterministic tests pass; retain only sanitized matching claims and a
receipt. Update status, commit/push and stop for independent review.

Do not add crawling, binary download, UI/background scheduling, phone/emulator access, build/flash/
root/debloat execution, Guardian approval, production trust, publication, Companion/Windows/Linux
changes or bootloader relocking.

### Gate status

- Typed official guidance and legacy migration: **VERIFIED**
- Knowledge Coverage & Value Gate: **VERIFIED AND REQUIRED FOR FUTURE SOURCES**
- Next Knowledge milestone: **ONE PIXEL 6 OFFICIAL FIRMWARE-METADATA SOURCE**
- Compatibility/confirmed-fix promotion and consequential authority: **NOT AUTHORIZED**

## Reviewed checkpoint: 83e6594 — live Google Play identity acquisition

- Live evidence/handoff commit: `83e6594942da04b11163a1bdaa25ae242784bf96`
- Implementation commit: `68a2bf7573b99146ef36b8e127943820d99dd520`
- Product Assurance authorization/base: `f2975629d9decddcd3e0103ca7bb88ab14c41020`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — FIRST REAL OFFICIAL DEVICE-EVIDENCE ACQUISITION VERIFIED**

### Decision and independent evidence

The checkpoint performs real bounded acquisition from exactly the registered Google Play public
supported-device catalog and retains only four query-matched `Google / Pixel 6 / oriole` identity
claims plus a strict acquisition receipt. The 4,753,074-byte response is held in memory, validated,
digested and discarded; no raw CSV or unrelated catalog rows are retained. Exact URL, timeout,
redirect, content-type, compression, row, privacy, conditional-cache and request-spacing boundaries
remain fail closed. Duplicate matching rows and ambiguous identities cannot become claims.

Product Assurance inspected the complete source/test/evidence/status diff and the sanitized retained
records. The claims remain identity evidence only: compatibility is `UNCONFIRMED` and every
execution, phone, Guardian and relock authority field remains false/none. Product Assurance
independently reran the exact focused suite: **100/100 passed**. The branch is clean and Linux,
Windows and protected Companion work were untouched.

### Approved next bounded task

Extend the evidence model only as necessary for typed `diagnostic`, `guide`, `fix-claim` and
`outcome` knowledge. Retain bounded symptoms/error identifiers, prerequisites, affected
device/build scope, non-executable diagnostic or remedy descriptions, expected result,
rollback/recovery route and outcome provenance. Migrate schema one conservatively; existing identity
claims and archive digests must remain readable and must not be silently promoted.

Then add one real source-specific acquisition/parser for the exact official Android Developers page
`https://developer.android.com/studio/run/device`. Acquire only the canonical English page through
the existing registered HTTPS boundary. Extract a small reviewed set of connection-diagnostic
evidence from the official troubleshooting sections, with canonical URL, page revision/last-updated
date when present, content digest, parser identity and bounded supporting excerpts. Retain no raw
HTML, scripts, navigation, code blocks or bulk copyrighted page copy. Record one sanitized live
acquisition receipt and expose the resulting read-only guidance to Knowledge Archives, Device DNA
diagnostics, Nexus and Insight.

Classify this material as `officially-documented` guidance—not a confirmed fix. A source's own claim,
votes or repetition cannot produce `independently-corroborated`, `live-confirmed` or
ROMVERSE-verified status. Those require genuinely independent publishers or an exact-device,
exact-firmware observed outcome. Source descriptions must never become shell/ADB commands,
Guardian authority or automatic actions.

Add focused fixture tests for schema migration, missing/changed headings, malicious HTML,
code/script exclusion, oversized sections, localization/query redirects, stale dates, conflicting
guidance and privacy-unsafe content. Perform one bounded live retrieval only after deterministic
tests pass. Update KNOWLEDGE-RESEARCH-STATUS.md with exact retained evidence and limitations, commit
and push, then stop for Product Assurance before adding another guide, OEM or community source.

Do not interrupt the current Linux/Windows tracks, crawl links, add background scheduling/UI,
execute diagnostics, target a phone, publish source content, enroll trust, flash/root/wipe/relock or
grant consequential authority.

### Gate status

- Real official retail-identity acquisition: **VERIFIED**
- Next Knowledge milestone: **ONE OFFICIAL DIAGNOSTIC/GUIDE SOURCE**
- Confirmed-fix promotion and multi-source ingestion: **NOT YET AUTHORIZED**
- Physical/consequential execution and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 195e4cb — bounded Adaptive Online Device DNA evidence foundation

- Handoff commit: `195e4cb1a5e1e27e31d3c6f7d41967595840b22f`
- Implementation commit: `d4c7d57ea7bc4e5f289973d6558b85b0633d6af3`
- Authorized base: `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`
- Branch: `adaptive-online-device-dna`
- Review status: **APPROVED — BOUNDED ONLINE-EVIDENCE FOUNDATION VERIFIED**

### Decision and independent evidence

The checkpoint supplies the minimum reusable evidence boundary required before ROMVERSE can safely
acquire unfamiliar-device information online. Claims retain exact source, scope, timestamps,
freshness, content digest, parser identity, confidence and explicit conflicts. Storage is bounded,
private and strict; merging is deterministic; unknown and conflicting combinations request further
investigation rather than becoming unsupported or executable. Read-only projections exist for the
named product consumers and permanently carry zero execution, phone, Guardian and relock authority.

Product Assurance inspected the complete six-file implementation/handoff diff, including URL,
redirect, size/content-type, privacy, archive-integrity and authority invariants. Product Assurance
independently reran the exact focused suite: **79/79 passed**. Git whitespace validation passed, the
branch is clean, and the Linux, Windows and protected Companion work were not touched.

### Vision, freeze and safety result

- Evidence-derived unfamiliar-device foundation: **PASS**
- Provenance, conflicts, freshness and privacy boundaries: **PASS**
- `UNCONFIRMED` remains investigable: **PASS**
- Feature-freeze exception: **PASS — approved foundational correctness only**
- Online evidence → command/Guardian authority: **STRUCTURALLY IMPOSSIBLE IN THIS SLICE**
- Exact-device evidence, UNKNOWN/no-blind-retry, consent separation and permanent no-relock:
  **PRESERVED**

### Approved next bounded task

Add one real, source-specific acquisition path for the already registered fixed Google Play public
supported-device catalog URL. Implement a bounded HTTPS client and exact CSV parser that:

- permits only the registry's exact public URL, with no credentials, redirects, authentication,
  cookies, compression, private query fields or alternate hosts;
- uses explicit connect/read/overall timeouts, response-byte and parsed-row limits, minimum request
  spacing, a stable user agent, and conditional `ETag`/`Last-Modified` metadata when supplied;
- validates status and content type before parsing, rejects malformed/duplicate/oversized rows, and
  retains no raw response body after bounded claim formation;
- accepts only an explicit non-personal manufacturer/model/device-codename lookup and stores only
  matching normalized identity claims plus exact provenance/content digest; it must not bulk-promote
  the catalog into compatibility or execution support;
- produces a durable acquisition receipt for success, no exact match, HTTP failure, validation
  failure and cache-not-modified outcomes without converting uncertainty into `UNSUPPORTED`;
- performs one bounded live acquisition against the exact official URL and records only sanitized
  receipt/claim evidence and its content digest; fixture-based tests must remain deterministic and
  must not depend on the network.

Expose the retained claims through the existing read-only Device DNA/Compatibility Matrix/Knowledge
Archives projections. Add focused normal/adversarial tests for redirects, timeout, truncation,
unexpected content, CSV formula/control characters, ambiguous matches and privacy-unsafe lookup
input. Update `docs/sync/KNOWLEDGE-RESEARCH-STATUS.md` with the exact live source URL, retrieval time,
HTTP/cache metadata, content digest, parser identity, number of matched claims and limitations.

Do not add arbitrary crawling, community/OEM sources, UI wiring, background scheduling, device
commands, Guardian approval, physical-phone access, publication, production trust/signing or relock.
Run proportional tests/lint, commit and push the two bounded checkpoints, then stop for Product
Assurance before adding another source.

### Gate status

- Claim/storage/source-registry foundation: **VERIFIED**
- Next Knowledge milestone: **ONE REAL OFFICIAL CATALOG ACQUISITION**
- Multi-source/OEM/community acquisition and UI integration: **DEFERRED**
- Physical/consequential execution and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 0792fa8 — Recipe Forge to durable local build

- Handoff commit: `0792fa8`
- Implementation commit: `b77ee3c03aac1746a8e8f18acd370ddcb3094360`
- Product Assurance authorization/base: `4282da62947dd7e21de56eeb4550a827b468ae87`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — DURABLE LOCAL-BUILD JOURNEY VERIFIED**

### Decision and evidence

The bounded production-widget/service journey proves a useful complete local path: deterministic
Recipe creation and preview, explicit transactional application, durable Recipe evidence, seven-step
inert local build, exact output/receipt verification, and truthful reconstruction after normal
service/UI reload. It is correctly classified as simulated orchestration with no phone or real host
image-building claim.

The discovered restart defect is real and `b77ee3c` is the minimum correction. A durable unsigned
local candidate now remains `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED`; its primary action is
artifact verification, not installation preparation. The installation handoff is selected only
when the separately derived `signing_ready` state is true. Artifact trust, signing/AVB, Guardian,
installation and device execution semantics are unchanged.

Product Assurance inspected the exact two-file source/test diff and handoff. Build's one journey,
**7/7 focused regressions**, Ruff success and whitespace success are proportional evidence. No broad
suite or duplicate interruption/retry campaign is required. The later creator-approved Adaptive
Online Evidence plan at `b7e7a33` is a separate documentation-only commitment and does not alter
this verdict or grant implementation scope.

### Vision, freeze and safety result

- Recipe Forge through durable local-build completion/reload: **PASS**
- Guided completion truthfulness and next-action routing: **PASS**
- Feature freeze: **PASS — first concrete existing-flow correction only**
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**
- Phone, signing, installation, Recovery, publication and release activity: **NONE**

### Approved next bounded task

Run one fresh, no-phone **local candidate to artifact-verification/offline-signing readiness
journey** on Linux using a disposable project, bounded synthetic source and inert host adapters.
Begin from a durable unsigned local candidate and activate the production `Continue to artifact
verification` path. Verify that ROMVERSE rehashes and binds the exact candidate artifacts, inspects
the applicable AVB/signing requirements, and presents either a valid existing offline-signing
request/export route or one precise missing-evidence action. It must not present installation,
Guardian consent or flash readiness as complete, and a reload must preserve the same truthful state.

Record only the first concrete defect and apply only its minimum freeze-safe correction with one
focused regression; if clean, commit evidence only. Reuse current local-build receipts and existing
signing/AVB contract coverage rather than rebuilding the seven-step journey or running a broad
suite. Do not use a phone/emulator, import a real private signature, enroll production trust, build
packages/APKs, touch protected Companion/original-checkout Windows work, begin Guardian/Recovery/
installation, publish, release, force-push or relock. Commit and push, then stop for Product
Assurance.

Windows may separately synchronize only `b77ee3c`, run the one new completed-but-unsigned focused
test plus lint/whitespace, and stop without rebuilding its alpha artifact. Include both this fix and
the already approved neutral Command Deck subtitle naturally in the next normal Windows artifact
batch, not in another immediate packaging cycle.

### Gate status

- Unfamiliar intake and durable local build: **VERIFIED**
- Next core milestone: **ARTIFACT VERIFICATION / OFFLINE-SIGNING READINESS**
- Windows source synchronization of `b77ee3c`: **AUTHORIZED WITHOUT REBUILD**
- Physical device, production signing/trust, installation, Recovery and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 2d27723 — unfamiliar-firmware Guided intake

- Final handoff commit: `2d27723`
- Evidence checkpoint: `41580a949689087618a08fb0930422f45dfeba7d`
- Product Assurance authorization/base: `fc24870124004a250c1bd54b215280fe8c599e74`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EVIDENCE-DERIVED UNFAMILIAR INTAKE VERIFIED**

### Decision and evidence

The bounded journey satisfies the requested Adaptive Discovery foundation milestone. One synthetic
archive with no exact Device Pack/recipe match passed through the production Guided ROM Studio
controls and existing service boundaries: protected import, automatic bounded inspection,
source-derived Device DNA, persisted Compatibility Matrix, isolated working copy, safe tree and an
inert Recipe Forge readiness handoff.

The classification stayed truthful. `guardian_flash` remained Device DNA `UNCONFIRMED` and Matrix
`Unknown`; it did not become `UNSUPPORTED`, known-incompatible or a terminal stop. The UI continued
safe local evidence gathering while displaying `EXECUTION AUTHORITY: NONE`. No known device name,
Pack, live target, consent, signature, execution or hardware result was invented.

No product-source change exists in this checkpoint, and none is required. Build's single
production-widget journey plus **5/5 focused regressions** is proportional evidence; the repository
diff contains only the Build handoff and passes whitespace validation. The evidence is correctly
classified as simulated UI/service behavior, not packaged-app, hardware, build-output or Recovery
verification.

### Vision, freeze and safety result

- Evidence-derived unfamiliar firmware intake: **PASS**
- `UNCONFIRMED` remains investigable rather than unsupported: **PASS**
- Guided next-action clarity through Recipe Forge readiness: **PASS**
- Feature freeze: **PASS — evidence-only checkpoint**
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry and permanent no-relock:
  **PRESERVED**

### Approved next bounded task

Run one fresh, no-phone **Recipe Forge to durable local-build completion journey** using a new
disposable project and bounded synthetic unfamiliar firmware/input tree. Start from the existing
Recipe Forge-ready state, create one minimal deterministic recipe through the real production UI,
preview the exact change, apply it transactionally, run the existing local build path, and verify
the durable result/receipt and reopened project state after one normal application-level restart or
service reload. Stop before signing, Guardian, installation or any device action. The final UI must
distinguish local build completion from install/flash success and offer one clear next action.

Use existing tools only. Record the first concrete defect and implement only its minimum
freeze-safe correction with one focused regression; if clean, commit evidence only. Reuse prior
resume/UNKNOWN evidence rather than retesting interruption cases. Do not run a full suite, rebuild
desktop/Companion packages, use an emulator/phone, touch protected Companion or original-checkout
Windows drafts, download tools, sign, publish, release, force-push or relock. Commit and push, then
stop for Product Assurance.

### Gate status

- Unfamiliar firmware evidence intake: **VERIFIED**
- Next core user milestone: **RECIPE FORGE TO DURABLE LOCAL BUILD**
- Physical device, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 7785a25 — Companion offline acceptance blocker

- Final handoff commit: `7785a25`
- Evidence checkpoint: `ac22e2db430ab603d1b8ee0bc891c70b5ff33889`
- Product Assurance authorization/base: `292cd09131c3b788c88a2ef66041e358c8615494`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EVIDENCE ACCEPTED; UI CORRECTION DEFERRED FOR PROTECTED OVERLAP**

### Decision and independent evidence

The non-rendered offline evidence is sufficient for this bounded pass. Product Assurance inspected
the retained Gradle XML results and confirmed **29/29 passed** with zero skips, failures or errors:
10 Link readiness, 4 navigation and 15 Device Atlas/Knowledge cases. The existing debug APK remains
byte-identical at `9,060,239` bytes and SHA-256
`62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`.

No emulator-rendered claim is accepted: the existing API 35 virtual device exited before ADB
registration and no APK was installed. The production-state checks support only the stated facts:
Home is the safe fallback, disconnected Link does not pretend to be paired, and evidence surfaces
carry zero execution authority.

The identified first-entry defect is valid. Internal-alpha identity is available in About and
authority boundaries exist in deeper surfaces, but neither is concise at the initial Home entry.
The minimum fix belongs in `MainActivity.kt`. Product Assurance independently confirmed that the
original authoritative checkout has protected uncommitted changes in exactly that file, plus the
related navigation source/test. Build correctly made no competing Companion edit. This is a scoped
overlap, not a creator decision and not a reason to stop unrelated product progress.

### Vision, freeze and safety result

- Companion offline state truthfulness: **PASS AT POLICY/JVM LEVEL**
- Rendered first-run journey: **NOT VERIFIED**
- First-entry internal-alpha/no-authority disclosure: **CORRECTION REQUIRED AFTER RECONCILIATION**
- Protected user work preservation: **PASS**
- Feature freeze and Guardian/no-relock invariants: **PRESERVED**
- Physical phone, APK install, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Keep the Companion correction parked until the protected `MainActivity.kt`/navigation work is
reconciled into authoritative history. Continue instead with one fresh, no-phone **unfamiliar
firmware intake journey** on Linux using a new disposable ROM workspace and a bounded synthetic
firmware archive that is not represented by a known device recipe. Drive the real Guided/ROM Studio
presentation from project creation through protected source import, automatic inspection,
evidence-derived Device DNA and Compatibility Matrix/next-action presentation. Verify that
`UNCONFIRMED` permits safe further investigation rather than becoming `UNSUPPORTED`, that no device
or execution authority is invented, and that the user reaches Recipe Forge/readiness or one clear
evidence-gathering action without a dead button or technical loop.

Record only the first concrete defect and apply only its minimum freeze-safe correction with one
focused regression; if the journey is clean, commit an evidence-only handoff. Do not run a full
suite, build/package either desktop app or Companion APK, use an emulator/phone, download tools,
begin Guardian/Recovery/install, sign, publish, release, force-push or relock. Commit and push, then
stop for Product Assurance.

### Gate status

- Companion offline policy baseline: **VERIFIED**
- Companion rendered first entry and disclosure: **WAITING FOR PROTECTED-SOURCE RECONCILIATION**
- Windows and Fedora internal alpha baselines: **VERIFIED; NO REBUILD LOOP**
- Next core product milestone: **EVIDENCE-DERIVED UNFAMILIAR FIRMWARE INTAKE**

## Reviewed checkpoint: 49821cc — refreshed Fedora Guided alpha

- Handoff commit: `49821cc`
- Packaged-run correction: `64ad510532a18b5e26a6feec46791069aee0e8ec`
- Artifact source/authorization base: `b59c3d86a24fdc08d8531ac2414ff6f97b4ee498`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — FEDORA GUIDED ALPHA REFRESH VERIFIED**

### Decision and independent evidence

The refreshed Fedora artifact contains the approved internal-alpha/Guided onboarding correction and
completed one real packaged first-run journey into a truthful no-phone Command Deck. Product
Assurance independently rehashed the canonical ZIP as
`cc9f1c7df7b9147e4a2e8bc1a3ac4b8acb5441ece9fd495854f725322fee9ac0`, confirmed its
`150,947,822`-byte size and mode `0644`, and reran complete ZIP integrity verification successfully.

The journey found one genuine presentation defect: a static subtitle claimed one live device and
one active project while the authoritative cards showed neither. `64ad510` is the minimum correct
repair. It changes only that neutral status text, exposes the label for focused verification and
adds one regression. Build's focused **1/1 passed**, Ruff success and whitespace success are
proportional. Product Assurance also instantiated the corrected production `DeviceCenter` directly
and independently confirmed the false claims are absent.

The exactly-once refreshed ZIP correctly was not rebuilt again. It contains the approved onboarding
correction but predates only the neutral subtitle fix; this limitation is explicit and must remain
visible. The source fix should be synchronized to Windows now and included naturally in the next
cross-platform artifact batch, not trigger another immediate rebuild cycle.

### Vision, freeze and safety result

- Real Fedora packaged first-run Guided/no-phone journey: **PASS**
- Command Deck truthfulness correction: **PASS**
- Feature freeze: **PASS — first concrete presentation defect only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Move to one fresh, no-phone **Companion first-run/offline user journey** using the existing approved
debug Companion baseline. Prefer an already available repository-managed emulator; do not download
or install an emulator/system image merely for this checkpoint. If no runnable emulator is already
available, exercise the production Android presentation/state path through the narrowest existing
local JVM/UI harness. Verify that a new user can identify the internal development build, understand
that Companion has no execution authority, reach Home, and see a truthful disconnected ROMVERSE
Link/device state without a dead action, false pairing/readiness claim or technical loop. Record the
first concrete defect and implement only its minimum freeze-safe correction with one focused
regression; if no defect appears, commit evidence only. Do not run the full Companion suite or
rebuild the APK unless a correction requires one later batched artifact refresh. Commit and push,
then stop for Product Assurance.

Windows is separately authorized to synchronize only `64ad510`, run its one focused subtitle test
plus lint/whitespace and stop without rebuilding. No physical phone, device-scoped ADB/Fastboot,
Recovery, Companion execution authority, signing, publication, release, force-push or relock.

### Gate status

- Fedora v0.2.0-alpha.1 onboarding-corrected development artifact: **VERIFIED**
- Windows v0.2.0-alpha.1 onboarding-corrected development artifact: **VERIFIED at `ab0f299`**
- Neutral Command Deck subtitle in current source: **VERIFIED; PACKAGE AT NEXT BATCH**
- Next user-facing milestone: **COMPANION FIRST-RUN/OFFLINE JOURNEY**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 6c8411c — fresh-user Guided onboarding

- Handoff commit: `6c8411c`
- Implementation commit: `eaa3d615912a4eefddd44ee3b032562047ddadc3`
- Product Assurance authorization/base: `4528cea4cb4331afd78392f41edc91c56a8a57e2`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — GUIDED FIRST-RUN INTENT CORRECTED**

### Decision and evidence

The first-run defect was real and the correction is the minimum truthful fix. The wizard now names
the exact internal alpha, explicitly selects Guided Mode, explains that setup performs no phone
action, and hands that typed selection into the settings saved before Command Deck opens. It does
not grant Guardian, device, build, installation or Recovery authority.

Product Assurance inspected the exact source/test diff and confirmed that only application startup,
the setup wizard and one focused launch/settings regression changed. Build's focused result of
**5/5 passed**, Ruff success and Git whitespace success are accepted as proportional evidence. The
Product Assurance checkout does not contain the project's isolated test dependencies, so no
independent pytest result is claimed. Direct inspection confirms the settings handoff flows through
the existing `launch_settings` persistence boundary and the production-widget journey remains
no-engine/no-device with managed auto-start disabled.

The unchanged Fedora and Windows ZIPs remain valid evidence for the earlier alpha packaging and
no-device startup checkpoints, but they predate this correction and must not be represented as
containing the improved onboarding. Refresh each platform artifact exactly once after synchronizing
this approved source; do not repeat broad suites or unrelated journeys.

### Vision, freeze and safety result

- Guided friction and internal-alpha truthfulness: **PASS**
- Feature freeze: **PASS — minimum first-run intent correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Refresh the Fedora `0.2.0-alpha.1` unsigned development artifact exactly once from this approved
source. Verify its versioned filename, SHA-256/tree and one fresh first-run Guided/no-phone journey
that observes the corrected alpha identity and reaches the truthful Platform Tools or no-device
state. Do not run a full suite or another source correction unless that exact packaged journey finds
a concrete defect. Update the Build handoff, commit and push, then stop for Product Assurance.

In parallel, Windows may synchronize only `eaa3d61` onto the approved Windows branch, run the same
focused launch/settings tests plus lint/whitespace, and refresh its unsigned alpha executable/ZIP
exactly once. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion change,
system installation, signing, publication, release, merge/history rewrite, force-push or relock.

### Gate status

- Fresh-user Guided source journey: **VERIFIED**
- Refreshed Fedora and Windows alpha artifacts containing the correction: **NEXT PLATFORM MILESTONE**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 677dc0b — cross-platform alpha source convergence

- Handoff commit: `677dc0b`
- Linux convergence implementation: `7ea47d24fab13a4df43745dc95954f425ca3a890`
- Approved Windows source: `a5527a04fe4b6183b903b209206b4eab40220f11`
- Product Assurance authorization/base: `87af66065ea679919d603e056d40dce7b6ee07b5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — v0.2.0-alpha.1 SOURCE CONVERGED**

### Decision and evidence

The Linux product-source blob for `toolchain_versions.py` is byte-identical to the approved Windows
source blob (`2676599b64d8c104e35fc69d315988b27d69f94b`). Only the short unpublished staging-name
hunk was imported. Windows ACL assertions, branch history and handoff documents were not copied.

Build's focused Linux result of **22/22 passed**, Ruff success and Git whitespace success are
sufficient. The final digest-bound slot, source-byte verification, private staging, atomic
publication, retained receipt and cleanup behavior remain unchanged. Rebuilding the Fedora or
Windows alpha artifacts solely for this host-temporary path correction would add cost without
material user/runtime evidence and is not required.

### Safety and gate result

- Cross-platform internal-alpha source convergence: **PASS**
- Feature freeze: **PASS — exact approved portability correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, signing, publication and release activity: **NONE**

### Approved next bounded task

Run one fresh ordinary-user **Fedora v0.2.0-alpha.1 first-run/onboarding journey** using the existing
unsigned frozen development artifact and a new disposable workspace. Do not skip onboarding. Verify
that the user can choose Guided mode, understand the internal-alpha/no-device state, reach the
Command Deck, open the existing Platform Tools resolution route if offered, and return to a truthful
ready/no-phone or actionable-host-prerequisite state without a dead button, misleading success or
technical loop.

This is one user-facing acceptance journey, not a broad test campaign. Record the first concrete
onboarding/navigation/readiness defect and implement only its minimum freeze-safe correction with
one focused regression; if no defect appears, commit a truthful evidence-only handoff. Reuse the
current artifact unless a correction makes one source-level rerun necessary; do not rebuild/package
either platform yet. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion
change, signing, publication, release, force-push or relock. Commit and push, then stop for Product
Assurance.

### Gate status

- Fedora and Windows v0.2.0-alpha.1 development artifacts: **VERIFIED**
- Cross-platform alpha source convergence: **VERIFIED**
- Fresh-user Fedora onboarding/readiness: **NEXT USER-FACING MILESTONE**
- Production/public v0.2, physical Recovery and production signing/trust: **NOT AUTHORIZED**

## Reviewed checkpoint: 679b0d8 — Fedora v0.2.0-alpha.1 development build

- Handoff commit: `679b0d8`
- Accepted implementation: `07b5b1721282b2af59abdc8eae0bd152b5361e81`,
  `9e6762aa8cf25b06b64c57486fbe4cd719155d91`
- Product Assurance authorization/base: `817e264cd37e74d0d49b8d627b12b3a523b89cf1`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — FEDORA v0.2.0-alpha.1 DEVELOPMENT ARTIFACT VERIFIED**

### Decision

ROMVERSE now has one coherent internal alpha identity: PEP 440 package/runtime version `0.2.0a1`
and user-facing version `0.2.0-alpha.1`. The visible desktop, Qt metadata and network/update user
agents derive from that authoritative identity. The valid alpha version also passes the corrected
release-order parser and no longer aborts startup.

The single Fedora ZIP is accepted as an unsigned internal development artifact. It is not a signed
release candidate, public release, hardware-verification result or authorization to update an
installed production system.

### Independent repository and artifact evidence

- `07b5b17` changes only authoritative version identity, directly visible desktop identity,
  version-derived user agents, current build guidance and focused bundle tests. `9e6762a` changes
  only the release-version parser and its focused ordering regression. Historical reports, Device
  Pack versions, fixture package/protocol identities, Companion and safety/execution code are
  untouched.
- Numeric PEP 440 `a`, `b` and `rc` stages order before the matching stable version and in their
  expected progression. Existing stable and hyphenated-label formats remain accepted.
- Build's focused result: **42/42 passed**; Ruff and whitespace checks passed. Product Assurance
  independently rehashed the artifact as
  `fb02858c5b8001ab03a8c3015210c74c66c26a00365844a7ab192a02b6116ea9`, confirmed its
  `150947125`-byte size and successfully retested every ZIP member.
- Product Assurance independently reran the frozen application with an empty executable-search path
  and offscreen Qt in a fresh disposable workspace: **startup/no-device smoke passed**.

### Vision, freeze and safety result

- Internal alpha version coherence and truthful development classification: **PASS**
- Fedora runnable artifact and bounded no-device startup: **PASS**
- Feature freeze: **PASS — milestone identity plus directly exposed startup correction only**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification and permanent no-relock: **PRESERVED**
- Phone, Recovery, production trust/signing, publication and release activity: **NONE**

### Approved next bounded task

On `windows-launcher-authorized-work`, synchronize only the approved platform-neutral source/test
commits `3475b45` then `dcd73cc` (durable local-build resume and its exact correction), followed by
`07b5b17` then `9e6762a` (alpha identity and parser correction). Do not copy Linux handoff/assurance
history or merge/rewrite either branch. Resolve only genuine Windows context differences and retain
the already approved Windows launcher and Platform Tools work.

Run the exact focused resume/version/parser regressions on Windows plus lint/whitespace. Then produce
exactly one consolidated unsigned Windows `0.2.0-alpha.1` development build and one matching ZIP,
verify their exact hashes/tree, and run one bounded no-phone startup/no-device smoke. Do not repeat
the full Guided journey or broad suite. Update the Windows Build handoff, commit and push, then stop
for Product Assurance. No phone/emulator target, device-scoped ADB/Fastboot, Recovery, Companion
change, driver/firewall/global PATH change, production signing, publication, release, force-push or
relock.

### Gate status

- Fedora v0.2.0-alpha.1 internal development build: **VERIFIED**
- Windows v0.2.0-alpha.1 consolidated build: **NEXT PLATFORM MILESTONE**
- Cross-platform public v0.2 release: **NOT CLAIMED**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 96edc08 — corrected local-build durable resume

- Handoff commit: `96edc08`
- Correction implementation: `dcd73cca2fdeedc0992c5dd6793a6297eccd76e9`
- Required correction: `54bdefcdfdeafc34578c64c35ee0b7ab83d47e85`
- Original implementation: `3475b45d653ef2ed9ca49802804f385e6c00cdb5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — EXACT LOCAL-BUILD INTERRUPTION/RESUME VERIFIED**

### Decision

Both held findings are corrected exactly. A stop already requested at a durable boundary dispatches
nothing and leaves resumable evidence; a request received during a bounded step still pauses only
after that step is observed and checkpointed. Completed logs now have their own exact path, size,
nanosecond mtime and SHA-256 evidence and must survive the same strict revalidation as outputs.

This closes the demonstrated restart loop without adding blind retry, weakening UNKNOWN or granting
any device authority. Conservative UNKNOWN after an already-recorded intent remains the correct
boundary even when the underlying host command may have reported failure, because ROMVERSE cannot
durably prove which side effects preceded that report.

### Independent repository and acceptance evidence

- `dcd73cc` changes only the local-build executor and its focused contract tests; `96edc08` changes
  only the Build handoff. The correction is an exact descendant of `54bdefc` and Git whitespace
  checks pass.
- The pre-intent callback is checked before checkpoint revalidation, intent recording and dispatch.
  The existing post-step check remains after output/log evidence is durably recorded.
- Attempt parsing and validation require one unique log-evidence entry for every completed-step log.
  Resumption verifies exact containment under the versioned log directory, regular non-symlink file
  type, size, mtime and SHA-256 before any next intent.
- Build's focused correction result: **19/19 passed**. Ruff and whitespace checks passed. The earlier
  accepted 66-case affected result and one production-UI simulated journey are not double-counted.
- Schema-three attempt evidence is corrected in place because it was neither approved nor released;
  final successful local-build receipts remain schema two and versions 1/2 remain read-compatible.

### Vision, freeze and safety result

- Existing Guided workflow and restart recovery: **PASS**
- Evidence integrity and exact-prefix continuation: **PASS**
- UNKNOWN-on-uncertainty and zero blind redispatch: **PASS**
- Feature freeze: **PASS — minimum correctness repair only**
- Guardian-only authority, exact-device evidence, consent separation, same-incident Recovery,
  independent verification and permanent no-relock: **PRESERVED**
- Physical phone, ADB/Fastboot target, Recovery, production trust/signing, publication and release:
  **NONE**

### Approved next bounded task

Begin the creator-approved **v0.2.0-alpha.1 development identity** checkpoint on Linux only. Update
the authoritative package/runtime and visible desktop version identity from `0.1.0`/`v0.1` to the
PEP 440 package version `0.2.0a1` and the user-facing label `0.2.0-alpha.1`. Update only directly
coupled build commands, filename expectations and focused version/readiness tests; do not rewrite
historical reports, Device Pack versions, fixture package versions or unrelated protocol versions.

Produce exactly one unsigned Fedora development artifact from the approved source, verify its exact
versioned filename/hash and one bounded startup/no-device smoke, and record it as an internal alpha
development build—not a signed, published or production release. Do not rerun the full suite or a
duplicate Guided/Recovery journey. Commit and push the platform-neutral identity/source changes and
Linux handoff, then stop for Product Assurance so Windows can synchronize the approved local-resume
and alpha identity changes once and perform one consolidated Windows rebuild.

### Gate status

- Fedora local-build interruption/resume: **VERIFIED**
- Windows synchronization of local-resume correction: **BATCH WITH ALPHA IDENTITY AFTER REVIEW**
- Next milestone: **v0.2.0-alpha.1 INTERNAL DEVELOPMENT BUILD**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: d9f9f9f — local-build durable resume

- Handoff commit: `d9f9f9f`
- Implementation commit: `3475b45d653ef2ed9ca49802804f385e6c00cdb5`
- Product Assurance authorization/base: `9cb181ae3d6359a89569de5278fc816ea0397009`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — RESUME DESIGN ACCEPTED; TWO EXACT BOUNDARY GAPS**

### Decision

The schema-three local-build attempt, exact completed-step prefix, output hashing, retained-toolchain
binding, UNKNOWN/no-retry handling and reopened Forge presentation are the correct minimum repair for
the demonstrated restart loop. The production-UI simulation is useful and honestly non-consequential.

Approval is held for two narrow mismatches between the claimed contract and the implementation. A
stop request that already exists before a new step may still record intent and dispatch that step,
and completed log bytes are not included in the hash-verified checkpoint even though the handoff
claims that they are. Neither issue warrants redesign, schema expansion beyond the proposed
unreleased version three, a broad suite or another full journey.

### Independent repository evidence

- `3475b45` changes only the local-build attempt/executor, durable inventory, background shutdown,
  Forge presentation and focused tests. `d9f9f9f` changes only the Build handoff. Companion, Device
  Engine, Guardian, Recovery, physical transport, signing and release source are untouched.
- Step intent is durably written before `_execute_step`; a caught post-intent result becomes UNKNOWN
  and no later call can redispatch it. Completed output artifacts are bound by relative path, size,
  nanosecond mtime and SHA-256 and are revalidated before continuation.
- The final successful local-build receipt remains schema two. Proposed attempt versions 1/2 remain
  read-compatible and schema three grants no phone or Guardian authority.
- Build's focused result of **66/66 passed**, Ruff success, one final simulated production-UI journey
  and Git whitespace success are accepted as proportional evidence. Product Assurance could not
  rerun the suite from this checkout because its isolated test environment is not present; the
  source, tests and committed evidence were reviewed directly.

### Required minimum correction

1. Before recording a new `step-intent`, check the cooperative stop callback at the current durable
   boundary. If stop is already requested, leave the existing `ready` or `step-complete` checkpoint
   intact, dispatch zero additional adapter calls and report the normal paused/resumable state. Keep
   the existing post-step check so a request received during a running bounded step pauses after that
   step is observed and checkpointed. Add one focused test proving a pre-requested stop performs zero
   runner calls and remains resumable from zero completed steps.
2. Bind every completed step log to the schema-three checkpoint with the same exact path/size/mtime/
   SHA-256 treatment already used for output artifacts, and revalidate it before resume. A changed,
   missing, linked or out-of-bound log must make the checkpoint invalid and dispatch nothing. Add one
   focused tampered-log regression. Because schema three is not approved or released, correct its
   proposed shape in place rather than opening another migration/version family.
3. Update only the affected Build handoff wording and counts, commit the correction, push the same
   branch and stop for Product Assurance. Do not add a discard/retry UI or reinterpret a known local
   command failure; conservative UNKNOWN after any already-recorded intent remains accepted.

### Acceptance criteria

- Pre-requested shutdown at a durable boundary records no new intent and dispatches no step.
- A request arriving during a step still permits only that bounded step to finish and checkpoint,
  then pauses before the next intent.
- Every completed output and log is hash-bound and revalidated; tamper or disappearance fails closed
  with zero resume dispatch.
- Existing exact-prefix resume, no redispatch, UNKNOWN/no-retry, legacy attempt-read compatibility,
  final schema-two receipt, reopened Forge presentation and durable inventory tests remain passing.
- Run only the directly affected focused tests, lint and whitespace checks. No phone, ADB/Fastboot
  target, Recovery, new feature, broad simulation, full suite, signing, publication or relock.

### Approved next bounded task

Apply only the two corrections above and return the exact checkpoint for review. Windows must not
sync `3475b45` until the corrected Linux checkpoint is approved.

### Gate status

- Local-build durable exact-prefix resume architecture: **ACCEPTED**
- Linux interruption/restart checkpoint: **HELD FOR TWO MINIMUM CORRECTIONS**
- Windows synchronization: **WAITING FOR CORRECTED APPROVED LINUX SOURCE**
- v0.2 Golden Foundation: **CLOSED**
- Physical hardware, production Recovery/trust, signing, publication and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 17750ca — simulated AVB / Guardian boundary

- Handoff commit: `17750ca`
- Product implementation: unchanged at `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b`
- Product Assurance authorization: `12b32d5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — STRICT PRE-GUARDIAN BOUNDARY VERIFIED**

### Decision

The production UI correctly accepts exact test-only source AVB identity for simulation while keeping
Guardian handoff and flash readiness false. The missing Device Pack write/readback/transition/AVB/
recovery contracts, independent physical recovery evidence, and operation scope are real safety
requirements—not a Guided defect. No correction or broader synthetic Device Pack is warranted.

### Independent evidence and acceptance

- `17750ca` changes only the Build handoff; no product, test, policy, key, adapter, package, or asset
  source changed.
- The journey derived and reloaded the protected source, build, candidate and AVB evidence through
  production services and one inert adapter; it did not inject a Guardian manifest or completed
  authority state.
- Local candidate and simulation-only signer gates passed; Device Pack flash and physical-validation
  gates remained blocked; Guardian handoff, flash readiness and relock remained false.
- The result is clearly labelled `SIMULATED`, reports zero physical targets,
  `production_execution_authority: none` and `phone_changed: false`.
- Correct strict stop without a speculative fix or repeated suite: **PASS**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification, feature freeze, and permanent no-relock: **PRESERVED**
- Phone/device/Recovery/production-signing/release activity: **NONE**

### Approved next bounded task

Shift to one non-duplicative, offline Fedora **SIMULATED interruption-and-resume journey** for the
existing local-build workflow. In a disposable workspace, use valid sanitized source-derived inputs
and inert adapters to begin a local build, interrupt it at one durable boundary, close/reopen the
production UI, and verify that ROMVERSE reloads only committed evidence, never invents success, and
does not blindly retry an ambiguous or incomplete operation. Resume only when the existing contracts
explicitly permit it from the exact verified checkpoint.

Identify the first concrete user-facing recovery/resume defect and implement only its minimum freeze-
safe correction; rerun only the affected segment and focused test. Do not construct additional
Device Pack execution authority, Guardian consent, Recovery success, physical evidence, or production
signing to force progress. If current behavior is already correct, commit the truthful handoff with no
source change. No phone, ADB/Fastboot target, mode transition, signing, publication, release, or
relock. Commit and push, then stop for Product Assurance.

### Gate status

- Simulated local candidate and AVB verification: **VERIFIED**
- Guardian handoff absent required execution/recovery evidence: **CORRECTLY BLOCKED**
- Local-build interruption/restart truthfulness: **NEXT OFFLINE SLICE**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 44199de — source-derived simulated Forge candidate

- Handoff commit: `44199de`
- Implementation commit: `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b`
- Product Assurance authorization: `68b6902`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — SOURCE-DERIVED LOCAL CANDIDATE PATH VERIFIED**

### Decision

The Forge sequencing correction is sound. Exact input preparation legitimately changes the
source-derived working tree, so freezing that final tree in the same successful background operation
is the correct evidence boundary. It prevents ROMVERSE from rejecting its own newly prepared inputs
while retaining the separate Device Pack execution-plan revalidation before any local build.

The simulated journey produced a reloaded schema-two local-build receipt and byte-verified outputs
without promoting placeholder AVB material into signing, Guardian, Recovery, or execution authority.
That is the correct truthful boundary for this slice.

### Independent evidence and acceptance

- `37e2ee2` changes only `RebuildMetadataWorker` and one focused regression; `44199de` changes only
  the Build handoff. No Device Pack policy, executor contract, Guardian, Recovery, phone transport,
  signing, release, Companion, Windows, or asset source changed.
- The worker refreezes only after `prepare(...)` succeeds and before announcing completion. Existing
  planner hashing and the later exact execution-plan checks remain intact.
- The focused regression recreates the old ordering, adds one source-derived input, runs the worker,
  and proves the new final plan verifies and contains that exact file.
- `git diff --check 68b6902..44199de` passes. Build used one defect reproduction, one corrected
  affected rerun, and one focused test rather than a broad or duplicate suite.
- Simulated local candidate with three verified outputs: **PASS**
- Guardian handoff and flash readiness remain false without valid AVB/signing evidence: **PASS**
- Feature freeze, exact evidence, UNKNOWN, no blind retry, Guardian-only authority, and no-relock:
  **PRESERVED**
- Physical phone/device/Recovery/signing/release activity: **NONE**

### Approved next bounded task

Run one production-UI **SIMULATED** Fedora continuation from the verified local candidate using valid
test-only AVB material and the repository's existing strict, non-consequential adapters. Exercise
candidate AVB verification and the review-only Guardian manifest handoff as far as the current
product truthfully permits. Test keys and placeholder signatures must remain explicitly simulation-
only and must never satisfy production signer, runtime-trust, live-target, consent, Recovery, or
execution authority.

Identify the first concrete user-facing dead end or correctness defect in that existing flow and
implement only its minimum freeze-safe correction. Rerun only the affected segment and focused test.
If the strict product correctly stops before Guardian handoff, record the exact missing evidence
instead of forging a receipt or weakening validation. No real phone, ADB/Fastboot target, physical
mode transition, production key/trust, signing ceremony, Recovery action, publication, release, or
relock. Commit and push the handoff, then stop for Product Assurance.

### Gate status

- Fedora source-derived simulated local candidate: **VERIFIED**
- Simulated AVB and review-only Guardian handoff: **NEXT BOUNDED SLICE**
- v0.2 Golden Foundation: **CLOSED**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 99c961e — simulated Fedora Guided Forge boundary

- Handoff commit: `99c961e`
- Implementation commit: `392b21eb90966b09f089ed9b8f3dac29e5fedf8d`
- Product Assurance authorization: `15092ce`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — GUIDED FORGE PAUSE IS TRUTHFUL**

### Decision

The ordinary-user simulation found one real presentation defect and corrected only that defect.
Genesis now names Forge Control when the local build/sign stage pauses and retains Guardian review
only for the optional phone-install stage. The consequential chain, evidence requirements, and all
authority boundaries are unchanged.

Stopping at missing exact Partition Atlas inputs and verified Fakeroot is the correct result for the
minimal sanitized OTA fixture. The product did not turn incomplete synthetic evidence into a build,
signature, consent, Recovery result, reassessment, or verification claim. No additional work is
required for this exact fixture.

### Independent repository evidence

- `392b21e` changes seven lines in `guided_mission.py` and the exact focused ROM Studio regression;
  `99c961e` changes only the Build handoff.
- The stage ID selects the user-facing review-surface name without changing stage selection,
  readiness, modal ownership, automatic advancement, or live-console authority.
- The focused regression requires `paused at Forge Control` and excludes the stale Guardian label.
- Build recorded one pre-fix discovery run, one post-fix affected rerun, and one focused test pass;
  no broad suite or duplicated milestone was claimed. `git diff --check 15092ce..99c961e` passes.
- The production-UI report remains explicitly `SIMULATED`, records
  `production_execution_authority: none`, and contains no physical target or phone operation.

### Safety and acceptance result

- Correct build-stage surface and no false Guardian direction: **PASS**
- Truthful stop on missing source-derived partition/build evidence: **PASS**
- Feature freeze and existing Guided flow: **PRESERVED**
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN, no blind retry,
  independent verification, and permanent no-relock: **UNCHANGED**
- Phone, ADB/Fastboot target, Recovery, install, flash, signing, publication, release: **NONE**

### Approved next bounded task

Continue one new, non-duplicative Fedora production-UI **SIMULATED** journey from the Forge Control
boundary toward a verified local candidate. Use a disposable workspace and only the smallest
sanitized source-derived partition/image fixtures and injected non-consequential build adapters
already supported by the repository. Do not inject completed internal state, forge receipts, weaken
image/tool/evidence validation, or reuse the 722-byte source to claim progress it cannot support.

Exercise existing Partition Atlas, Fakeroot/toolchain, build-plan, candidate preparation, AVB and
Guardian handoff behavior only as far as valid evidence permits. Identify the first concrete
user-facing dead end or correctness defect after the now-approved Forge pause and implement only its
minimum freeze-safe correction. Rerun only the affected segment and focused tests. If the supported
production services correctly stop on evidence that cannot be represented safely by sanitized
fixtures, record that exact boundary without inventing completion. Label all results `SIMULATED`;
they grant no hardware, production, signing, release, Recovery, or execution authority. Commit and
push the handoff, then stop for Product Assurance.

### Gate status

- Fedora protected-source through Forge Control Guided journey: **SIMULATED AND VERIFIED**
- Source-derived local candidate through Guardian handoff: **NEXT SIMULATED INTEGRATION SLICE**
- v0.2 Golden Foundation: **CLOSED**
- Physical execution, production trust/signing, publication, and release: **NOT AUTHORIZED**

## Reviewed checkpoint: 27538d8

- Handoff commit: `27538d8`
- Product implementation: unchanged at `f61cbc54c203283e457a346bd327a99bec29d880`
- Physical authorization: `c4043b871d7029ffd513bdda33d8e7a1fb5de103`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — LINUX PHYSICAL READ-ONLY DEVICE ENGINE VERIFIED**

### Decision

The bounded real Fedora Device Engine / First Light observation is accepted. The production UI
retained one exact authorized physical USB target, rendered privacy-safe Device DNA truthfully,
kept Guardian and First Light fail-closed, and shut down cleanly. The phone is released and this
authorization is exhausted; no further physical-device action is implied.

The automatic repair-research presentation remained guidance-only, did not block navigation, sent no
raw serial or private evidence, and granted no authority. It is acceptable for this checkpoint. Its
calmness and relevance should be observed during the next ordinary-user simulated journey rather
than opening a separate audit loop.

### Independent evidence

- `27538d8` changes only `docs/sync/BUILD-STATUS.md`; product source, tests, packages, assets,
  Companion, Windows work, and protected unrelated changes are untouched.
- Product Assurance visually inspected the retained Command Deck and ROM Studio captures. They show
  the named phone, `CONNECTED • READ ONLY`, Android 17, the protected-firmware prerequisite, no
  active project, `NOT YET VERIFIED`, and Guardian `NOT YET READY` without a false success state.
- The screenshot and sanitized-JSON SHA-256 values exactly match the handoff:
  `f3968b87acb810cb4bdb340cc616b988f11280360071c0d8e5bb05753bca6f0c`,
  `d120386c0ae344119e93bfec0c771f47760c1b598aedb8fdd950dd5a96215e33`, and
  `43f624c2e8c07fdca292898232f4d2364bf8f0fe1489f3ddb320179d3f772827`.
- Sanitized evidence records one USB target, zero device errors, Guardian unverified, execution
  authority `none`, and First Light `NOT STARTED`.
- A direct byte search found zero raw-serial occurrences in the retained workspace/evidence scope.
- No repeated suite was needed because the unchanged product journey exposed no implementation
  defect. Existing 2,881-test Fedora and focused Companion evidence remains non-double-counted.

### Safety and gate result

- Exact physical USB observation: **PASS**
- Privacy-safe Device DNA and raw-serial exclusion: **PASS**
- Guardian no-authority and First Light fail-closed truthfulness: **PASS**
- ROM Studio protected-original prerequisite: **PASS**
- Phone mutation, APK install, mode change, Recovery/Fastboot, flashing, signing, release, relock:
  **NONE**
- v0.2 Golden Foundation: **CLOSED; physical read-only discovery gap now verified on one device**

### Approved next bounded task

Run one ordinary-user, production-UI **SIMULATED** Fedora ROM Studio journey in a disposable isolated
workspace. Use only sanitized synthetic firmware/Device DNA fixtures and injected non-consequential
ADB/Fastboot/Recovery adapters; no real phone may be connected or targeted. Exercise the existing
flow from project creation and protected-original import through evidence-derived Device DNA,
Matrix/Nexus/Pathfinder presentation, candidate build/preparation, Guardian gating, and inert
Recovery/result presentation as far as the current product truthfully supports.

The purpose is to identify the first concrete user-facing dead end or correctness defect in an
existing pre-v1.0 flow. If one appears, implement only its minimum freeze-safe correction and rerun
only the affected segment. If the product correctly stops at a prerequisite, record that truthful
boundary instead of inventing completion. Label all evidence `SIMULATED`; it grants no hardware,
production, signing, release, or execution claim. Do not run broad suites, repeat accepted journeys,
or create a general architecture/audit task. Commit and push the Build handoff, then stop for
independent Product Assurance review.

## Creator-authorized physical checkpoint: 2026-09-08

- Base checkpoint: `c415391`
- Branch: `linux/stage1-desktop-readiness`
- Authorization status: **APPROVED — ONE CONTROLLED READ-ONLY PHYSICAL ANDROID JOURNEY**

### Decision

Steve connected a phone to the Linux host immediately after Product Assurance requested explicit
authorization for controlled read-only physical Android verification. Read-only preflight observed
exactly one authorized ADB target with explicit `usb:3-1` transport evidence, product/device identity
`popsicle`, and model `2509FPN0BC`. The raw serial is intentionally not recorded here.

This authorizes one bounded real-product Device Engine / First Light observation journey on Linux.
It does not authorize a build, flash, wipe, unlock, reboot, Recovery or Fastboot transition, APK
installation, root action, production trust enrollment, signing, publication, release, or relock.

### Approved next bounded task

Using the existing approved Fedora development build and a fresh isolated workspace, exercise the
production Device Engine / First Light read-only discovery path against the one current physical USB
target. Require one unambiguous authorized target throughout. Capture only product-generated,
privacy-safe evidence for target classification, observable mode/identity, Device DNA/First Light
state, Guardian authority state, and any truthful actionable blocker. Do not persist the raw serial.

Do not issue a state-changing device command, install the Companion APK, enter another device mode,
or manufacture execution readiness. If the target changes, multiplies, disconnects, becomes
unauthorized, or any evidence is uncertain, classify the result as `UNKNOWN` or specifically blocked
and stop. Reuse existing accepted tests; run only a focused check if the journey exposes a concrete
defect. Commit and push the Build handoff, then stop for independent Product Assurance review.

### Acceptance criteria

- Exactly one explicit physical USB target remains unambiguous: **REQUIRED**
- Production UI truthfully identifies the observable target and mode: **REQUIRED**
- First Light / Device DNA evidence is read-only, bounded, and privacy-safe: **REQUIRED**
- Guardian grants no execution authority: **REQUIRED**
- Uncertainty, disconnect, authorization loss, or identity change fails closed: **REQUIRED**
- No APK, reboot, mode transition, flashing, Recovery, trust enrollment, signing, release, or relock:
  **REQUIRED**

## Reviewed checkpoint: 1ecb0d1

- Handoff commit: `1ecb0d1`
- Implementation commit: `f61cbc54c203283e457a346bd327a99bec29d880`
- Product Assurance authorization: `44a3332d975583747e576bfa2967c1bb0bfb0014`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — COMPANION STALE-RESULT INVALIDATION VERIFIED**

### Decision

The minimum Companion correctness repair is accepted. A reset, newer request, or Activity teardown
now invalidates the older pairing generation before that worker can update current presentation,
persist a token, or restore pairing preferences. The direct product Link milestone remains verified,
and its retained evidence count is now stated exactly as 13 observations total / 12 authenticated.

This repair adds no user decision, retry, network authority, execution authority, or feature. It
closes the observed `APPROVAL TIMEOUT • TRY AGAIN` overwrite without repeating the product journey.

### Independent repository and verification evidence

- `f61cbc5` changes only `MainActivity.kt` and one new local unit test. `1ecb0d1` changes only the
  Build handoff. Desktop source, Windows work, protocol, assets, and protected original-checkout
  changes are untouched.
- The synchronized generation gate gives each submitted request one current identity. Reset calls
  invalidate before clearing session state, a newer begin supersedes the older identity, and
  `onDestroy` closes the gate.
- Initial request presentation, polling, telemetry/transfer collection, token-vault persistence,
  paired preferences, late failure, and timeout all require the same current generation. A stale
  worker exits or its main-thread action is rejected.
- The deterministic regression proves stale timeout and stale approval cannot replace reset state or
  restore token/preferences; only the newer attempt can apply; teardown rejects its pending result.
- Product Assurance independently read the generated JUnit XML: the new gate test passed 1/1 and the
  retained Link security tests passed 7/7, with zero failure, error, or skip. Android lint produced no
  blocking error. Git whitespace and remote ancestry are clean.
- Automatic retrieval of SDK Platform 35 revision 2 and Build-Tools 34.0.0 occurred only inside the
  already dedicated removable-data Android toolchain. It did not change repository dependencies,
  Fedora packages, user-wide SDK state, host security, or application behavior. Removing and
  redownloading those valid components would add risk and waste, so no cleanup or follow-up is
  required.

### Safety, freeze, and Guided-friction review

- Certificate pinning, exact safety-code comparison, Companion confirmation, separate Desktop
  approval, remembered-session behavior, revocation, and privacy-filtered telemetry are preserved.
- Link still grants no flash, wipe, root, unlock, relock, Recovery, command, or Guardian authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-device evidence, and permanent no-relock are unchanged.
- No additional dialog, confirmation, route, or technical dead end was introduced.
- The feature freeze is preserved: this is a bounded correctness repair to an existing Link flow.

### Acceptance criteria result

- Stale reset/new-attempt/teardown result rejection: **PASS**
- Stale token/preference restoration prevention: **PASS**
- Focused Android unit and security regression: **8/8 PASS**
- Android compile/lint admission: **PASS; zero blocking lint errors**
- Evidence wording: **CORRECTED — 13 total / 12 authenticated**
- Emulator/full-journey/broad-suite repetition: **NOT PERFORMED; NOT REQUIRED**
- Physical, Recovery, signing, publication, release, or relock action: **NONE**

### Approved next bounded task

Linux stops at this clean approved checkpoint. The remaining emulator-versus-physical-USB
classification defect is assigned to the Windows branch as the single owner because that branch now
contains the completed Desktop listener lifecycle correction in the same source subsystem. Linux must
not duplicate it or begin unrelated work merely to stay busy.

Further Linux Stage-1 product work now crosses a creator-controlled gate: controlled physical Android
verification and production Recovery trust/enrollment remain unauthorized. Product Assurance will
assign a Linux task only after a non-overlapping freeze-safe correction appears or Steve explicitly
authorizes the next physical/production boundary.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone and direct Desktop Link: **VERIFIED**
- Companion stale-result invalidation: **VERIFIED**
- Emulator/physical-USB Desktop classification: **ASSIGNED TO WINDOWS NEXT**
- Windows Device Engine readiness: **listener correction complete; stale OS prompt still requires human dismissal**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: c4bcdfa

- Handoff commit: `c4bcdfa6b46e377c4947b8e5f1a9de52012edd45`
- Product Assurance authorization: `db6fcc14b8fd446ed06e4f31100f17ff0e1b37c8`
- Reviewed implementation: unchanged from `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — DIRECT PRODUCT LINK VERIFIED; MINIMUM PRESENTATION RACE REPAIR**

### Decision

The direct real Fedora Desktop-to-real Companion product Link milestone is accepted. The unchanged
applications completed the production TLS pairing path through both visible identity decisions,
delivered sustained authenticated telemetry, restored one remembered session, revoked it through the
visible Desktop control, and rejected the old credential after Companion restart. No fixture,
instrumentation hook, private-state injection, physical phone, or execution authority participated.

One observed Companion presentation race requires a minimum correction before Linux advances: after
a visible reset invalidated an in-flight request, that older request's eventual timeout overwrote the
current button copy with `APPROVAL TIMEOUT • TRY AGAIN`. The button still opened the correct safety
dialog and no stale credential or authority was restored, so this is not a pairing or Guardian failure.
It is nevertheless untruthful stale UI state and should be fixed in the existing flow.

Product Assurance also corrects two evidence/wording points without rejecting the milestone:

- The retained Desktop event log contains 13 snapshot observations total. The first is the expected
  unauthenticated waiting state and the following **12 are authenticated**, not 13 authenticated
  observations. Twelve still exceeds the required two.
- The Desktop described the sole API-35 emulator as `USB also connected` and later claimed USB
  read-only evidence remained. Repository inspection shows `DeviceEngine` classifies any ADB serial
  without a colon as `usb`, and `CompanionCenter.set_device_snapshot` sets `_usb_ready` for every
  normal `device` snapshot. This is a real connection-source classification defect, not physical-USB
  evidence. Its Desktop source overlaps the active Windows Companion lifecycle slice, so it is queued
  for one coordinated correction after that Windows checkpoint rather than duplicated now.

### Independent repository and runtime evidence

- Commit `c4bcdfa` changes only `docs/sync/BUILD-STATUS.md`; product source, tests, APK, Desktop
  artifacts, protected original-checkout files, and Windows work are unchanged.
- Product Assurance independently inspected the redacted 17-event Desktop log. Its SHA-256 is
  `082aa7090499f3f7ef565b47f86d24177ec68a8f1ee5814c9a06fb26e3c4fcfe`.
  The order is ready, approved, 13 observations, reconnected, reset; every event reports
  `execution_authority: none`.
- Observation one visibly says it is waiting for an authenticated phone snapshot; observations two
  through thirteen contain authenticated health state. No pairing code, bearer token, private key,
  or raw serial is present in the redacted log.
- Product Assurance independently matched the recorded hashes for the paired Desktop, authenticated
  Desktop snapshot, reconnect, reset, Companion safety dialog, paired screen, Live Console,
  remembered reopen, revoked reopen, and Android error log.
- The actual screens show the same certificate-derived code on both products. Companion's Live
  Console visibly retains `Execution authority: NONE` and `Bootloader relock: NEVER`; after revocation
  it requires a new Link code.
- After the run ADB was empty and no emulator, ROMVERSE process, or port-8765 listener remained.
  SELinux stayed enforcing. No physical target, host-security change, dependency install, Recovery,
  signing, publication, or release action occurred.
- Repository inspection localizes the stale Companion copy to the in-flight polling thread in
  `MainActivity.kt`, which unconditionally writes the timeout label after the request is no longer
  approved. The visible reset can complete while that older thread is still pending.

### Vision, Guided friction, freeze, and safety review

- This proves the existing products can pair directly and sustain their intended read-only health
  channel. It is meaningful operability progress, not another fixture or broad-test checkpoint.
- Both identity decisions remain meaningful. Reset and revocation remain effective despite the stale
  label; no hidden approval, retry, or authority path was observed.
- Guardian-only execution, exact-device attribution, consent separation, UNKNOWN-on-uncertainty,
  no blind retry, independent reassessment/verification, and permanent no-relock remain unchanged.
- The feature freeze is preserved. The required change is a correctness repair to an existing
  asynchronous presentation boundary, not a new feature.

### Required minimum correction

Correct only the existing Companion Link request-generation/presentation lifecycle:

1. Give an in-flight Link request a bounded attempt identity, cancellation state, or equivalent
   existing-state check so a visible reset, a newer request, or Activity teardown makes an older
   request unable to update current UI or pairing preferences.
2. A late approval, rejection, network error, or timeout from an invalidated attempt must be ignored
   for presentation and authorization. Do not turn it into a retry, success, or replacement request.
3. Preserve certificate pinning, exact safety-code comparison, explicit confirmation, remembered
   session behavior, reset/revocation, read-only telemetry, and zero execution authority.
4. Add the smallest deterministic affected test proving reset followed by an older timeout cannot
   overwrite the reset/new-request state. Retain current Link assertions; do not weaken timing or
   safety checks.
5. Correct `docs/sync/BUILD-STATUS.md` to say 13 observations total / 12 authenticated.

Expected scope is the minimum relevant Companion Activity source, its directly affected test, and
the handoff wording. Do not change Desktop Companion source in this Linux task while the Windows
listener lifecycle correction is active. Do not rerun the full Fedora journey, broad Python suite,
or unrelated Android inventory.

### Acceptance criteria

- A deterministic focused test proves a reset/new attempt invalidates the old asynchronous
  presentation result and that no stale approval/token/preferences are restored.
- Directly affected Android compile/static/test gates pass. Rebuild only the affected development APK
  if the test requires it; do not repeatedly rebuild artifacts.
- If a bounded emulator check is necessary, use one emulator, reproduce only reset-versus-late-result,
  and shut it down afterward. Do not repeat the entire direct Link milestone.
- `BUILD-STATUS.md` truthfully records 13 total observations and 12 authenticated observations.
- No Desktop source, Windows branch, physical phone, mutating ADB/Fastboot command, Recovery,
  production trust/signing, firewall policy, publication, release, or relock action occurs.
- Commit and push the exact correction/handoff, then stop for independent Product Assurance review.

### Approved next bounded task

Implement only the minimum Companion stale-result invalidation correction above. This keeps the Linux
track on functioning product behavior while Windows independently finishes its already-active Desktop
listener lifecycle correction. The queued emulator-versus-physical-USB classification defect must not
be started by Linux until Product Assurance has reviewed that Windows checkpoint and assigned one
owner.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 runtime: **VERIFIED**
- Contained fixture-backed Companion Link: **VERIFIED**
- Direct Fedora Desktop-to-Companion product Link: **VERIFIED**
- Companion reset-versus-late-result presentation: **MINIMUM CORRECTION REQUIRED**
- Emulator/physical-USB Desktop classification: **QUEUED; SINGLE OWNER AFTER WINDOWS CHECKPOINT**
- Windows optional-listener lifecycle: **SEPARATE ACTIVE CORRECTION**
- v0.2 Golden Foundation: **CLOSED pending remaining Windows, physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: e091a55

- Handoff commit: `e091a555c8ad95d79c4969b6ce77b492d5f7f600`
- Implementation commit: `b86aca25e5cf2078fdcae375812e59f0327d89b5`
- Product Assurance authorization: `a015b2fdd7e7cc2c23cd1ad5f44ed8e8ddcb8f0a`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — CONTAINED COMPANION LINK RUNTIME VERIFIED**

### Decision

The stale instrumentation interaction is corrected without changing the application. The complete
API-35 Companion inventory now passes through the current visible safety-code confirmation, performs
the real ephemeral TLS exchange, observes fresh health state, and reconnects its encrypted remembered
session while retaining zero execution authority.

This closes the contained fixture milestone. It does not claim a physical-phone result or prove that
the two independently runnable ROMVERSE applications can yet pair directly without the fixture. The
next bounded task therefore moves to a real-product integration journey instead of another unit,
packaging, architecture, or broad-regression loop.

### Independent repository and runtime evidence

- The implementation commit changes only
  `companion/app/src/androidTest/kotlin/com/radforge/romverse/companion/MainActivityInstrumentedTest.kt`.
  No production Activity, navigation, transport, Desktop source, dependency, Gradle file, asset, or
  protected original-checkout file changed.
- The test explicitly opens Link, fills the existing endpoint/fingerprint/code fields, proves the old
  checkbox remains disabled and non-clickable, and confirms through the visible accessibility action
  `YES • CODE MATCHES`. It contains no reflection, private hook, preference mutation, or direct-state
  bypass.
- Product Assurance independently read the raw runner log: 12 success status codes, zero failure or
  assumption-skip status, and `OK (12 tests)`. Its SHA-256 is
  `4490e6b7199de0e36c477528823a3083cae4237caba24717bbe269fa2e1a9a45`.
- The fixture log independently shows the exact order `ready → approved → first-health-snapshot →
  complete`, reports `execution_authority: none` at admission and completion, and finishes at
  `OPTIMAL`. Its SHA-256 is
  `9ddcbda1f97f062772239f89cc92a36b9387b7ed21921b8d2701378a95f8072b`.
- Product Assurance independently inspected the captured confirmation frame. It visibly presents the
  exact certificate-derived code, affirmative and decline choices, and the statement that Link grants
  no flash, root, wipe, unlock, relock, or command authority.
- Product Assurance also inspected the captured Live Console and bounded sequence sheet. The UI is
  readable and the sequence shows the unpaired state while the confirmation is present, followed by
  the Link/Console journey. Transient paired/Device-DNA/Ascension pages are supported by passing
  runtime assertions and are not overstated as separately captured frames.
- Product Assurance independently rehashed both artifacts. The unchanged application APK remains
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`; the corrected instrumentation
  APK is `5239d6d7efc4b4ce574cc3c9c84cc62783c8e22bfccee306921108711949df5c`.
  ZIP integrity passed; the instrumentation package targets SDK 35, uses the AndroidJUnitRunner, and
  has one Android Debug signer with a verified v2 signature.
- After the bounded run, ADB was empty and no emulator or Link listener remained. SELinux stayed
  enforcing; no package/environment, firewall, host-security, or physical-device change occurred.

### Guided friction and safety review

- One meaningful identity decision is retained; the retired direct-checkbox shortcut is unusable.
- Companion remains a structured, read-only mission view. Pairing and telemetry confer no Recovery or
  command authority.
- Guardian-only execution, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent reassessment/verification, and permanent no-relock remain intact.
- The short-lived listener's LAN bind/discovery behavior is described honestly. This approval is for
  the previously authorized ephemeral, zero-authority emulator run, not a network-isolation claim.
- The feature freeze is preserved: this is a test correction and runtime proof, not a new feature.

### Approved next bounded task

Prove one direct **real Fedora Desktop application ↔ real Companion application** development journey,
using the existing production Link surfaces rather than `companion_link_emulator_fixture.py`:

1. Use the current approved Fedora development source/application and unchanged approved Companion
   debug APK in isolated temporary workspaces. Do not rebuild or rerun broad suites merely for this
   checkpoint.
2. Launch exactly one clean API-35 emulator with no physical Android target present, then launch the
   real Fedora ROMVERSE Desktop application and open their existing ROMVERSE Link screens.
3. Generate the short-lived code in Desktop, enter the exact endpoint/fingerprint/code in Companion,
   compare the same derived safety code on both visible applications, and exercise every existing
   affirmative/decline decision required by the production flow. Do not bypass either UI or inject
   pairing state.
4. Demonstrate a genuine authenticated paired state and at least two fresh bounded health/mission
   snapshots delivered by the real Desktop transport, with the Companion Live Console remaining
   structured/privacy-filtered and `execution_authority: none`.
5. Restart/reopen the presentation only where the existing product supports it and demonstrate that
   remembered-session reconnection neither duplicates the session nor grants authority. Exercise the
   existing reset/revoke control and prove the old credential no longer reconnects.
6. Capture readable evidence from both applications and retain exact hashes/logs while redacting the
   short-lived pairing code. Shut down Desktop, Companion/emulator, listener, and ADB target at the end.

This is an integration/operability milestone, not authorization to implement or redesign Link. If the
unchanged products cannot complete the journey, preserve the smallest reproducible product blocker,
commit only the evidence/handoff, and stop for Product Assurance. Do not edit application source,
weaken pairing, add a fixture/test hook, install dependencies, connect a phone, merge platform
branches, enable Recovery, sign, publish, or release.

### Acceptance criteria

- Both actual development applications visibly complete the existing pairing journey without the
  fixture or private-state injection.
- Desktop and Companion display the same safety code and retain their meaningful approval boundaries.
- Two fresh authenticated snapshots, structured Live Console state, zero execution authority,
  remembered-session reconnection, and explicit revocation are demonstrated truthfully.
- No physical target, mutating ADB/Fastboot command, Recovery execution, relock, blind retry,
  production trust, or release action occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the bounded checkpoint, and stop for independent
  review. A genuine failure stops the run; do not loop or silently change source.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 runtime: **VERIFIED**
- Contained fixture-backed Companion Link: **VERIFIED**
- Direct Fedora Desktop-to-Companion product Link: **NEXT BOUNDED MILESTONE**
- Windows runnable development readiness: separate one-test portability correction in progress
- v0.2 Golden Foundation: **CLOSED pending remaining Windows, physical, production, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 1e0d4fe

- Handoff commit: `1e0d4fec65d9b2affc4174e8b40e5a6865187df3`
- Prior Product Assurance authorization:
  `1bc798bbca7a0f6a88dfa2514a25f130245c3d33`
- Title: `Record contained Link instrumentation failure`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **CORRECTION REQUIRED — STALE TEST INTERACTION; APPLICATION SAFETY FLOW RETAINED**

### Decision

The environment correction worked exactly: clean-worktree ROMVERSE source and the existing verified
dependency environment were separated correctly, the exact emulator and APK admission passed, and
the committed fixture reached a genuine TLS-ready state with `execution_authority: none`.

The remaining failure is independently localized to an outdated instrumentation interaction. The
test still searches for and directly checks a checkbox whose text begins
`I confirmed the Link safety code`. The current application intentionally no longer exposes that
bypass. Its internal confirmation checkbox is disabled and the real user journey requires the
visible `CONFIRM DESKTOP IDENTITY` dialog and affirmative `YES • CODE MATCHES` action.

The application behavior is the safer and authoritative contract. Do not weaken or alter it. The
minimum correction is confined to the existing Link instrumentation test so it navigates through
and asserts the current meaningful safety confirmation before pairing.

### Independent evidence

- Commit `1e0d4fe` changes only `docs/sync/BUILD-STATUS.md`; the worktree is clean and matches the
  remote branch.
- The fixture log hash and runner log hash independently match the handoff:
  `07d6cbdb23d72d8b22e98841a9afcd579e81016ac742eb1d142dfc95b0d19632` and
  `ca19e7914c5ef971c1080697c6f62aa132e513e7e307370fc80d78f1c8fae7bd`.
- The raw runner records 11 success completions, one failure, zero assumption skips, and
  `FAILURES!!!` for 12 tests.
- The one failure is a `NoSuchElementException` inside
  `tlsPinnedLinkCarriesLiveConsoleAndReconnectsAfterRecreation`, before any pairing request.
- The committed test directly searches for the retired checkbox text and sets `isChecked = true`.
- The committed application instead renders `Safety code confirmation is waiting`, keeps the
  checkbox disabled/non-clickable, and exposes a dialog containing the derived safety code, an
  explicit no-device-command explanation, a decline action, and `YES • CODE MATCHES`.
- The three pairing inputs and the Link route remain present; no evidence supports an application
  navigation or TLS defect at this boundary.

### Fixture containment classification

The fixture uses the production local-network transport, which binds a short-lived TLS listener to
all local interfaces and emits the existing discovery broadcast. It is therefore contained by
ephemeral identity, short-lived code, explicit approval, bounded duration, and zero execution
authority—not by a private network namespace or loopback-only bind.

That behavior must be described honestly. It does not require a production transport change in
this correction: no external request was observed, no reusable token existed, the unapproved
fixture accepted no telemetry, and the process/listener closed immediately after failure. The next
run must retain the same brief bounded lifetime, never expose its code externally, and verify no
unexpected request appears before the explicit in-emulator confirmation.

### Required minimum correction

Modify only
`companion/app/src/androidTest/kotlin/com/radforge/romverse/companion/MainActivityInstrumentedTest.kt`
within the clean Linux worktree:

1. In the existing TLS-pinned Link test, explicitly open the existing Link destination before
   interacting with its fields.
2. Populate only the fixture endpoint, certificate fingerprint, and six-digit pairing code.
3. Remove the stale direct-checkbox mutation.
4. Activate the existing `CONNECT WIRELESSLY` action and require the real confirmation dialog.
5. Assert the displayed safety code exactly matches the code derived from the supplied certificate
   fingerprint and assert the dialog retains its read-only/no-command authority explanation.
6. Select `YES • CODE MATCHES` through the visible/accessibility UI surface. Do not use reflection,
   private-field access, test-only application hooks, preference mutation, or another bypass.
7. Confirm the fixture receives no pairing request before that explicit affirmative action.
8. Preserve all existing post-pairing assertions: TLS pin, two fresh health snapshots, encrypted
   remembered-session storage/reconnection, schema-six Live Console, Device DNA, Ascension,
   `Execution authority: NONE`, and permanent bootloader-relock prohibition.

Do not modify `MainActivity.kt`, navigation, production transport, fixture behavior, protocol,
dependencies, Gradle configuration, or any protected original-checkout file. This is a correctness
repair to stale test interaction only, not a feature change.

### Acceptance criteria

- The exact test-source diff is limited to the interaction/assertion changes above.
- The instrumentation APK is rebuilt from the unchanged approved application source; its new hash,
  package/target/runner identities, debug signer and certificate are recorded and independently
  verified. The application APK must remain byte-identical at its approved hash.
- Relevant compile/static gates pass without weakening or removing an assertion.
- One clean API-35 host-GPU runtime uses the same exact-target, SELinux-enforcing, verified Python
  environment, ephemeral fixture, and artifact admission boundaries.
- The complete 12-test suite passes 12/12 with zero failure and zero skip.
- The fixture emits `ready`, then no request before explicit visible confirmation, then `approved`,
  two fresh health snapshots, and `complete`, always with `execution_authority: none`.
- Bounded readable evidence shows the paired Link state and current confirmation path; Live Console,
  Device DNA, and Ascension evidence remain truthful.
- Fixture and emulator are shut down; ADB is empty; no unexpected client or listener remains.

Any failure ends the task without another source change or retry.

### Approved next bounded task

Implement only the minimum test correction above, rebuild only what is required for the debug
instrumentation artifact, and perform its one exact contained integration run. Update
`docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, then stop for independent Product Assurance review.

No physical phone, application behavior change, production Recovery, production trust/signing,
platform merge, publication, or release is authorized.

### Gate status

- v0.2 Golden Foundation: **CLOSED pending remaining release gates**
- Fedora runnable build and inert Guided journey: **VERIFIED**
- Companion standalone API-35 emulator runtime: **VERIFIED**
- Contained Desktop/Companion Link integration: **MINIMUM TEST CORRECTION REQUIRED**
- Windows runnable development build: separate correction track in progress
- Physical hardware, production Recovery, signing, publication, and release: not authorized
