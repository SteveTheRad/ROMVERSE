package com.radforge.romverse.companion

import org.json.JSONObject

enum class CompanionTransferKind(
    val wireValue: String,
    val maximumBytes: Long,
    val mediaType: String,
) {
    APK(
        "apk",
        512L * 1024L * 1024L,
        "application/vnd.android.package-archive",
    ),
    REPORT(
        "report",
        64L * 1024L * 1024L,
        "application/octet-stream",
    ),
    RECOVERY_CAPSULE(
        "recovery_capsule",
        4L * 1024L * 1024L * 1024L,
        "application/vnd.romverse.recovery-capsule",
    ),
    APPROVED_PACKAGE(
        "approved_package",
        4L * 1024L * 1024L * 1024L,
        "application/vnd.romverse.approved-package",
    ),
    EMERGENCY_GUIDE(
        "emergency_guide",
        4L * 1024L * 1024L,
        "application/vnd.romverse.emergency-guide",
    ),
    ;

    companion object {
        fun fromWire(value: String): CompanionTransferKind? = entries.firstOrNull {
            it.wireValue == value
        }
    }
}

data class CompanionTransferOffer(
    val transferId: String,
    val kind: CompanionTransferKind,
    val displayName: String,
    val mediaType: String,
    val sizeBytes: Long,
    val sha256: String,
    val createdAtEpochMs: Long,
    val expiresAtEpochMs: Long,
    val downloadPath: String,
) {
    val fingerprintPreview: String
        get() = sha256.take(16)

    companion object {
        private const val MAX_OFFERS = 64
        private const val MAX_LIFETIME_MS = 7L * 24L * 60L * 60L * 1000L
        private val transferIdPattern = Regex("[0-9a-f]{32}")
        private val sha256Pattern = Regex("[0-9a-f]{64}")
        private val exactFields = setOf(
            "schema_version",
            "transfer_id",
            "kind",
            "display_name",
            "media_type",
            "size_bytes",
            "sha256",
            "created_at_epoch_ms",
            "expires_at_epoch_ms",
            "requires_phone_confirmation",
            "install_authority",
            "execution_authority",
            "download_path",
        )

        fun parseInbox(payload: JSONObject, nowEpochMs: Long): List<CompanionTransferOffer>? {
            if (payload.keys().asSequence().toSet() != setOf(
                    "protocol_version",
                    "schema_version",
                    "status",
                    "transfers",
                ) ||
                strictLong(payload.opt("protocol_version")) !=
                DesktopLinkSecurity.PROTOCOL_VERSION.toLong() ||
                strictLong(payload.opt("schema_version")) != 1L ||
                payload.opt("status") != "available"
            ) {
                return null
            }
            val rawOffers = payload.optJSONArray("transfers") ?: return null
            if (rawOffers.length() > MAX_OFFERS) return null
            return buildList {
                repeat(rawOffers.length()) { index ->
                    val offer = parse(rawOffers.optJSONObject(index) ?: return null, nowEpochMs)
                        ?: return null
                    add(offer)
                }
            }
        }

        fun parse(payload: JSONObject, nowEpochMs: Long): CompanionTransferOffer? {
            if (payload.keys().asSequence().toSet() != exactFields ||
                strictLong(payload.opt("schema_version")) != 1L ||
                payload.opt("requires_phone_confirmation") != true ||
                payload.opt("install_authority") != "none" ||
                payload.opt("execution_authority") != "none"
            ) {
                return null
            }
            val transferId = payload.opt("transfer_id") as? String ?: return null
            val kindValue = payload.opt("kind") as? String ?: return null
            val kind = CompanionTransferKind.fromWire(kindValue) ?: return null
            val displayName = payload.opt("display_name") as? String ?: return null
            val mediaType = payload.opt("media_type") as? String ?: return null
            val sha256 = payload.opt("sha256") as? String ?: return null
            val sizeBytes = strictLong(payload.opt("size_bytes")) ?: return null
            val createdAt = strictLong(payload.opt("created_at_epoch_ms")) ?: return null
            val expiresAt = strictLong(payload.opt("expires_at_epoch_ms")) ?: return null
            val downloadPath = payload.opt("download_path") as? String ?: return null
            if (
                !transferIdPattern.matches(transferId) ||
                !sha256Pattern.matches(sha256) ||
                displayName.length !in 1..160 ||
                displayName != displayName.substringAfterLast('/').substringAfterLast('\\') ||
                displayName.any(Char::isISOControl) ||
                mediaType != kind.mediaType ||
                sizeBytes !in 1..kind.maximumBytes ||
                createdAt <= 0L ||
                expiresAt <= createdAt ||
                expiresAt - createdAt > MAX_LIFETIME_MS ||
                expiresAt <= nowEpochMs ||
                downloadPath != "/companion/transfers/$transferId/content"
            ) {
                return null
            }
            return CompanionTransferOffer(
                transferId,
                kind,
                displayName,
                mediaType,
                sizeBytes,
                sha256,
                createdAt,
                expiresAt,
                downloadPath,
            )
        }

        private fun strictLong(value: Any?): Long? = when (value) {
            is Int -> value.toLong()
            is Long -> value
            else -> null
        }
    }
}
