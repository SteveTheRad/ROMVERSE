# ROMVERSE Product Assurance sync workflow

The active **Romverse Build** task remains the authoritative implementation task. It keeps its
current model, settings, source directory, master goal and development workflow. The separate
**ROMVERSE — Product Assurance & Strategy** conversation independently checks fidelity and does not
modify the same source tree or become a second Build task.

At every meaningful engineering checkpoint, Build sends a concise **ROMVERSE Product Assurance
Sync** covering:

- authoritative commit and working-tree state;
- current stage or milestone and exact changes;
- Implemented, Simulated/Tested, Hardware Verified and Released status;
- non-overlapping test results, current blockers and failures;
- Guided friction or remaining dead ends;
- Guardian, Recovery and safety implications;
- Windows and Linux verification status;
- feature-freeze and version-gate impact;
- the next concrete Build task; and
- whether any physical phone operation, publishing, package installation or remote push occurred.

When useful, the sync includes **Product Assurance Review Requested** for a decision, UX behavior,
safety boundary or release gate. Build continues after sending the sync and does not wait for Product
Assurance to implement or authorize ordinary in-scope work.

The loop is: **Build → Verify → Sync → Product Assurance → Feedback → Build**.
