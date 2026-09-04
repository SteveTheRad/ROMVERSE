package com.radforge.romverse.companion

import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

data class FirstBootGuideStep(
    val id: String,
    val title: String,
    val guidance: String,
)

data class FirstBootGuideState(
    val reviewedStepIds: Set<String> = emptySet(),
    val updatedAtEpochMs: Long = 0L,
) {
    val progressPercent: Int
        get() = reviewedStepIds.size * 100 / FirstBootGuide.steps.size

    val complete: Boolean
        get() = reviewedStepIds.size == FirstBootGuide.steps.size
}

object FirstBootGuide {
    private const val SCHEMA_VERSION = 1
    private const val MAX_BYTES = 16 * 1024
    private val idPattern = Regex("[a-z0-9_-]{1,40}")

    val steps = listOf(
        FirstBootGuideStep(
            "stable_boot",
            "Observe a stable Android boot",
            "Wait for the lock screen or launcher to remain responsive. A boot animation alone is not proof of success.",
        ),
        FirstBootGuideStep(
            "setup_choices",
            "Complete setup choices intentionally",
            "Read each setup page, restore option, permission, and account choice before continuing.",
        ),
        FirstBootGuideStep(
            "display_input",
            "Check display, touch, buttons, and unlock",
            "Confirm the screen, touch zones, hardware buttons, PIN, and any configured biometric prompt behave normally.",
        ),
        FirstBootGuideStep(
            "radio_basics",
            "Check Wi-Fi, Bluetooth, SIM, calls, and data",
            "Test only services available to your device and plan; keep unknown items unconfirmed.",
        ),
        FirstBootGuideStep(
            "usb_trust",
            "Re-authorize the trusted Desktop connection",
            "Reconnect USB, inspect the computer fingerprint, and approve debugging only for the computer you recognise.",
        ),
        FirstBootGuideStep(
            "services",
            "Check required Android services",
            "Confirm the services your ROM is meant to include, such as notifications, location, Play services, or vendor components.",
        ),
        FirstBootGuideStep(
            "android_auto",
            "Validate Android Auto when supported",
            "Open Android Auto, grant only expected permissions, and perform a real head-unit connection test before claiming it works.",
        ),
        FirstBootGuideStep(
            "first_light",
            "Run First Light on ROMVERSE Desktop",
            "Keep the phone available while First Light records genuine subsystem results and routes failures into Lifeline.",
        ),
    )

    init {
        require(steps.map { it.id }.toSet().size == steps.size)
        steps.forEach { step ->
            require(idPattern.matches(step.id))
            require(step.title.isNotBlank() && step.title.none(Char::isISOControl))
            require(step.guidance.isNotBlank() && step.guidance.none(Char::isISOControl))
        }
    }

    fun toggle(
        state: FirstBootGuideState,
        stepId: String,
        reviewed: Boolean,
        nowEpochMs: Long,
    ): FirstBootGuideState {
        require(steps.any { it.id == stepId }) { "First-boot step is unsupported" }
        require(nowEpochMs > 0L) { "First-boot review time is invalid" }
        val updated = state.reviewedStepIds.toMutableSet().apply {
            if (reviewed) add(stepId) else remove(stepId)
        }
        return FirstBootGuideState(updated, nowEpochMs)
    }

    fun encode(state: FirstBootGuideState): String {
        validate(state, Long.MAX_VALUE - 300_000L)
        val canonical = canonical(state)
        val encoded = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("reviewed_step_ids", JSONArray(state.reviewedStepIds.sorted()))
            .put("updated_at_epoch_ms", state.updatedAtEpochMs)
            .put("record_sha256", sha256(canonical))
            .toString()
        require(encoded.toByteArray(Charsets.UTF_8).size <= MAX_BYTES)
        return encoded
    }

    fun decode(raw: String?, nowEpochMs: Long): FirstBootGuideState = runCatching {
        if (raw.isNullOrBlank()) return@runCatching FirstBootGuideState()
        require(raw.toByteArray(Charsets.UTF_8).size <= MAX_BYTES)
        val payload = JSONObject(raw)
        require(payload.keys().asSequence().toSet() == setOf(
            "schema_version",
            "reviewed_step_ids",
            "updated_at_epoch_ms",
            "record_sha256",
        ))
        require(strictLong(payload.opt("schema_version")) == SCHEMA_VERSION.toLong())
        val values = payload.getJSONArray("reviewed_step_ids")
        require(values.length() <= steps.size)
        val reviewed = buildSet {
            repeat(values.length()) { index -> add(values.getString(index)) }
        }
        require(reviewed.size == values.length())
        val updatedAt = strictLong(payload.opt("updated_at_epoch_ms"))
        val state = FirstBootGuideState(reviewed, updatedAt)
        validate(state, nowEpochMs)
        require(payload.getString("record_sha256") == sha256(canonical(state)))
        state
    }.getOrElse { FirstBootGuideState() }

    private fun validate(state: FirstBootGuideState, nowEpochMs: Long) {
        val known = steps.mapTo(mutableSetOf()) { it.id }
        require(state.reviewedStepIds.all(known::contains))
        if (state.reviewedStepIds.isEmpty()) {
            require(state.updatedAtEpochMs == 0L)
        } else {
            require(state.updatedAtEpochMs in 1..nowEpochMs + 300_000L)
        }
    }

    private fun canonical(state: FirstBootGuideState): ByteArray = JSONObject()
        .put("schema_version", SCHEMA_VERSION)
        .put("reviewed_step_ids", JSONArray(state.reviewedStepIds.sorted()))
        .put("updated_at_epoch_ms", state.updatedAtEpochMs)
        .toString()
        .toByteArray(Charsets.UTF_8)

    private fun strictLong(value: Any?): Long = when (value) {
        is Int -> value.toLong()
        is Long -> value
        else -> error("First-boot review time is invalid")
    }

    private fun sha256(payload: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(payload)
        .joinToString("") { byte -> "%02x".format(byte) }
}
