# ROMVERSE Versioning and Releases

## Purpose

This file defines the release discipline and should also become the maintained private release history for ROMVERSE.

## Versioning direction

Use semantic-style versioning unless a later explicit project decision supersedes it:

`MAJOR.MINOR.PATCH`

- MAJOR — incompatible product/architecture changes or a major public generation.
- MINOR — backward-compatible feature milestones.
- PATCH — backward-compatible fixes and maintenance.

Pre-release identifiers may be used for internal, closed beta, public beta, release-candidate, or other pre-production builds where useful.

## Release stages

Current product progression:

closed beta → public beta → commercial launch

Guardian validation is required before commercial release readiness.

## Release preparation

Before a release is considered ready, verify as appropriate:

- Repository is clean and expected changes are committed.
- Target version is recorded consistently.
- Relevant build/test/lint/static-analysis checks pass.
- Critical firmware/device workflows have proportionate verification evidence.
- Guardian safety paths are tested for the affected scope.
- Migration/backward-compatibility concerns are reviewed.
- Required release notes are written.
- Documentation reflects the shipped behavior.
- Known issues and limitations are explicit.
- No secrets or sensitive local files are included in source or artifacts.
- Release artifacts are produced by a documented/reproducible process where practical.

## Branch flow

Normal development integrates through `develop`. Release preparation may use `release/<version>`. Stable release baselines merge to `main`. Urgent production corrections may use `hotfix/<name>` from `main` and should be reconciled back into ongoing development.

## Release evidence

A release tag or version number does not by itself prove a capability works. Preserve enough test/build/runtime evidence to support claims made for the release.

## Release history

No formal ROMVERSE release is recorded in this file yet. Add entries here as releases are prepared and shipped, including:

- version
- date
- release stage
- summary
- major changes
- migrations/compatibility notes
- verification performed
- known issues

Do not invent historic release entries without repository or release evidence.
