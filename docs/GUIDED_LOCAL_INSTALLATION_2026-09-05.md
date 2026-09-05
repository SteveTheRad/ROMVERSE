# Guided local image installation

This increment connects a completed local candidate to a real, separately confirmed image
operation. It removes the primary-action loop through Device Atlas. It does **not** claim an
automatic complete-ROM installer, universal device support, or production release readiness.

## User journey

1. In Forge Control, choose **Prepare local image installation…**, or continue from Genesis's
   optional installation step. The app stays in Guided Mode.
2. Explicitly choose the saved successful rebuilt candidate or verified extracted images from
   the protected original. A missing rebuilt candidate does not silently select stock images.
3. ROMVERSE checks the current project, source, inventory and image hashes in the background.
   Protected ZIP/TAR members are compared with their actual original archive bytes. OTA images
   require the current source-bound extraction manifest. Preparing this inventory sends no phone
   command and grants no write authority.
4. Add selected images and enter each exact partition and slot in the intended write order.
   The app deliberately does not turn an image filename into a destination or select every build
   output. For example, a rebuilt product image may already be inside super; an inventory alone
   does not establish a valid complete flashing sequence.
5. Review the phone, mode, source, full image hashes, destinations, space requirements and risks.
   Each mode change and each image-write plan has its own explicit confirmation. Cancel is the
   default. Project/source/image changes invalidate the prepared evidence. Contradictory known
   device identity cannot be waived by accepting a warning.
6. A confirmed image operation delegates to the existing exact-target local executor. It stages
   the approved image bytes, rechecks the phone and live partition capacity, writes in reviewed
   order, stops after a failure or cancellation, and saves private linked receipts. It does not
   automatically erase, activate a slot, disable AVB, unlock or relock the bootloader.
7. A separately confirmed restart can lead into measured Android boot observation. Write
   completion, observed boot, image readback and subsystem health remain distinct. A failed or
   uncertain operation leads to diagnosis for the exact attempted phone, not another connected
   device.

## Evidence boundaries

- Project-local receipts bind the project/source, selected inventory evidence, reviewed plan and
  exact local child receipt. They do not create a signed production Guardian execution result.
- Genesis displays historical local image outcomes separately from full-ROM installation and
  first-boot certification. Reopening the workflow is an intentional new action, not an instruction
  to repeat a completed write until certification indicators turn green.
- Production Device Pack attestations and release certificates retain their existing separate
  evidence checks. They no longer stand between a verified candidate and opening the local image
  workflow.
- Source hashing can be expensive for large firmware archives. Fresh execution checks do not
  extend an expired phone-mode consent automatically. Large-archive responsiveness and physical
  device validation remain necessary beyond the small inert fixtures.
- Local user-data backups and a credible recovery route remain the user's responsibility for
  these manually mapped operations. A stock archive's presence does not prove that a complete
  restoration procedure has been tested.

## Validation scope

The regression suite uses synthetic archives, real production project/image/lifecycle services,
real Qt dialogs and strictly inert Android transports. It covers actual click/type/review/decline/
confirm journeys, source and image changes with restored timestamps, changed projects, identity
conflicts, normalized archive paths, worker lifecycle, partial failure and recovery handoff.
These checks are software simulation evidence, not tests on a physical phone.

The approved ROMVERSE and RadForge Labs logos are unchanged. This work does not install a
Companion APK, restart the user's app, publish a release or push to a remote repository.

## Still required for an automatic full-ROM route

The current source-derived image inventories do not establish complete write order, required
transitions, active-slot policy, OTA post-install behavior, AVB relationships or a matching stock
restore sequence. A subsequent supported installer must consume an explicit source-declared or
reviewed typed installation recipe, reject unsupported instructions, preserve provenance and
rehearse the actual sequence. It must not infer a complete firmware upgrade from a successful
single-partition write.
