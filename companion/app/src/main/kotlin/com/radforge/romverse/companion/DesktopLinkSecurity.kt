package com.radforge.romverse.companion

import java.net.URI
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

internal object DesktopLinkSecurity {
    const val PROTOCOL_VERSION = 3
    const val MAX_REMEMBERED_SESSION_SECONDS = 30L * 24L * 60L * 60L

    fun normalizeFingerprint(value: String): String? {
        val normalized = value
            .filterNot { it == ':' || it == '-' || it.isWhitespace() }
            .lowercase()
        return normalized.takeIf {
            it.length == 64 && it.all { character -> character in '0'..'9' || character in 'a'..'f' }
        }
    }

    fun safetyCode(fingerprint: String): String? = normalizeFingerprint(fingerprint)
        ?.take(24)
        ?.uppercase()
        ?.chunked(4)
        ?.joinToString("-")

    fun isCurrentSession(
        protocolVersion: Int,
        fingerprint: String,
        expiresAtEpochMs: Long,
        nowEpochMs: Long,
    ): Boolean = protocolVersion == PROTOCOL_VERSION &&
        normalizeFingerprint(fingerprint) != null &&
        expiresAtEpochMs > nowEpochMs

    fun isRememberedDesktop(
        protocolVersion: Int,
        fingerprint: String,
        host: String,
    ): Boolean = protocolVersion == PROTOCOL_VERSION &&
        normalizeFingerprint(fingerprint) != null &&
        isValidEndpointHost(host)

    fun trustedRediscoveredEndpoint(
        protocolVersion: Int,
        rememberedFingerprint: String?,
        advertisedFingerprint: String,
        host: String,
        authenticatedSessionProof: Boolean,
    ): String? = host.takeIf {
        protocolVersion == PROTOCOL_VERSION &&
            rememberedFingerprint != null &&
            acceptsDiscoveredIdentity(rememberedFingerprint, advertisedFingerprint) &&
            isValidEndpointHost(host) &&
            authenticatedSessionProof
    }

    fun acceptsDiscoveredIdentity(
        rememberedFingerprint: String?,
        advertisedFingerprint: String,
    ): Boolean {
        val advertised = normalizeFingerprint(advertisedFingerprint) ?: return false
        val remembered = rememberedFingerprint?.let(::normalizeFingerprint) ?: return true
        return MessageDigest.isEqual(
            advertised.toByteArray(Charsets.US_ASCII),
            remembered.toByteArray(Charsets.US_ASCII),
        )
    }

    fun retryDelayMillis(failedAttempts: Int): Long {
        val delays = longArrayOf(2_000L, 5_000L, 10_000L, 20_000L, 30_000L, 60_000L)
        return delays[failedAttempts.coerceIn(0, delays.lastIndex)]
    }

    fun isValidEndpointHost(host: String): Boolean = runCatching {
        require(host.length in 3..255)
        require(host.none { it.isWhitespace() || it in "@/\\?#" })
        val endpoint = URI("https://$host")
        require(endpoint.scheme == "https")
        require(endpoint.rawUserInfo == null)
        require(endpoint.rawPath.isNullOrEmpty())
        require(endpoint.rawQuery == null && endpoint.rawFragment == null)
        require(!endpoint.host.isNullOrBlank())
        require(endpoint.port in 1..65535)
        true
    }.getOrDefault(false)

    fun configure(connection: HttpsURLConnection, fingerprint: String) {
        val expected = normalizeFingerprint(fingerprint)
            ?: throw CertificateException("Invalid ROMVERSE Link certificate fingerprint")
        val trustManager = PinnedTrustManager(expected)
        val context = SSLContext.getInstance("TLSv1.2").apply {
            init(null, arrayOf(trustManager), SecureRandom())
        }
        connection.sslSocketFactory = context.socketFactory
        connection.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, session ->
            runCatching {
                val certificates = session.peerCertificates
                certificates.size == 1 && trustManager.matches(certificates[0] as X509Certificate)
            }.getOrDefault(false)
        }
    }

    private class PinnedTrustManager(private val expected: String) : X509TrustManager {
        override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            throw CertificateException("ROMVERSE Link does not accept client certificates")
        }

        override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
            if (chain == null || chain.size != 1) {
                throw CertificateException("ROMVERSE Link certificate chain is invalid")
            }
            chain[0].checkValidity()
            if (!matches(chain[0])) {
                throw CertificateException("ROMVERSE Link certificate pin does not match")
            }
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()

        fun matches(certificate: X509Certificate): Boolean {
            val observed = MessageDigest.getInstance("SHA-256").digest(certificate.encoded)
            val expectedBytes = expected.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            return MessageDigest.isEqual(observed, expectedBytes)
        }
    }
}
