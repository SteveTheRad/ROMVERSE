# ROMVERSE Architecture

## Architectural goal

ROMVERSE should separate detection, evidence, planning, safety authorization, execution, verification, and presentation so that no UI surface or subsystem independently guesses device facts or bypasses safety gates.

## Core architecture

### Firmware and device pipeline

Current M1 direction:

Firmware Import → Automatic Detection → Device Identification → Device DNA → Capability Map → Tool Resolution → Workspace Creation

The broader functional chain then continues through extraction, modification/debloat, build validation, Guardian Readiness, local backup, and controlled Guardian Flash.

### Device DNA

Device DNA is the authoritative evidence-backed device/firmware profile. It should hold trusted findings such as retail identity, model, codename, SoC/platform, Android/ROM/build/region data, firmware format, partition architecture, A/B state, filesystems, bootloader/slot information where obtainable, root/encryption/Verified Boot state where safely identifiable, partition sizes, fastboot/recovery capabilities, compatibility warnings, evidence sources, and confidence.

Consumers must read the authoritative profile instead of independently inferring the same facts.

Capability Map states are exactly:

- SUPPORTED
- CAUTION
- UNSUPPORTED
- UNCONFIRMED

Unknown information must remain explicitly UNCONFIRMED.

### ROMVERSE Nexus

Nexus is the central goal-to-plan orchestration layer.

Mission flow:

Nexus Mission → Understand → Research → Nexus Plan → Guardian Review → Execute/Adapt → Nexus Verification

Nexus coordinates evidence and route selection rather than replacing the specialized systems beneath it.

### Pathfinder

Pathfinder finds the best evidence-backed route for a requested goal and powers the visual Route Map.

### Foresight

Foresight predicts dependencies, risks, and likely change impact before execution.

### Guardian

Guardian is the safety, authorization, readiness, and evidence gate. Guardian consumes Device DNA and other evidence but remains the subsystem responsible for deciding whether an operation may proceed.

### Insight

Insight provides lightweight explainability and decision trace information, including Why explanations, evidence, confidence, and history.

### Synapse

Synapse is the shared server-side verified-solution knowledge system.

Unknown issue flow:

sanitized fingerprint → Synapse Query → Nexus/Pathfinder investigation → Guardian-approved fix → execution → Nexus Verification → sanitized Synapse Contribution

Evidence maturity:

Candidate → Verified Success → Corroborated/Strong → Trusted

Evidence may be downgraded or retired when failures or firmware changes invalidate it.

### AI Gateway

ROMVERSE uses a provider-independent AI Gateway. The initial preferred primary reasoning provider is OpenAI, while the architecture should allow alternate providers for capability, cost, redundancy, outages, or independent corroboration.

The AI Usage Governor should prioritize deterministic/local code, cached knowledge, Synapse, and the Compatibility Matrix before paid AI.

### Companion

The Android Companion is a first-class half of ROMVERSE.

Primary mobile direction:

Home → Device → Nexus → Guardian → Tools → Community/Account

Key Companion systems:

- ROMVERSE Link — secure persistent PC/Companion connection.
- Pulse — telemetry, history, pre/post-change comparison, Nexus Verification evidence.
- Vitalis — interactive diagnostics and health.
- Lifeline — Companion recovery/rescue interface with PC handoff when Android cannot operate.
- Live Console — real execution progress, route, events, Guardian/Pathfinder/Foresight states, warnings, technical output, graphs, gauges, and terminal data carried from real PC execution.

## Infrastructure direction

Initial infrastructure direction is one primary rented server/VPS containing separate services/containers for website, community/forum, accounts/subscriptions, ROMVERSE API/backend, Synapse, database/cache, and monitoring/admin. Large installers, Companion APKs, updates, and assets should use object storage/CDN. Backups should be automated and stored off-server.

## Performance rules

Performance is architectural, not cosmetic. Prefer progressive/event-driven analysis, caching, responsive UI, bounded background work, and measurable startup/RAM/network/processing targets.

## Portability rule

Architecture-relevant assumptions, dependencies, service boundaries, configuration requirements, and setup steps must be documented in-repository so the project can move between development machines safely.
