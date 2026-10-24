# ROMVERSE Development Workflow

## Repository role

This public repository is the authoritative source for ROMVERSE code, tests, build instructions,
architecture, implementation status, and release evidence. Important decisions must not exist only
in chat history or on one development computer.

## Branches

Use `git branch -r` to inspect the current branches. In addition to `main` and `develop`, the
repository retains topic, evidence, and recovery branches; their presence is not a release claim.

- `main`: stable project baseline and migration/release commits
- `develop`: normal integration branch
- `feature/<name>`: short-lived feature work from `develop`
- `fix/<name>`: bug fixes from `develop`
- `release/<version>`: optional release preparation
- `hotfix/<name>`: urgent stable corrections from `main`

Use pull requests where practical. The initial local-source import is a baseline migration; normal
feature development should resume through `develop`.

## Status language

Use these labels exactly:

- **Planned**: approved or described direction with no implementation claim.
- **In Progress**: active implementation that is incomplete.
- **Implemented**: production code exists, but proportionate verification is incomplete.
- **Implemented and Verified**: source exists and the stated automated, fixture, build, or runtime
  evidence passed.
- **Unverified**: a claim or integration path has not been demonstrated in the stated environment.

Always state verification scope. Passing fixtures does not prove a physical-device operation,
Windows behavior, production service, signed release, or commercial readiness.

## Development cycle

1. Search existing models and vocabulary before introducing a duplicate concept.
2. Identify Guardian, privacy, data-loss, device, and rollback implications.
3. Implement on the appropriate branch.
4. Add focused tests and failure-path coverage.
5. Run proportionate quality/build/runtime gates.
6. Update affected docs and feature status in the same change.
7. Record limitations and unverified environments.
8. Review the complete staged change for secrets and generated files.

## Required desktop gates

```bash
pytest
ruff check .
ruff format --check .
```

GitHub Actions runs the full suite on Ubuntu with Python 3.12 and 3.14. Windows currently runs a
targeted portability smoke plus Ruff. The full Windows suite is known to require platform-aware
permission, fsync, symlink, executable, and path handling before it can become a required gate.

For package-impacting changes:

```bash
python -m build --wheel
python scripts/verify_wheel.py dist/romverse-0.1.0-py3-none-any.whl
```

Run the installed-wheel smoke test when startup, packaging, assets, Device Packs, or workspace
initialization changes.

## Required Companion gates

For Kotlin/Android changes:

```bash
./companion/gradlew --no-daemon -p companion testDebugUnitTest :app:assembleDebug
```

Run `:app:lintDebug` for Android packaging/UI changes. Run
`:app:connectedDebugAndroidTest` when an authorized emulator or device is available and the
change affects Activity behavior, lifecycle, pairing, permissions, or device integration.

Never describe JVM-only evidence as connected-device verification.

## Guardian and device rules

- Never relock a bootloader.
- Keep destructive operations behind explicit informed authorization.
- Preserve source firmware, projects, backups, configuration, and user data by default.
- Treat unknown device evidence as `UNCONFIRMED`.
- Keep Companion telemetry read-only unless a separately reviewed contract explicitly changes it.
- Require exact evidence bindings and fail closed when evidence is stale, malformed, mismatched, or
  incomplete.
- Validate real-device write, signing, backup/restore, and flash contracts independently before
  advertising them.

## Secrets and personal data

Never commit:

- passwords, API keys, tokens, credentials, or populated `.env` files
- private/signing keys, certificates, keystores, or release signing material
- real device serials, private logs, account identifiers, or customer/user data
- machine-specific paths or local tool receipts that identify one development PC

Documentation may name required variables but must not contain their values. If a credential is
ever committed, rotate it immediately; deleting Git history is not sufficient.

## Generated-file boundary

Do not stage virtual environments, SDKs, Gradle caches, build trees, APKs, Python distributions,
coverage, logs, firmware images, extracted workspaces, backups, dumps, or `work/` media. Use
`git status --short` and inspect every staged path before committing.

The committed Gradle wrapper is an intentional exception: `gradlew`, `gradlew.bat`,
`gradle-wrapper.properties`, and `gradle-wrapper.jar` are source-controlled portability files.

## Commit and review discipline

Prefer focused commits with conventional prefixes:

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `test:`
- `build:`
- `chore:`

Before push, review the staged file list, diff summary, credential scan, and build/test evidence.
Never force-push shared stable branches unless a separately approved recovery requires it.

Use GitHub's private commit email for future commits. For this maintainer it is
`322917794+SteveTheRad@users.noreply.github.com`; contributors should use their own address from
GitHub Settings > Emails. Set the identity only in the intended local repository, not globally.
Normal follow-up commits do not remove personal information from older commits. Historical
identities and evidence remain intact; a history rewrite requires a separate explicit decision.

Run `gitleaks git --redact --config .gitleaks.toml --log-opts="--all -m --full-history" .` before pushing. The
configuration extends the default rules and excludes only exact, reviewed non-secret code lines.
Do not add broad path exclusions or real secrets to an allowlist. See [SECURITY.md](../SECURITY.md)
for vulnerability reporting and [asset provenance](ASSET_PROVENANCE.md) for bundled media.

## Documentation ownership

- `BUILDING.md`: prerequisites, setup, build, test, and migration
- `ARCHITECTURE.md`: actual subsystem boundaries and data flow
- `FEATURES.md`: current status and verification scope
- `GUARDIAN.md`: safety invariants and authorization
- `ROADMAP.md`: future ordering, never implementation evidence
- `RELEASE_READINESS.md`: detailed gates and honest release boundary
- `RELEASES.md`: actual releases only

## Handoff record

A development handoff should state:

- branch and commit
- Implemented and Verified work
- Implemented but not fully verified work
- In Progress and Planned work
- Unverified hosts, devices, services, and workflows
- exact gates run and their results
- secrets/configuration names required, never values
- known blockers and safe next action
