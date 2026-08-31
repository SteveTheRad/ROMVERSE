package com.radforge.romverse.companion

import org.json.JSONObject

data class DesktopDeviceDnaCapability(
    val capabilityId: String,
    val label: String,
    val state: String,
    val detail: String,
) {
    init {
        require(capabilityId.matches(Regex("[a-z0-9._-]{1,80}"))) {
            "Device DNA capability id is invalid"
        }
        require(label.isNotBlank() && label.length <= 100 && label.none(Char::isISOControl))
        require(detail.isNotBlank() && detail.length <= 500 && detail.none(Char::isISOControl))
        require(state in STATES) { "Device DNA capability state is invalid" }
    }

    companion object {
        val STATES = setOf("SUPPORTED", "CAUTION", "UNSUPPORTED", "UNCONFIRMED")
    }
}

data class DesktopDeviceDnaStatus(
    val state: String,
    val project: String,
    val profileRef: String,
    val warningCount: Int,
    val capabilities: List<DesktopDeviceDnaCapability>,
    val executionAuthority: String,
    val bootloaderRelock: String,
) {
    init {
        require(state in setOf("ready", "needs-attention")) { "Device DNA state is invalid" }
        require(project.isNotBlank() && project.length <= 120 && project.none(Char::isISOControl))
        require(profileRef.matches(Regex("[0-9a-f]{16}"))) {
            "Device DNA profile reference is invalid"
        }
        require(warningCount in 0..100) { "Device DNA warning count is invalid" }
        require(capabilities.size in 1..12) { "Device DNA Capability Map is invalid" }
        require(executionAuthority == "none") { "Device DNA cannot carry execution authority" }
        require(bootloaderRelock == "never") {
            "Device DNA can never authorize bootloader relocking"
        }
    }

    val headline: String
        get() = if (state == "ready") "PROFILE READY" else "EVIDENCE NEEDS ATTENTION"

    val attentionCount: Int
        get() = capabilities.count {
            it.capabilityId != "bootloader_relock" && it.state != "SUPPORTED"
        }

    fun privacySafeReport(): String = buildString {
        appendLine("ROMVERSE DEVICE DNA • READ-ONLY CAPABILITY MAP")
        appendLine("Project: $project")
        appendLine("Profile reference: $profileRef")
        appendLine("State: ${state.replace('-', ' ').uppercase()}")
        appendLine("Warnings: $warningCount")
        appendLine("Actionable items: $attentionCount")
        capabilities.forEach { capability ->
            appendLine("${capability.state} • ${capability.label}")
            appendLine("  ${capability.detail}")
        }
        appendLine("Execution authority: NONE")
        appendLine("Bootloader relock: NEVER")
        append("Privacy scope: no source paths, full hashes, commands, approvals, or device writes")
    }

    companion object {
        fun parse(schemaVersion: Int, payload: JSONObject): DesktopDeviceDnaStatus? = runCatching {
            require(schemaVersion == 6) { "Device DNA requires Link schema 6" }
            val state = payload.optString("device_dna_state", "unavailable")
            val rawCapabilities = payload.optJSONArray("device_dna_capabilities")
                ?: error("Device DNA Capability Map is missing")
            val authority = payload.optString("device_dna_execution_authority")
            val relock = payload.optString("device_dna_bootloader_relock")
            if (state == "unavailable") {
                require(payload.optString("device_dna_project").isBlank())
                require(payload.optString("device_dna_profile_ref").isBlank())
                require(payload.optInt("device_dna_warning_count", 0) == 0)
                require(rawCapabilities.length() == 0)
                require(authority == "none" && relock == "never")
                return@runCatching null
            }
            require(rawCapabilities.length() in 1..12)
            val capabilities = buildList {
                for (index in 0 until rawCapabilities.length()) {
                    val item = rawCapabilities.getJSONObject(index)
                    add(
                        DesktopDeviceDnaCapability(
                            capabilityId = item.getString("capability_id"),
                            label = item.getString("label"),
                            state = item.getString("state"),
                            detail = item.getString("detail"),
                        ),
                    )
                }
            }
            DesktopDeviceDnaStatus(
                state = state,
                project = payload.getString("device_dna_project"),
                profileRef = payload.getString("device_dna_profile_ref"),
                warningCount = payload.getInt("device_dna_warning_count"),
                capabilities = capabilities,
                executionAuthority = authority,
                bootloaderRelock = relock,
            )
        }.getOrNull()
    }
}
