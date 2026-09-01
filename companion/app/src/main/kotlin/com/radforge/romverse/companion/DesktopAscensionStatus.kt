package com.radforge.romverse.companion

data class DesktopAscensionStatus(
    val state: String,
    val project: String,
    val method: String,
    val targetPartition: String,
    val blockerCount: Int,
    val phoneChanged: Boolean,
    val executionAuthority: String,
    val stageNumber: Int = 0,
    val stageTitle: String = "",
    val guidedNextAction: String = "",
    val whyItMatters: String = "",
    val romverseAction: String = "",
    val managerState: String = "unavailable",
    val managerRepository: String = "",
    val managerTag: String = "",
    val managerAsset: String = "",
    val managerSha256Ref: String = "",
) {
    init {
        require(state in STATES) { "Ascension state is invalid" }
        require(project.length <= 120 && project.none(Char::isISOControl)) {
            "Ascension project is invalid"
        }
        require(method in METHODS) { "Ascension method is invalid" }
        require(targetPartition in PARTITIONS) { "Ascension target partition is invalid" }
        require(blockerCount in 0..100) { "Ascension blocker count is invalid" }
        require(!phoneChanged) { "Read-only telemetry cannot claim a phone change" }
        require(executionAuthority == "none") {
            "Read-only telemetry cannot carry execution authority"
        }
        require(stageNumber in 0..9) { "Ascension stage is invalid" }
        require(stageTitle.length <= 120 && stageTitle.none(Char::isISOControl)) {
            "Ascension stage title is invalid"
        }
        require(guidedNextAction.length <= 500 && guidedNextAction.none(Char::isISOControl)) {
            "Ascension next action is invalid"
        }
        require(whyItMatters.length <= 500 && whyItMatters.none(Char::isISOControl)) {
            "Ascension reason is invalid"
        }
        require(romverseAction.length <= 500 && romverseAction.none(Char::isISOControl)) {
            "Ascension automatic action is invalid"
        }
        require(managerState in MANAGER_STATES) { "Ascension manager state is invalid" }
        val managerValues = listOf(
            managerRepository,
            managerTag,
            managerAsset,
            managerSha256Ref,
        )
        if (managerState == "unavailable") {
            require(managerValues.all(String::isEmpty)) {
                "Unavailable Ascension manager cannot carry provenance"
            }
        } else {
            require(managerRepository == MANAGER_REPOSITORIES[method]) {
                "Ascension manager repository does not match its method"
            }
            require(managerTag.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,79}"))) {
                "Ascension manager tag is invalid"
            }
            val assetPattern = when (method) {
                "magisk" -> Regex("Magisk-v[0-9][A-Za-z0-9._-]*\\.apk")
                "kernelsu_lkm" -> Regex("KernelSU_v[0-9][A-Za-z0-9._-]*-release\\.apk")
                else -> null
            }
            require(managerAsset.length <= 120 && assetPattern?.matches(managerAsset) == true) {
                "Ascension manager asset is invalid"
            }
            require(managerSha256Ref.matches(Regex("[0-9a-f]{16}"))) {
                "Ascension manager fingerprint reference is invalid"
            }
        }
    }

    val stagePercent: Int
        get() = if (stageNumber > 0) {
            ((stageNumber * 100) + 4) / 9
        } else when (state) {
            "no_project" -> 0
            "not_started" -> 10
            "skipped" -> 100
            "preparing" -> 65
            "blocked" -> 82
            "review_ready" -> 100
            else -> 0
        }

    val stateLabel: String
        get() = when (state) {
            "no_project" -> "NO DESKTOP PROJECT"
            "not_started" -> "READY TO BEGIN"
            "skipped" -> "UNROOTED ROM SELECTED"
            "preparing" -> "PREPARING WITH DESKTOP"
            "blocked" -> "GUARDIAN NEEDS ATTENTION"
            "review_ready" -> "READY FOR GUARDIAN REVIEW"
            else -> "UNKNOWN"
        }

    val nextStep: String
        get() = guidedNextAction.ifBlank { when (state) {
            "no_project" ->
                "Open ROM Studio on Desktop and choose or create a ROM project. Companion will update automatically."
            "not_started" ->
                "Open Ascension Protocol on Desktop. ROMVERSE will scan the exact project and explain the safest supported route."
            "skipped" ->
                "Genesis Sequence will continue with the standard unrooted build route. Root remains optional."
            "preparing" ->
                "Keep ROMVERSE Desktop open while it verifies the source, device match, manager, backup, and patch target."
            "blocked" ->
                "Return to Desktop and follow the highlighted Guardian card. ROMVERSE will resolve safe gates automatically and explain any choice only you can make."
            "review_ready" ->
                "Review the exact plan on Desktop. Nothing is written to the phone until the final Guardian review and your explicit consent."
            else -> "Return to ROMVERSE Desktop for a fresh read-only status scan."
        } }

    companion object {
        private val STATES = setOf(
            "no_project",
            "not_started",
            "skipped",
            "preparing",
            "blocked",
            "review_ready",
        )
        private val METHODS = setOf("none", "magisk", "kernelsu_lkm")
        private val PARTITIONS = setOf("", "boot", "init_boot", "recovery", "vendor_boot")
        private val MANAGER_STATES = setOf("unavailable", "verified")
        private val MANAGER_REPOSITORIES = mapOf(
            "magisk" to "topjohnwu/Magisk",
            "kernelsu_lkm" to "tiann/KernelSU",
        )
        private val SUPPORTED_SCHEMAS = 2..6

        fun parse(
            schemaVersion: Int,
            state: String,
            project: String,
            method: String,
            targetPartition: String,
            blockerCount: Int,
            phoneChanged: Boolean,
            executionAuthority: String,
            stageNumber: Int = 0,
            stageTitle: String = "",
            guidedNextAction: String = "",
            whyItMatters: String = "",
            romverseAction: String = "",
            managerState: String = "unavailable",
            managerRepository: String = "",
            managerTag: String = "",
            managerAsset: String = "",
            managerSha256Ref: String = "",
        ): DesktopAscensionStatus? = runCatching {
            require(schemaVersion in SUPPORTED_SCHEMAS) {
                "Ascension telemetry schema is unsupported"
            }
            if (schemaVersion < 6) {
                require(
                    managerState == "unavailable" &&
                        managerRepository.isEmpty() &&
                        managerTag.isEmpty() &&
                        managerAsset.isEmpty() &&
                        managerSha256Ref.isEmpty()
                ) { "Ascension manager provenance requires Link schema 6" }
            }
            DesktopAscensionStatus(
                state,
                project,
                method,
                targetPartition,
                blockerCount,
                phoneChanged,
                executionAuthority,
                stageNumber,
                stageTitle,
                guidedNextAction,
                whyItMatters,
                romverseAction,
                managerState,
                managerRepository,
                managerTag,
                managerAsset,
                managerSha256Ref,
            )
        }.getOrNull()
    }
}
