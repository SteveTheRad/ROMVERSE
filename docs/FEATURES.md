# ROMVERSE Features

## Status discipline

A feature may be Planned, Confirmed Commitment, In Progress, Implemented, or Implemented and Verified.

**Implemented and Verified** requires repository inspection plus proportionate build, test, fixture, or runtime evidence. Documentation must never imply implementation merely because a feature has been approved or designed.

## Core workflows

### ROM Studio
Primary firmware inspection, modification, build, and validation workspace.

### Genesis Sequence
Beginner-friendly end-to-end guided ROM workflow.

### Recipe Forger
Reusable guided modification recipes.

### Ascension Protocol
Optional root path selected during Genesis Sequence and skipped when root is declined.

### Guardian Readiness and Guardian Flash
Evidence-backed readiness validation followed by controlled flashing with explicit user authority.

## Firmware pipeline capabilities

- Detect supported `payload.bin` packages.
- Detect fastboot archives.
- Detect extracted firmware folders.
- Detect partitions/filesystems.
- Select the appropriate tools and extraction/build path automatically.
- Show genuine progress, current stage, explanations, warnings, and recovery options during long operations.
- Offer a local-drive backup before flashing.
- Present explicit dirty-flash/preserve-data and clean-flash/wipe-data choices after readiness is all-green.
- Scan real firmware apps for debloat and classify them as Safe, Caution, or Protected using OEM/device-specific evidence.

## Intelligence systems

### Device DNA
Authoritative evidence-backed device and firmware profile.

### Capability Map
Uses exactly these states:
- SUPPORTED
- CAUTION
- UNSUPPORTED
- UNCONFIRMED

### Compatibility Matrix
Tracks evidence about what works on a specific device/firmware combination.

### Foresight
Predicts dependencies and impact before execution.

### ROMVERSE Nexus
Coordinates goal understanding, research, planning, Guardian review, execution/adaptation, and verification.

### Pathfinder
Finds the best evidence-backed route and powers the visual Route Map.

### Guardian
Safety, authorization, readiness, and evidence gate.

### Insight
Why explanations, evidence, confidence, and decision history.

### Synapse
Shared server-side verified-solution knowledge system with evidence maturation and retirement.

## Companion features

- ROMVERSE Link
- Pulse
- Vitalis
- Lifeline
- Live Console
- Community/Account surfaces
- Device/Nexus/Guardian/Tools navigation

## Recovery and continuity

ROMVERSE should preserve projects, source firmware, backups, configuration, and user data by default. Recovery preparation and PC handoff are first-class requirements rather than afterthoughts.

## Product/platform notes

The normal application startup should prioritize responsiveness and should not block on decorative branding sequences. Approved brand/cinematic assets may be used in non-blocking contexts such as installers, About/credits, website, promotional materials, trailers, and end cards.

The official Facebook Page should be surfaced in appropriate About/Community surfaces when those areas exist.

## Feature documentation rule

When a feature is added, removed, renamed, superseded, or materially changed, this file and any affected architecture/UX/Guardian/roadmap documentation should be updated in the same development cycle.
