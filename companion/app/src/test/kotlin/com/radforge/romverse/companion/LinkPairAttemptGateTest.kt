package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LinkPairAttemptGateTest {
    @Test
    fun `reset and newer attempt prevent an older result from restoring state`() {
        val gate = LinkPairAttemptGate()
        var buttonCopy = "CONNECTING…"
        var sessionToken: String? = null
        val pairingPreferences = mutableMapOf<String, Any>()
        val olderAttempt = gate.begin()

        gate.invalidate()
        buttonCopy = "CONNECT WIRELESSLY"
        sessionToken = null
        pairingPreferences.clear()

        val staleTimeoutApplied = gate.runIfCurrent(olderAttempt) {
            buttonCopy = "APPROVAL TIMEOUT • TRY AGAIN"
        }
        val staleApprovalApplied = gate.runIfCurrent(olderAttempt) {
            buttonCopy = "PAIRED"
            sessionToken = "stale-token"
            pairingPreferences["paired"] = true
        }

        assertFalse(staleTimeoutApplied)
        assertFalse(staleApprovalApplied)
        assertEquals("CONNECT WIRELESSLY", buttonCopy)
        assertNull(sessionToken)
        assertTrue(pairingPreferences.isEmpty())

        val newerAttempt = gate.begin()
        assertFalse(gate.runIfCurrent(olderAttempt) { buttonCopy = "STALE" })
        assertTrue(gate.runIfCurrent(newerAttempt) { buttonCopy = "WAITING FOR PC APPROVAL" })
        assertEquals("WAITING FOR PC APPROVAL", buttonCopy)

        gate.close()
        assertFalse(gate.runIfCurrent(newerAttempt) { buttonCopy = "PAIRED" })
        assertEquals("WAITING FOR PC APPROVAL", buttonCopy)
    }
}
