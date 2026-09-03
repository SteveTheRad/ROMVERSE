package com.radforge.romverse.companion

internal data class CompanionUsbPairingAssist(
    val host: String,
    val certificateSha256: String,
    val pairingCode: String,
)

/** Strict, in-memory contract for a user-started Desktop USB pairing handoff. */
internal object CompanionUsbPairingAssistPolicy {
    const val ACTION = "com.radforge.romverse.companion.action.USB_PAIR"
    const val HOST_EXTRA = "romverse_link_host"
    const val FINGERPRINT_EXTRA = "romverse_link_fingerprint"
    const val CODE_EXTRA = "romverse_link_code"

    fun parse(
        action: String?,
        host: String?,
        fingerprint: String?,
        pairingCode: String?,
    ): CompanionUsbPairingAssist? {
        if (action != ACTION) return null
        val normalizedHost = host?.trim().orEmpty()
        val match = LOOPBACK_ENDPOINT.matchEntire(normalizedHost) ?: return null
        val port = match.groupValues[1].toIntOrNull() ?: return null
        if (port !in 1..65_535 || !DesktopLinkSecurity.isValidEndpointHost(normalizedHost)) {
            return null
        }
        val normalizedFingerprint = DesktopLinkSecurity.normalizeFingerprint(
            fingerprint.orEmpty(),
        ) ?: return null
        val normalizedCode = pairingCode.orEmpty().filterNot(Char::isWhitespace)
        if (normalizedCode.length != 6 || !normalizedCode.all(Char::isDigit)) return null
        return CompanionUsbPairingAssist(
            host = normalizedHost,
            certificateSha256 = normalizedFingerprint,
            pairingCode = normalizedCode,
        )
    }

    private val LOOPBACK_ENDPOINT = Regex("^127\\.0\\.0\\.1:([0-9]{1,5})$")
}
