package com.radforge.romverse.companion

import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

data class LastKnownDeviceDna(
    val capturedAtEpochMs: Long,
    val status: DesktopDeviceDnaStatus,
    val recordSha256: String,
)

object LastKnownDeviceDnaArchive {
    private const val SCHEMA_VERSION = 1
    private const val MAX_BYTES = 64 * 1024
    private val sha256Pattern = Regex("[0-9a-f]{64}")

    fun encode(status: DesktopDeviceDnaStatus, capturedAtEpochMs: Long): String {
        require(capturedAtEpochMs > 0L) { "Device DNA capture time is invalid" }
        val payload = canonical(status, capturedAtEpochMs)
        val result = JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("captured_at_epoch_ms", capturedAtEpochMs)
            .put("status", statusJson(status))
            .put("record_sha256", sha256(payload))
            .toString()
        require(result.toByteArray(Charsets.UTF_8).size <= MAX_BYTES) {
            "Last-known Device DNA exceeds its storage boundary"
        }
        return result
    }

    fun decode(raw: String?, nowEpochMs: Long): LastKnownDeviceDna? = runCatching {
        require(!raw.isNullOrBlank() && raw.toByteArray(Charsets.UTF_8).size <= MAX_BYTES)
        val payload = JSONObject(raw)
        require(payload.keys().asSequence().toSet() == setOf(
            "schema_version",
            "captured_at_epoch_ms",
            "status",
            "record_sha256",
        ))
        require(strictLong(payload.opt("schema_version")) == SCHEMA_VERSION.toLong())
        val capturedAt = strictLong(payload.opt("captured_at_epoch_ms"))
        require(capturedAt in 1..nowEpochMs + 300_000L)
        val status = parseStatus(payload.getJSONObject("status"))
        val recordSha256 = strictString(payload, "record_sha256")
        require(sha256Pattern.matches(recordSha256))
        require(recordSha256 == sha256(canonical(status, capturedAt)))
        LastKnownDeviceDna(capturedAt, status, recordSha256)
    }.getOrNull()

    private fun parseStatus(payload: JSONObject): DesktopDeviceDnaStatus {
        require(payload.keys().asSequence().toSet() == setOf(
            "state",
            "project",
            "profile_ref",
            "warning_count",
            "capabilities",
            "execution_authority",
            "bootloader_relock",
        ))
        val rawCapabilities = payload.getJSONArray("capabilities")
        require(rawCapabilities.length() in 1..12)
        val capabilities = buildList {
            repeat(rawCapabilities.length()) { index ->
                val item = rawCapabilities.getJSONObject(index)
                require(item.keys().asSequence().toSet() == setOf(
                    "capability_id",
                    "label",
                    "state",
                    "detail",
                ))
                add(
                    DesktopDeviceDnaCapability(
                        capabilityId = strictString(item, "capability_id"),
                        label = strictString(item, "label"),
                        state = strictString(item, "state"),
                        detail = strictString(item, "detail"),
                    ),
                )
            }
        }
        val warningCount = strictLong(payload.opt("warning_count"))
        require(warningCount in 0..100)
        return DesktopDeviceDnaStatus(
            state = strictString(payload, "state"),
            project = strictString(payload, "project"),
            profileRef = strictString(payload, "profile_ref"),
            warningCount = warningCount.toInt(),
            capabilities = capabilities,
            executionAuthority = strictString(payload, "execution_authority"),
            bootloaderRelock = strictString(payload, "bootloader_relock"),
        )
    }

    private fun canonical(status: DesktopDeviceDnaStatus, capturedAtEpochMs: Long): ByteArray =
        JSONObject()
            .put("schema_version", SCHEMA_VERSION)
            .put("captured_at_epoch_ms", capturedAtEpochMs)
            .put("status", statusJson(status))
            .toString()
            .toByteArray(Charsets.UTF_8)

    private fun statusJson(status: DesktopDeviceDnaStatus): JSONObject = JSONObject()
        .put("state", status.state)
        .put("project", status.project)
        .put("profile_ref", status.profileRef)
        .put("warning_count", status.warningCount)
        .put(
            "capabilities",
            JSONArray().apply {
                status.capabilities.forEach { capability ->
                    put(
                        JSONObject()
                            .put("capability_id", capability.capabilityId)
                            .put("label", capability.label)
                            .put("state", capability.state)
                            .put("detail", capability.detail),
                    )
                }
            },
        )
        .put("execution_authority", status.executionAuthority)
        .put("bootloader_relock", status.bootloaderRelock)

    private fun strictLong(value: Any?): Long = when (value) {
        is Int -> value.toLong()
        is Long -> value
        else -> error("Device DNA capture time is invalid")
    }

    private fun strictString(payload: JSONObject, key: String): String =
        payload.opt(key) as? String ?: error("Last-known Device DNA text is invalid")

    private fun sha256(payload: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(payload)
        .joinToString("") { byte -> "%02x".format(byte) }
}
