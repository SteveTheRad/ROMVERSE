# ROMVERSE Guardian

## Purpose

Guardian is ROMVERSE's safety, authorization, readiness, and evidence gate. It must not be bypassed merely to reduce friction, cost, or development time.

## Non-negotiable rules

- Never relock a bootloader.
- Destructive device operations require an informed user choice at the point of action.
- Preserve projects, source firmware, backups, configuration, and user data by default.
- Automatically apply only genuinely safe, verified fixes.
- Require explicit authority when elevated privilege, data loss, rooting, unlocking, flashing, or another meaningful user choice is involved.
- Never present uncertain evidence as certain.
- Unknown Device DNA information remains UNCONFIRMED.
- Never upload raw personal data; sanitize serials, account identifiers, usernames in paths, and unnecessary logs.
- Guardian safety cannot be weakened to reduce AI usage or infrastructure cost.

## Evidence inputs

Guardian may consume evidence from:

- Device DNA
- Capability Map
- Compatibility Matrix
- Foresight
- Pathfinder
- build/extraction validation
- device state
- backup readiness
- test/fixture/runtime evidence
- Synapse confidence where applicable

These systems provide evidence. Guardian remains responsible for authorization and readiness decisions.

## Readiness model

Guardian Readiness should aggregate the actual evidence required before a controlled flash or other high-impact operation. Final readiness must be represented as an explicit all-green state only when every required condition genuinely passes.

## User authorization

Meaningful choices must be explained in understandable language. The UI must distinguish safe automated work from actions that require the user to authorize consequences.

Before flashing, ROMVERSE should offer a local-drive backup. Once readiness is satisfied, users should receive clear explanations of preserve-data/dirty-flash and wipe-data/clean-flash paths when both are valid.

## Verification

Guardian-approved execution is not the end of a workflow. Nexus Verification and appropriate post-operation evidence should confirm the actual result.

## Development rule

Any new subsystem that can modify firmware, devices, boot state, partitions, user data, recovery state, or security-sensitive configuration must define how Guardian participates before the feature may be considered production-ready.
