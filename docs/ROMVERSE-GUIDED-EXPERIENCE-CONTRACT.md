# ROMVERSE Guided Experience Contract

Status: creator-approved requirements, 2026-09-05. Implementation remains subject to the full
twenty-stage master goal and evidence-based acceptance; approval is not proof that a feature ships.

Source: latest approvals in **ROMVERSE General chat**
(`6a92fbe2-b70c-83ec-8f31-11a80ef7f9c1`), explicitly adopted by the creator in **Romverse Build**:
“add the new approvals in and ofcourse the ones that conflict do what is recommended by you.”

## Purpose

**Maximum capability. Minimum friction. No compromise on safety.**

The user chooses an outcome. ROMVERSE owns the work needed to reach it: preparation, diagnosis,
solution selection, verification, continuity and an understandable result. Guided must not require
the user to understand Android tooling, search for an error explanation or navigate multiple
departments to escape a failure. Minimize disruption; do not promise that every hardware failure can
be repaired or every operation can safely resume.

## Resolved decisions

- Only **Guided** and **Expert**. Earlier Beginner/Standard/Advanced three-level proposals are
  superseded. Their capabilities remain available through contextual help and Expert controls.
- One engine, operation session, project state and evidence model; two deliberately different
  presentations. Do not maintain a second executor or a competing Journey state store.
- Expert expands visibility, configuration and direct controls, not authority to ignore a different
  phone, changed inputs, forbidden commands or failed integrity. Earlier “Guardian off” or
  “advisory-only” wording is superseded for these protections. Risk warnings and uncertain evidence
  remain distinct from confirmed incompatibility; do not reintroduce arbitrary certificate locks.
- Bootloader relocking is forbidden everywhere, without an override. This includes Guided, Expert,
  imported procedures, recipes, tools, AI/Copilot, Autonomous Repair, Recovery and future features.
  Never blindly remove a forbidden step and assume the rest of an unfamiliar procedure is valid;
  use a validated permitted plan or explain the unsupported procedure and available alternative.
- Preserve all twenty master-goal stages, offline usefulness, privacy, explicit user control,
  accessibility, reduced motion and byte-exact approved ROMVERSE/RadForge Labs logos.

## Guided presentation

Default to a calm goal-oriented journey: choose intent and firmware, prepare, review when needed,
install or build, check the outcome, and finish or enter guided recovery.

Show the device, selected ROM/project, current human-readable stage, meaningful consequences,
actual progress and the next useful action. Keep raw hashes, partition lists, individual commands,
dependency graphs and detailed logs behind **View technical details**. They remain available and
recorded. Use spacious layouts, a restrained cosmic identity and purposeful transitions; avoid
technical walls of text, redundant green rows and fake percentage estimates.

Routine completion and informational events go to unobtrusive inline status or Activity Center,
not modal popups. A decision that genuinely requires the user receives one clear, accessible
review. A changed consequential plan needs fresh review; it must not quietly reuse earlier consent.
Do not ask again merely because the user changes screens or presentation mode.

Show honest outcomes. “No data erase requested” is not a guarantee against data loss. “Commands
completed” does not prove readback, boot, stability or subsystem health. Do not display “Safe,”
“Recovery ready,” “Data preserved” or “Your phone is ready” unless the actual evidence supports the
specific claim. State uncertainty concisely, with its practical consequence and proposed action.

## Automatic preparation and remediation

Perform safe deterministic inspection, matching, source validation, tool resolution and planning
in the background as soon as the necessary inputs exist. Respect user-selected network/tool
policies, offline operation, resource budgets and permissions. Automation does not authorize
unrestricted downloads, host changes or deletion of user files.

Carry the validated phone, project, firmware, source, tool and operation context between views and
resumable sessions. Reuse evidence only while its dependencies remain valid; freshly check critical
inputs at their use boundaries. A changed phone or source must not inherit another plan's consent.

For every interruption, follow **detect → diagnose → prepare a permitted solution → verify →
continue** wherever possible. Inspect source and offline Knowledge Archives automatically for
relevant guidance, retaining provenance and uncertainty. Knowledge or AI suggestions cannot become
executable commands or permission by themselves.

| Interruption | Required Guided behavior |
| --- | --- |
| ADB authorization missing | Show the exact physical instruction, watch for authorization and continue automatically once the intended phone is verified. |
| Missing or incompatible tool | Resolve a verified compatible tool within the approved tool policy, verify it and continue; request privileged permission only when genuinely required. |
| Insufficient workspace storage | Calculate the requirement and offer an available destination or eligible app-owned temporary cleanup. Never delete originals, recovery evidence, user backups or unrelated files automatically. |
| Source changed | Revalidate and re-plan automatically. If the approved content or consequences changed, prepare one new meaningful review before execution. |
| USB disconnected | Stop unsafe commands, preserve durable progress, watch for the exact device and revalidate its state. Resume only where the checkpoint and measured outcome justify it. |
| Write failed or result uncertain | Reconstruct completed, attempted and unknown actions, automatically enter recovery diagnosis and prepare the supported next action. Never blindly retry a write. |
| Android slow to boot or bootlooping | Measure arrival and boot evidence, diagnose the failure and continue into the appropriate recovery workflow; do not stop at an unexplained timeout. |
| No supported automatic solution | Explain the precise limitation and guide the best available next action. Do not fabricate a solution or promise repair. |

Ask the user only for intent, an actual choice, consequential/destructive authorization, required
physical action, necessary privileges or information the app cannot safely determine. Existing
exact-plan authorization covers its reviewed steps, not an additional wipe, reflash or recovery
operation with different consequences. After required user action, detect completion and continue
where valid rather than making the user repeatedly press Refresh or navigate back to setup.

## Shared session and seamless switching

Use an application-owned mission/session controller to retain the selected context, immutable
reviewed plan, consent identity, worker, progress, cancellation state, durable results, boot
observation and recovery continuation. Screens subscribe to that controller; they do not own a
second execution lifetime. Reuse the existing build, installation, transition, boot, history and
recovery services behind it.

Guided ↔ Expert changes layout and information density while the same operation continues. Never
restart, duplicate or abandon work; never let a mode change grant permission or silently change
the plan. A view closing is distinct from the user's explicit Stop request. Preserve the shared
device-command lock, safe Stop boundaries, stale-input rejection and truthful interrupted state.

Expert exposes partitions, ROM and Device DNA, source provenance, pipelines, Guardian evidence,
logs, timings, toolchain, advanced Workshop controls, configurable layouts and Command Bar access.
Guided keeps the human stages prominent. Both retain access to a common final result showing
installation, readback, boot/stability and individual subsystem states separately.

## Engineering and release discipline

Keep **Approved → Implemented → Verified → Released** distinct. Continue the representative
end-to-end workflow and save verified version checkpoints before broadening supported formats or
performing a broad cosmetic rewrite. Existing approved capabilities remain planned, not cancelled.

Use the existing release and Device Pack/compatibility systems for evidence levels and support
scope; do not create contradictory registries or a second certificate gate. Release readiness is
an engineering claim, not an extra user task that must be satisfied to view results or proceed
through a supported, appropriately reviewed local workflow.

Maintain separate evidence for simulation, command completion, image readback, boot observation,
stability, subsystem validation, physical-device verification and release readiness. Cosmetic
animation or a successful test suite cannot promote an unmeasured state. Platform parity and
performance measurements remain part of verification, not assumed from the development PC.

## Acceptance tests required

- Guided completes safe preparation without routine popups or repeated device/source selection.
- Guided shows a compact outcome-oriented view; Expert exposes the same live operation's details.
- Switching mode during preparation, writes, boot observation and recovery preserves the exact
  session, plan, consent and result, with no extra commands or duplicate worker.
- An unavoidable physical action has an exact instruction, automatic detection and continuation.
- A changed target, source, tool or consequential plan cannot reuse stale consent.
- Disconnect/failure preserves exact attempted/completed/unknown states and proposes an actionable
  recovery route; unknown write outcomes never cause an automatic retry.
- Safe remediation is verified before continuation. Repeated failure is bounded and changes the
  proposed solution rather than spinning in a retry or navigation loop.
- New destructive recovery actions need appropriate exact-plan confirmation; mode changes and
  knowledge/AI output cannot grant it.
- Bootloader relocking is rejected through every command entry point and imported plan, in both
  modes, including aliases and attempted indirect invocation. There is no “relock anyway” control.
- No global success or data-preservation claim appears without the required specific evidence.
- Session recovery, layouts, keyboard/screen-reader access, high contrast and reduced motion are
  verified on supported desktop platforms. Approved logo bytes remain unchanged.

These are completion requirements, not a statement that the current implementation already passes
them. The current modal installation lifecycle and partial recovery orchestration still require
integration work.
