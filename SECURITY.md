# Security policy

ROMVERSE is pre-release software that handles sensitive device evidence. A passing test or an
open-source license does not authorize device writes, bootloader relocking, signing, account
access, or disclosure of another person's data.

## Reporting a vulnerability

Use the repository's **Security > Report a vulnerability** control when private reporting is
available: <https://github.com/SteveTheRad/ROMVERSE/security/advisories/new>.
If GitHub does not offer that control, ask the maintainer for a private reporting channel using
the contact options on <https://github.com/SteveTheRad>. A public issue may request a private
channel, but must contain no exploit details, credentials, device identifiers, or private logs.
Do not assume that private reporting is enabled merely because this document exists.

Privately provide the affected commit/version, expected and actual behavior, impact, a minimal
synthetic reproduction, and redacted diagnostics. Never attach customer data, firmware dumps,
private keys, tokens, pairing material, or real device serials. Agree on disclosure timing with
the maintainer; no response deadline or security support for old topic/recovery branches is
promised. Fixes target the current `main` branch first.

## Accidental exposure

Revoke or rotate exposed credentials first. Removing a file in a new commit does not erase its
history, forks, or caches. Historical cleanup requires a separately reviewed decision; never
force-push or delete shared branches as a substitute for revocation.

Before committing, use the documented Gitleaks check, inspect the staged diff and file list,
and use your own GitHub noreply commit email. CI scans reachable history with default secret
rules plus narrowly anchored exceptions for reviewed non-secret declarations. Scanner output
is redacted; a clean scan is not a guarantee that all private information has been found.
