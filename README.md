# ROMVERSE

> **Public open-source software.** ROMVERSE is licensed under GPL-3.0-only; see `LICENSE`.

ROMVERSE is a software project focused on providing a polished, dependable platform for Android-focused tooling and workflows.

## Project status

ROMVERSE is under active open-source development. Credentials, signing material, personal device evidence, customer data, and third-party confidential information must remain outside Git.

## Repository policy

- `main` contains the stable project baseline.
- `develop` is the integration branch for ongoing development.
- New work should use short-lived `feature/<name>` branches from `develop`.
- Bug fixes should use `fix/<name>` branches from `develop`.
- Release preparation may use `release/<version>` branches when needed.
- Emergency production fixes may use `hotfix/<name>` branches from `main`.
- Merge work through pull requests where practical; avoid direct feature development on `main`.

## Security and confidentiality

Never commit credentials, API tokens, signing keys, certificates, private configuration, customer/user data, proprietary research notes, unreleased architecture details, generated secrets, or local environment files.

Use environment variables or an approved secret-management mechanism for sensitive values. If a secret is committed accidentally, treat it as compromised and rotate it immediately rather than relying on commit deletion alone.

## Local development

Detailed setup instructions will be added alongside the implementation as the project matures. Keep machine-specific configuration outside version control and follow the repository `.gitignore` rules.

## Ownership

Copyright (c) 2026 SteveTheRad / RadForge Labs.

ROMVERSE is licensed under GPL-3.0-only. See `LICENSE`; third-party components retain their own terms.

## Public source maintenance

The current branch tip is distributed under GPL-3.0-only; see [LICENSE](LICENSE).
[Third-party notices](THIRD_PARTY_NOTICES.txt) retain separate media and trademark terms.
The supported current development baseline is `main`; topic, evidence, and recovery branches
retain their feature state and are not release-readiness claims. Original commits, historical
identities, and evidence have not been rewritten. Use your own GitHub noreply commit email
for new contributions. See [SECURITY.md](SECURITY.md) for reporting and privacy guidance.
