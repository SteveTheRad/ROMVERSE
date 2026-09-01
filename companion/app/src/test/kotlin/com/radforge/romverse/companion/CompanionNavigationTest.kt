package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionNavigationTest {
    @Test
    fun `home is the single bottom-left route`() {
        val allVisibleRoutes = CompanionNavigation.bottomDestinations + CompanionNavigation.drawerDestinations

        assertEquals(CompanionDestination.HOME, CompanionNavigation.bottomDestinations.first())
        assertEquals(1, allVisibleRoutes.count { it == CompanionDestination.HOME })
        assertFalse(CompanionNavigation.drawerDestinations.contains(CompanionDestination.HOME))
    }

    @Test
    fun `primary and drawer navigation preserve every functional destination`() {
        val expected = CompanionDestination.entries.toSet() - CompanionDestination.MORE

        assertEquals(expected, CompanionNavigation.navigableDestinations.toSet())
        assertTrue(CompanionNavigation.bottomDestinations.contains(CompanionDestination.LIVE_CONSOLE))
        assertTrue(CompanionNavigation.bottomDestinations.contains(CompanionDestination.VITALIS))
        assertTrue(CompanionNavigation.drawerDestinations.contains(CompanionDestination.LIFELINE))
        assertTrue(CompanionNavigation.drawerDestinations.contains(CompanionDestination.DEVICE_DNA))
        assertTrue(
            CompanionNavigation.drawerDestinations.contains(
                CompanionDestination.ASCENSION_PROTOCOL,
            ),
        )
        assertTrue(CompanionNavigation.drawerDestinations.contains(CompanionDestination.GALAXY))
    }

    @Test
    fun `every visible and nested route has a stable activity restoration token`() {
        val sectionRoutes = CompanionRoute.entries.filter { it.sectionTitle != null }

        sectionRoutes.forEach { route ->
            assertEquals(route, CompanionRoute.fromSectionTitle(route.sectionTitle!!))
            assertEquals(route, CompanionRoute.fromSavedToken(route.name))
            assertTrue(route.restoredDetail.isNotBlank())
        }
        assertEquals(CompanionRoute.HOME, CompanionRoute.fromSavedToken("tampered-route"))
        assertEquals(CompanionRoute.HOME, CompanionRoute.fromSavedToken(null))
    }

    @Test
    fun `restored evidence routes hydrate once when their link snapshot arrives`() {
        assertTrue(
            CompanionRoute.LIVE_CONSOLE.needsTelemetryHydration(
                hasAscension = true,
                hasLiveConsole = false,
                hasDeviceDna = true,
            ),
        )
        assertTrue(
            CompanionRoute.DEVICE_DNA.needsTelemetryHydration(
                hasAscension = true,
                hasLiveConsole = true,
                hasDeviceDna = false,
            ),
        )
        assertTrue(
            CompanionRoute.ASCENSION_PROTOCOL.needsTelemetryHydration(
                hasAscension = false,
                hasLiveConsole = true,
                hasDeviceDna = true,
            ),
        )
        assertFalse(
            CompanionRoute.LIVE_CONSOLE.needsTelemetryHydration(
                hasAscension = true,
                hasLiveConsole = true,
                hasDeviceDna = true,
            ),
        )
        assertFalse(
            CompanionRoute.HOME.needsTelemetryHydration(
                hasAscension = false,
                hasLiveConsole = false,
                hasDeviceDna = false,
            ),
        )
    }
}
