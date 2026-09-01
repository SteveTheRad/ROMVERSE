package com.radforge.romverse.companion

import java.net.URI
import org.json.JSONObject

data class CompanionMembersConfig(
    val issuer: String,
    val clientId: String,
    val scope: String = "openid profile email offline_access",
) {
    fun validated(): CompanionMembersConfig {
        val cleanIssuer = trustedMembersUrl(issuer, "Members issuer").trimEnd('/')
        val cleanClient = clientId.trim()
        require(cleanClient.isNotEmpty() && cleanClient.length <= 200 && cleanClient.none(Char::isWhitespace)) {
            "The Members client ID is missing or invalid."
        }
        val scopes = scope.split(Regex("\\s+")).filter(String::isNotBlank).distinct()
        require("openid" in scopes && scopes.size <= 12) {
            "The Members scope must be bounded and include openid."
        }
        return copy(issuer = cleanIssuer, clientId = cleanClient, scope = scopes.joinToString(" "))
    }
}

data class CompanionMembersDiscovery(
    val issuer: String,
    val deviceEndpoint: String,
    val tokenEndpoint: String,
    val userInfoEndpoint: String,
) {
    companion object {
        fun parse(payload: JSONObject, expectedIssuer: String): CompanionMembersDiscovery {
            val issuer = payload.requireBoundedString("issuer", 2048).trimEnd('/')
            require(issuer == expectedIssuer.trimEnd('/')) {
                "The Members issuer identity does not match its discovery record."
            }
            return CompanionMembersDiscovery(
                issuer,
                trustedMembersUrl(
                    payload.requireBoundedString("device_authorization_endpoint", 4096),
                    "Device authorization endpoint",
                ),
                trustedMembersUrl(
                    payload.requireBoundedString("token_endpoint", 4096),
                    "Token endpoint",
                ),
                trustedMembersUrl(
                    payload.requireBoundedString("userinfo_endpoint", 4096),
                    "User profile endpoint",
                ),
            )
        }
    }
}

data class CompanionDeviceAuthorization(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val verificationUriComplete: String,
    val expiresAtEpochMs: Long,
    val intervalSeconds: Int,
) {
    companion object {
        fun parse(payload: JSONObject, nowEpochMs: Long): CompanionDeviceAuthorization {
            val expires = payload.requireBoundedInt("expires_in", 60, 1800)
            val interval = if (payload.has("interval")) {
                payload.requireBoundedInt("interval", 2, 30)
            } else {
                5
            }
            val complete = payload.optString("verification_uri_complete").trim().let {
                if (it.isBlank()) "" else trustedMembersUrl(it, "Complete verification URL")
            }
            return CompanionDeviceAuthorization(
                payload.requireBoundedString("device_code", 4096),
                payload.requireBoundedString("user_code", 80),
                trustedMembersUrl(
                    payload.requireBoundedString("verification_uri", 4096),
                    "Verification URL",
                ),
                complete,
                nowEpochMs + expires * 1000L,
                interval,
            )
        }
    }
}

data class CompanionMemberProfile(
    val subject: String,
    val displayName: String,
    val email: String,
    val plan: String,
    val status: String,
    val trialEndsAt: String,
    val renewsAt: String,
) {
    companion object {
        fun parse(payload: JSONObject): CompanionMemberProfile {
            val membership = payload.optJSONObject("romverse_membership") ?: JSONObject()
            val status = membership.optString("status").trim().lowercase().let {
                if (it in setOf("active", "trial", "past_due", "inactive", "unverified")) {
                    it
                } else {
                    "unverified"
                }
            }
            return CompanionMemberProfile(
                payload.requireBoundedString("sub", 240),
                payload.optionalBoundedString("name", 160).ifBlank { "ROMVERSE Member" },
                payload.optionalBoundedString("email", 320),
                membership.optionalBoundedString("plan", 120).ifBlank { "No verified plan" },
                status,
                membership.optionalBoundedString("trial_ends_at", 80),
                membership.optionalBoundedString("renews_at", 80),
            )
        }
    }
}

data class CompanionMemberSession(
    val accessToken: String,
    val expiresAtEpochMs: Long,
    val profile: CompanionMemberProfile,
)

internal fun trustedMembersUrl(value: String, label: String): String {
    require(value.length <= 4096) { "$label is too long." }
    val uri = runCatching { URI(value.trim()) }.getOrElse {
        throw IllegalArgumentException("$label is invalid.")
    }
    require(
        uri.scheme == "https" &&
            !uri.host.isNullOrBlank() &&
            uri.userInfo == null &&
            uri.fragment == null
    ) { "$label must be a clean HTTPS URL." }
    val host = uri.host.lowercase().trimEnd('.')
    require(host != "localhost" && !host.endsWith(".localhost") && !isPrivateLiteral(host)) {
        "$label cannot use a private or local address."
    }
    return uri.toASCIIString()
}

private fun isPrivateLiteral(host: String): Boolean {
    val parts = host.split('.')
    if (parts.size != 4 || parts.any { it.toIntOrNull() !in 0..255 }) return false
    val first = parts[0].toInt()
    val second = parts[1].toInt()
    return first == 10 || first == 127 ||
        (first == 169 && second == 254) ||
        (first == 172 && second in 16..31) ||
        (first == 192 && second == 168)
}

private fun JSONObject.requireBoundedString(name: String, maximum: Int): String {
    val value = optString(name).trim()
    require(value.isNotEmpty() && value.length <= maximum) {
        "The Members response is missing $name."
    }
    return value
}

private fun JSONObject.optionalBoundedString(name: String, maximum: Int): String {
    val value = optString(name).trim()
    return if (value.length <= maximum) value else ""
}

private fun JSONObject.requireBoundedInt(name: String, minimum: Int, maximum: Int): Int {
    require(has(name) && !isNull(name)) { "The Members response is missing $name." }
    val value = get(name)
    require(value is Number && value.toInt() in minimum..maximum) {
        "The Members $name is outside the safe boundary."
    }
    return value.toInt()
}
