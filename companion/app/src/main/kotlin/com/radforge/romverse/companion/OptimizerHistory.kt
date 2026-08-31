package com.radforge.romverse.companion

import java.security.MessageDigest

internal data class OptimizerSnapshot(
    val capturedAtEpochMs: Long,
    val batteryPercent: Int,
    val storagePercent: Int,
    val ramPercent: Int,
    val healthScore: Int,
) {
    init {
        require(capturedAtEpochMs > 0L) { "Optimizer timestamp must be positive" }
        listOf(batteryPercent, storagePercent, ramPercent, healthScore).forEach {
            require(it in 0..100) { "Optimizer metric must be 0..100" }
        }
        require(healthScore == OptimizerTrendHistory.healthScore(batteryPercent, storagePercent, ramPercent)) {
            "Optimizer health score does not match its evidence"
        }
    }
}

internal data class OptimizerHistoryRead(
    val valid: Boolean,
    val integrityVerified: Boolean,
    val snapshots: List<OptimizerSnapshot>,
    val reason: String,
)

internal object OptimizerTrendHistory {
    const val MAX_SNAPSHOTS = 24
    const val DEDUPE_WINDOW_MS = 60_000L
    private const val PREFIX = "romverse.optimizer-history|1"
    private const val MAX_ENCODED_CHARS = 16_384

    fun healthScore(battery: Int, storage: Int, ram: Int): Int {
        require(battery in 0..100 && storage in 0..100 && ram in 0..100)
        var score = 100
        if (battery < 20) score -= 25 else if (battery < 40) score -= 10
        if (storage >= 90) score -= 30 else if (storage >= 75) score -= 15
        if (ram >= 90) score -= 20 else if (ram >= 80) score -= 10
        return score.coerceIn(0, 100)
    }

    fun needsGuidedRecovery(healthScore: Int): Boolean {
        require(healthScore in 0..100) { "Optimizer health score must be 0..100" }
        return healthScore < 85
    }

    fun append(
        existing: List<OptimizerSnapshot>,
        snapshot: OptimizerSnapshot,
    ): List<OptimizerSnapshot> {
        require(existing.size <= MAX_SNAPSHOTS) { "Optimizer history is too large" }
        existing.forEach(::validateSnapshot)
        val previous = existing.lastOrNull()
        if (
            previous != null &&
            snapshot.capturedAtEpochMs >= previous.capturedAtEpochMs &&
            snapshot.capturedAtEpochMs - previous.capturedAtEpochMs < DEDUPE_WINDOW_MS &&
            previous.copy(capturedAtEpochMs = snapshot.capturedAtEpochMs) == snapshot
        ) {
            return existing
        }
        require(previous == null || snapshot.capturedAtEpochMs > previous.capturedAtEpochMs) {
            "Optimizer timestamps must increase"
        }
        return (existing + snapshot).takeLast(MAX_SNAPSHOTS)
    }

    fun encode(snapshots: List<OptimizerSnapshot>): String {
        require(snapshots.size <= MAX_SNAPSHOTS) { "Optimizer history is too large" }
        snapshots.forEach(::validateSnapshot)
        require(snapshots.zipWithNext().all { (first, second) ->
            second.capturedAtEpochMs > first.capturedAtEpochMs
        }) { "Optimizer timestamps must increase" }
        val body = snapshots.joinToString(";") {
            "${it.capturedAtEpochMs},${it.batteryPercent},${it.storagePercent},${it.ramPercent},${it.healthScore}"
        }
        val digest = sha256("$PREFIX|$body")
        return "$PREFIX|$digest|$body"
    }

    fun decode(
        encoded: String,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): OptimizerHistoryRead {
        if (encoded.isBlank()) {
            return OptimizerHistoryRead(true, true, emptyList(), "No health trend has been saved yet")
        }
        if (encoded.length > MAX_ENCODED_CHARS) {
            return rejected("Health trend exceeds the accepted storage boundary")
        }
        val parts = encoded.split('|', limit = 4)
        if (parts.size != 4 || "${parts[0]}|${parts[1]}" != PREFIX) {
            return rejected("Health trend format is unsupported")
        }
        val expected = parts[2]
        val body = parts[3]
        if (expected.length != 64 || !expected.all { it in "0123456789abcdef" }) {
            return rejected("Health trend fingerprint is invalid")
        }
        val actual = sha256("$PREFIX|$body")
        if (!MessageDigest.isEqual(expected.toByteArray(), actual.toByteArray())) {
            return rejected("Health trend integrity mismatch")
        }
        return runCatching {
            val snapshots = if (body.isEmpty()) emptyList() else body.split(';').map(::parseSnapshot)
            require(snapshots.size <= MAX_SNAPSHOTS) { "Health trend contains too many samples" }
            require(snapshots.zipWithNext().all { (first, second) ->
                second.capturedAtEpochMs > first.capturedAtEpochMs
            }) { "Health trend timestamps are not ordered" }
            require(snapshots.all { it.capturedAtEpochMs <= nowEpochMs + 300_000L }) {
                "Health trend contains a future timestamp"
            }
            OptimizerHistoryRead(
                true,
                true,
                snapshots,
                "SHA-256 health trend integrity verified",
            )
        }.getOrElse { rejected(it.message ?: "Health trend content is invalid") }
    }

    fun migrateLegacy(
        batteryRaw: String,
        storageRaw: String,
        ramRaw: String,
        nowEpochMs: Long,
    ): OptimizerHistoryRead {
        if (batteryRaw.isBlank() && storageRaw.isBlank() && ramRaw.isBlank()) {
            return OptimizerHistoryRead(true, true, emptyList(), "No health trend has been saved yet")
        }
        return runCatching {
            val battery = parseLegacySeries(batteryRaw)
            val storage = parseLegacySeries(storageRaw)
            val ram = parseLegacySeries(ramRaw)
            val count = minOf(battery.size, storage.size, ram.size, MAX_SNAPSHOTS)
            require(count > 0) { "Legacy health trend has no complete samples" }
            val snapshots = (0 until count).map { index ->
                val batteryValue = battery[battery.size - count + index]
                val storageValue = storage[storage.size - count + index]
                val ramValue = ram[ram.size - count + index]
                OptimizerSnapshot(
                    nowEpochMs - (count - index).toLong() * DEDUPE_WINDOW_MS,
                    batteryValue,
                    storageValue,
                    ramValue,
                    healthScore(batteryValue, storageValue, ramValue),
                )
            }
            OptimizerHistoryRead(
                true,
                false,
                snapshots,
                "Legacy health trend validated and ready for integrity migration",
            )
        }.getOrElse { rejected(it.message ?: "Legacy health trend is invalid") }
    }

    private fun parseSnapshot(value: String): OptimizerSnapshot {
        val fields = value.split(',')
        require(fields.size == 5) { "Health trend sample is malformed" }
        return OptimizerSnapshot(
            fields[0].toLong(),
            fields[1].toInt(),
            fields[2].toInt(),
            fields[3].toInt(),
            fields[4].toInt(),
        )
    }

    private fun parseLegacySeries(value: String): List<Int> {
        require(value.isNotBlank() && value.length <= 4096) { "Legacy trend series is invalid" }
        return value.split(',').map {
            val parsed = it.toFloat()
            require(parsed.isFinite() && parsed in 0f..100f && parsed % 1f == 0f) {
                "Legacy trend metric is invalid"
            }
            parsed.toInt()
        }
    }

    private fun validateSnapshot(snapshot: OptimizerSnapshot) {
        OptimizerSnapshot(
            snapshot.capturedAtEpochMs,
            snapshot.batteryPercent,
            snapshot.storagePercent,
            snapshot.ramPercent,
            snapshot.healthScore,
        )
    }

    private fun rejected(reason: String) = OptimizerHistoryRead(false, false, emptyList(), reason)

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
