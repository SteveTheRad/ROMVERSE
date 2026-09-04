package com.radforge.romverse.companion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CompanionTransferOfferTest {
    private val now = 1_800_000_000_000L

    private fun offer(): JSONObject = JSONObject()
        .put("schema_version", 1)
        .put("transfer_id", "a".repeat(32))
        .put("kind", "apk")
        .put("display_name", "ROMVERSE-Companion.apk")
        .put("media_type", "application/vnd.android.package-archive")
        .put("size_bytes", 2048L)
        .put("sha256", "b".repeat(64))
        .put("created_at_epoch_ms", now)
        .put("expires_at_epoch_ms", now + 86_400_000L)
        .put("requires_phone_confirmation", true)
        .put("install_authority", "none")
        .put("execution_authority", "none")
        .put("download_path", "/companion/transfers/${"a".repeat(32)}/content")

    private fun inbox(vararg offers: JSONObject): JSONObject = JSONObject()
        .put("protocol_version", DesktopLinkSecurity.PROTOCOL_VERSION)
        .put("schema_version", 1)
        .put("status", "available")
        .put("transfers", JSONArray(offers.toList()))

    @Test
    fun parsesExactDownloadOnlyOffer() {
        val result = CompanionTransferOffer.parseInbox(inbox(offer()), now - 1L)

        assertEquals(1, result?.size)
        assertEquals(CompanionTransferKind.APK, result?.single()?.kind)
        assertEquals("b".repeat(16), result?.single()?.fingerprintPreview)
    }

    @Test
    fun rejectsAuthorityWideningPathsExpiryAndUnknownFields() {
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("execution_authority", "install")),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("download_path", "https://evil.invalid/payload")),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("expires_at_epoch_ms", now - 1L)),
                now,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("unexpected", true)),
                now - 1L,
            ),
        )
    }

    @Test
    fun rejectsWrongMediaTypeTraversalAndOversizedApk() {
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("media_type", "text/html")),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("display_name", "../Companion.apk")),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("size_bytes", 513L * 1024L * 1024L)),
                now - 1L,
            ),
        )
    }

    @Test
    fun rejectsJsonTypeConfusion() {
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer()).put("schema_version", "1"),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("requires_phone_confirmation", "true")),
                now - 1L,
            ),
        )
        assertNull(
            CompanionTransferOffer.parseInbox(
                inbox(offer().put("size_bytes", "2048")),
                now - 1L,
            ),
        )
    }
}
