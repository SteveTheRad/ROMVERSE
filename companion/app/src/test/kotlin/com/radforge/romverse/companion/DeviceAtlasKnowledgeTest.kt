package com.radforge.romverse.companion

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceAtlasKnowledgeTest {
    @Test
    fun resolvesKnownManufacturerWithoutGrantingAuthority() {
        val pack = CompanionDeviceAtlas.resolve(" Google ")

        assertEquals("google.pixel", pack.packId)
        assertTrue(pack.sources.isNotEmpty())
        assertTrue(pack.reportText().contains("Execution authority: NONE"))
    }

    @Test
    fun resolvesNewOemKnowledgeWithoutGrantingAuthority() {
        val expected = mapOf(
            "OPPO" to "oppo.coloros",
            "realme" to "realme.ui",
            "Nothing" to "nothing.os",
            "vivo" to "vivo.funtouch-iqoo",
            "iQOO" to "vivo.funtouch-iqoo",
            "ASUS" to "asus.rog-android",
            "HUAWEI" to "huawei.emui-harmonyos",
            "HONOR" to "honor.magicos",
            "HMD Global" to "hmd.nokia-android",
            "Nokia" to "hmd.nokia-android",
            "TECNO" to "transsion.android",
            "Infinix" to "transsion.android",
            "itel" to "transsion.android",
            "ZTE" to "zte.nubia-android",
            "nubia" to "zte.nubia-android",
            "REDMAGIC" to "zte.nubia-android",
            "Fairphone" to "fairphone.android",
        )

        expected.forEach { (manufacturer, packId) ->
            val pack = CompanionDeviceAtlas.resolve(manufacturer)
            assertEquals(packId, pack.packId)
            assertTrue(pack.sources.isNotEmpty())
            assertTrue(pack.boundary.isNotBlank())
            assertTrue(pack.reportText().contains("Execution authority: NONE"))
        }
    }

    @Test
    fun unknownManufacturerFallsBackToGenericReadOnlyKnowledge() {
        val pack = CompanionDeviceAtlas.resolve("Example OEM")

        assertEquals("android.generic", pack.packId)
        assertTrue(pack.boundary.contains("read-only"))
    }

    @Test
    fun prefersExactPublishedPixelIdentityOverBroadOemPack() {
        val pack = CompanionDeviceAtlas.resolve("Google", "Pixel 9 Pro", "caiman")

        assertEquals("google.pixel.tensor-gki", pack.packId)
        assertTrue(pack.productPatterns.contains("caiman"))
    }

    @Test
    fun prefersExactPublishedSonyOpenDevicesIdentity() {
        val pack = CompanionDeviceAtlas.resolve("Sony", "XQ-TEST", "pdx215")

        assertEquals("sony.xperia.open-devices.identity", pack.packId)
        assertTrue(pack.reportText().contains("Execution authority: NONE"))
    }

    @Test
    fun resolvesExactPhysicallyValidatedIdentityWithoutGrantingBuildAuthority() {
        val identity = CompanionDeviceAtlas.identify("Xiaomi", "2509FPN0BC", "popsicle")

        assertEquals("Xiaomi 17 Pro Max", identity.displayName)
        assertTrue(identity.verifiedExact)
        assertTrue(identity.evidence.contains("xiaomi.popsicle.hyperos4.os4.0.0.23"))
        assertEquals("2509FPN0BC", identity.rawModel)
    }

    @Test
    fun resolvesExactObservedS24UltraIdentityWithoutGrantingBuildAuthority() {
        val identity = CompanionDeviceAtlas.identify("samsung", "SM-S928B", "e3q")
        val pack = CompanionDeviceAtlas.resolve("samsung", "SM-S928B", "e3q")
        val sibling = CompanionDeviceAtlas.resolve("samsung", "SM-S928U1", "e3q")

        assertEquals("Samsung Galaxy S24 Ultra", identity.displayName)
        assertTrue(identity.verifiedExact)
        assertTrue(identity.evidence.contains("samsung.galaxy-s24-ultra.sm-s928b"))
        assertEquals("samsung.galaxy-s24-ultra.sm-s928b", pack.packId)
        assertTrue(pack.reportText().contains("Execution authority: NONE"))
        assertEquals("samsung.oneui", sibling.packId)
    }

    @Test
    fun unknownMarketingIdentityKeepsReportedModelExplicitlyUnconfirmed() {
        val identity = CompanionDeviceAtlas.identify("Example", "ABC-123", "example")

        assertEquals("Example ABC-123", identity.displayName)
        assertTrue(!identity.verifiedExact)
        assertTrue(identity.evidence.contains("unconfirmed"))
    }

    @Test
    fun emulatorMarkersNeverMasqueradeAsAPhysicalGoogleDevice() {
        val identity = CompanionDeviceAtlas.identify(
            "Google",
            "sdk_gphone64_x86_64",
            "emu64xa",
        )
        val resolution = CompanionDeviceAtlas.resolveDetailed(
            "Google",
            "sdk_gphone64_x86_64",
            "emu64xa",
        )

        assertEquals("Android Emulator", identity.displayName)
        assertTrue(!identity.verifiedExact)
        assertTrue(identity.evidence.contains("emulator"))
        assertEquals("android.generic", resolution.pack.packId)
        assertTrue(resolution.reason.contains("without claiming physical-device compatibility"))
    }

    @Test
    fun unknownSonyProductFallsBackToBroadReadOnlyPack() {
        val pack = CompanionDeviceAtlas.resolve("Sony", "Unknown Xperia", "unknown-product")

        assertEquals("sony.xperia", pack.packId)
    }

    @Test
    fun equalPriorityCollisionFallsBackAndReportsAmbiguity() {
        val sony = CompanionDeviceAtlas.resolve("Sony")
        val first = sony.copy(packId = "sony.conflict.one", priority = 999)
        val second = sony.copy(packId = "sony.conflict.two", priority = 999)
        val generic = CompanionDeviceAtlas.resolve("Unknown OEM")

        val resolution = CompanionDeviceAtlas.resolveFromCatalog(
            "Sony",
            "XQ-TEST",
            "unknown",
            listOf(first, second),
            generic,
        )

        assertTrue(resolution.ambiguous)
        assertTrue(!resolution.matched)
        assertEquals("android.generic", resolution.pack.packId)
        assertTrue(resolution.reportText().contains("RESOLUTION BLOCKED"))
        assertTrue(resolution.reportText().contains("sony.conflict.one"))
    }

    @Test
    fun sourceFreshnessIsDeterministicAndVisible() {
        val source = CompanionDeviceAtlas.resolve("Google").sources.first()

        assertTrue(!source.isStale(LocalDate.of(2026, 12, 1)))
        assertTrue(source.isStale(LocalDate.of(2027, 3, 1)))
    }

    @Test
    fun exposesIntegrityCheckedCatalogHealth() {
        val status = CompanionDeviceAtlas.catalogStatus()

        assertTrue(status.contains("integrity-checked Packs"))
        assertTrue(status.contains("authoritative references"))
        assertTrue(status.contains("sources current"))
    }

    @Test
    fun searchesCatalogAcrossOemCodenameAndAuthoritativeSourceText() {
        assertEquals(
            setOf("samsung.galaxy-s24-ultra.sm-s928b", "samsung.oneui"),
            CompanionDeviceAtlas.search("Knox").map { it.packId }.toSet(),
        )
        assertEquals(
            "google.pixel.tensor-gki",
            CompanionDeviceAtlas.search("caiman").single().packId,
        )
        assertTrue(
            CompanionDeviceAtlas.search("verified boot").any { it.packId == "android.generic" },
        )
        val catalog = CompanionDeviceAtlas.search("")
        assertEquals(GeneratedDeviceAtlasPacks.catalogPackCount, catalog.size)
        assertEquals(catalog.map { it.priority }.sortedDescending(), catalog.map { it.priority })
        assertEquals(catalog.size, catalog.map { it.packId }.distinct().size)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnboundedAtlasSearchResultLimit() {
        CompanionDeviceAtlas.search("android", limit = 51)
    }
}
