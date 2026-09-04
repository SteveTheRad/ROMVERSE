# ROMVERSE architecture

## Dependency direction

```text
PySide6 UI → application services → domain models/policies
                         ↓
              infrastructure adapters
              (ADB, filesystem, platform)
```

`domain` has no Qt or subprocess dependency. `guardian` owns policy; `infrastructure`
owns effects. `device` coordinates read-only probes. `ui` observes services and renders
state. Future features should enter as bounded packages (`companion`, `galaxy`, `rom`,
`repair`, `recipes`, `lab`, `licensing`, `device_packs`) rather than expanding `app.py`.

## Repository map

```text
src/romverse/
  app.py                 composition root / CLI
  core/                  settings and workspace rules
  platform/              OS abstraction
  guardian/              policy, execution gateway, tamper-evident audit
  infrastructure/        subprocess and tool verification
  device/                ADB adapter, parsers, models, engine
  nexus/                 Device DNA compatibility, plans, routes, foresight, insight, event ledger
  intelligence/          online remediation, Synapse evidence, AI Gateway and Usage Governor
  diagnostics/           evidence, findings, analysis, redacted history
  knowledge/             offline repair brain, provenance store, deterministic evidence ranking
  device_packs/          validated multi-OEM metadata and matching
  repair/                guided assessment plus typed, receipt-bound safe repair services
  rom/                   provenance, payload/filesystem services, Recipes, build gates
  ui/                    PySide6 shell, setup wizard, Device Portal, theme
  assets/                scalable brand assets
tests/                    hardware-free unit tests
docs/                     product and engineering specifications
scripts/                  Linux and Windows environment bootstrap
```

## Extension contracts

- Replace `CommandRunner` to test or sandbox process behavior.
- Add platform adapters without OS conditionals in UI/domain code.
- Extend Guardian through typed operations and policy rules, never raw command strings from UI.
- Bind every enabled mutation to immutable evidence, a privacy-safe target, explicit approval,
  pre-execution revalidation, a bounded argument vector, and a post-operation receipt.
- Treat the Guardian runtime as a separately released artifact. Before deriving runtime trust,
  require a pinned Ed25519 release identity over a strict manifest that binds the executable hash,
  platform, protocol/result schemas, adapter and runtime public key; rehash the local regular file,
  reject links and all authority-widening policy claims, and never execute or enroll it as a side
  effect of package verification.
- Store approvals in a separate SHA-256 chain, expire new approvals after ten minutes, and treat
  readable legacy entries as audit-only rather than reusable authority.
- Add OEM knowledge through versioned Device Pack providers returning generic facts and checks.
- Publish Device Engine snapshots to later diagnostics, Companion, and Galaxy integrations.
- Treat Device DNA as the authoritative project evidence profile; Compatibility Matrix and Nexus
  plans must bind its digest and become invalid when the source evidence changes.
- Derive the Firmware Upgrade Passport from the same bounded relationship engine used by Device DNA,
  bind it to the current protected source and live device, and recompute it inside Forge readiness.
  Relationship classification must stay separate from installation authority: same and downgrade
  are never labelled upgrades and need an exact alternate-route contract; incompatible and rejected
  metadata stay blocked; unknown states remain Attention; and a distribution-channel change is
  reviewed against the exact Device Pack contract rather than physical country.
- Persist Device DNA through a bounded private atomic schema-two contract with exact top-level and
  nested shapes, typed enums, bounded collections, valid evidence cross-references, source binding,
  and an invariant UNSUPPORTED bootloader-relock capability. Consume structure facts only from the
  current stored schema-two inspection report or Forge's strict current project/source-bound local
  blueprint; direct caller objects are not evidence. The blueprint may reconcile identity,
  adapters, tools, partition inventory and bounded build preparation, but its local-evidence-only
  authority never permits a device write or flash.
- Re-derive every persisted Compatibility Matrix decision from the exact current Device DNA profile
  and stored assessment time on load. A record digest alone is insufficient; strict schema-two
  storage, immutable safety/telemetry flags, and deterministic equality are all required.
- Persist Nexus Plans and ROM DNA as bounded private schema-two evidence. Re-derive the entire Nexus
  route from current Device DNA/Matrix on load, and compare ROM DNA with the current project,
  protected source, build-tree plan, and Recipe provenance before returning either record.
- Keep Nexus coordination separate from execution. Pathfinder, Foresight, and Insight may explain
  and plan, but only typed services behind Guardian may perform an approved effect.
- Feed Live Console only from genuine producer events. A progress estimate, planned stage, or timer
  can never be recorded as a successful outcome.
- Route byte-addressable worker updates through the shared coalescing relay before Qt delivery.
  Publish at most one event for each new integer percentage, clamp it to 0-100, and reject late
  backwards updates so large copies, hashes, scans, and downloads cannot starve the UI event loop.
- Resolve connected intelligence through deterministic evidence, Synapse, verified cache, and the
  Compatibility Matrix before AI. Provider output stays guidance-only and passes through Guardian.
- Query the strict local Knowledge Archives after every successful Device DNA capture and from typed
  boot/flash failure producers. Rank exact error, finding, build, codename, model, and partition
  evidence ahead of broad family text; expose provenance, scope, corroboration, confidence,
  incompatibility, and missing evidence in every result. Community-reported successful outcomes are
  usable scoped evidence even when the count is one, but Archives never receives execution authority.
- Treat every Synapse Contribution Passport as an exact-byte, content-digested, private review
  artifact. Re-scrub summaries, allow only bounded aggregate scope/outcome fields, reject extra or
  altered fields, and keep upload, execution, and phone authority false until a separate production
  service and consent ceremony are implemented.
- Keep provider credentials server-side. Desktop and Companion must never request or persist a
  member's third-party AI key.
- Store projects and history as versioned manifests so migrations are explicit.
- Seal project manifests and working-copy records with strict schema-two digests in private atomic
  files. Bound project enumeration, reject symbolic-link directories and artifact paths, detect a
  changing source during protected-original import, and preserve schema-one readability without
  treating unverified legacy metadata as current evidence.
- Treat structure inspection as source-bound evidence rather than trusted cache. Persist strict
  schema-two digested reports through bounded private atomic storage, refresh legacy/rejected
  reports from the verified original before extraction, hold source identity stable across the
  operation, and create the contained tree under private non-linked directories only.
- Persist local guidance/evidence through byte-bounded, strict-schema, private atomic stores. Anchor
  paths beneath the resolved workspace, reject symlink/reparse and non-regular targets, bound file
  enumeration, and never derive a local filename or typed action from provider-controlled text.
- Promote connected remediation only through a schema-two verified outcome that binds the exact
  persisted fingerprint candidate to an allowlisted action and a format-specific local evidence
  reference. Revalidate that source receipt on every load; a digest-shaped value alone is not proof.
- Keep large firmware hashing and extraction off the Qt UI thread; UI refreshes consume small
  saved manifests and never re-hash multi-gigabyte trees or Time Machine images implicitly.
- Re-activate only receipt-verified managed executables before an automatic Forge tool decision.
  Skip setup when the exact scoped inventory is complete, and make an empty auto-close setup a
  successful no-op so nested UI cannot strand Autopilot.
- Treat an exact-source Device Pack draft as a development handoff only. Bind it to the revalidated
  project source, blueprint/plan digests, matching phone identity, partition count, tool list, and
  explicit missing flash contracts. When a current strict source-AVB receipt exists, carry its OEM
  algorithm, public-key fingerprint, true chain partitions and other descriptor partitions as
  evidence without treating them as an AVB execution policy; reject the draft from the production
  Pack registry and keep public, execution, and phone-action authority false.
- Apply the bounded evidence-store contract at the producer as well as the consumer. OTA/fastboot
  blueprints, local-build/super receipts, and AVB topology must reject hostile files and exact-shape
  violations before domain construction. Use saved size/mtime identity for bounded routine reloads;
  reserve full content hashing for the existing background build/sign/handoff verification gates.
- Bind offline signing imports to the exact exported manifest and flash-validated Pack policy.
  Store requests and receipts through the same bounded private atomic contract, reject symlinked
  records, artifacts, and intermediate evidence directories, and fully verify legacy evidence
  before migrating it to a bounded routine-reload schema.
- Keep Time Machine hashes separate from private absolute locators. Bind both bounded atomic records
  to the exact project, protected source, roles, and metadata; reject workspace redirection and let
  legacy recovery evidence inform the user only until a full rehash upgrades it.
- Keep local snapshot listing and rollback planning bounded: validate schema-two record digest,
  project path, size, and mtime without an implicit content hash. Run the mandatory artifact hash,
  safety-snapshot binding, atomic replacement, and postcondition hash in the managed worker before
  a local restore. A legacy snapshot cannot satisfy readiness until that worker verifies it.
- Treat “workspace ready,” “build ready,” “signed,” and “flash ready” as independent states.
  A simulation receipt proves only gate behavior and never stands in for a build/flash receipt.
