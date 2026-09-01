package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OptimizerHistoryTest {
    private fun snapshot(time: Long, battery: Int = 80, storage: Int = 40, ram: Int = 50) =
        OptimizerSnapshot(
            time,
            battery,
            storage,
            ram,
            OptimizerTrendHistory.healthScore(battery, storage, ram),
        )

    @Test
    fun `history round trip verifies one atomic aligned timeline`() {
        val snapshots = listOf(snapshot(1_000), snapshot(2_000, battery = 79, ram = 55))
        val encoded = OptimizerTrendHistory.encode(snapshots)
        val decoded = OptimizerTrendHistory.decode(encoded, nowEpochMs = 10_000)

        assertTrue(decoded.valid)
        assertTrue(decoded.integrityVerified)
        assertEquals(snapshots, decoded.snapshots)
        assertTrue(decoded.reason.contains("integrity verified"))
    }

    @Test
    fun `empty verified history round trips without inventing samples`() {
        val encoded = OptimizerTrendHistory.encode(emptyList())
        val fingerprint = encoded.split('|')[2]
        val decoded = OptimizerTrendHistory.decode(encoded, nowEpochMs = 10_000)

        assertEquals(64, fingerprint.length)
        assertTrue(decoded.valid)
        assertTrue(decoded.integrityVerified)
        assertTrue(decoded.snapshots.isEmpty())
    }

    @Test
    fun `tampered trend is rejected without returning partial data`() {
        val encoded = OptimizerTrendHistory.encode(listOf(snapshot(1_000)))
        val tampered = encoded.replace(",80,", ",10,")
        val decoded = OptimizerTrendHistory.decode(tampered, nowEpochMs = 10_000)

        assertFalse(decoded.valid)
        assertFalse(decoded.integrityVerified)
        assertTrue(decoded.snapshots.isEmpty())
        assertTrue(decoded.reason.contains("integrity mismatch"))
    }

    @Test
    fun `identical sample inside dedupe window does not pollute graph`() {
        val initial = listOf(snapshot(1_000))
        val result = OptimizerTrendHistory.append(initial, snapshot(30_000))
        assertEquals(initial, result)
    }

    @Test
    fun `history stays bounded to newest samples`() {
        val snapshots = (1L..30L).fold(emptyList<OptimizerSnapshot>()) { history, index ->
            OptimizerTrendHistory.append(history, snapshot(index * 100_000L, battery = 50 + index.toInt() % 20))
        }
        assertEquals(OptimizerTrendHistory.MAX_SNAPSHOTS, snapshots.size)
        assertEquals(700_000L, snapshots.first().capturedAtEpochMs)
        assertEquals(3_000_000L, snapshots.last().capturedAtEpochMs)
    }

    @Test
    fun `legacy aligned series migrate without claiming prior integrity`() {
        val migrated = OptimizerTrendHistory.migrateLegacy(
            "80.0,79.0",
            "40.0,41.0",
            "50.0,51.0",
            nowEpochMs = 1_000_000L,
        )
        assertTrue(migrated.valid)
        assertFalse(migrated.integrityVerified)
        assertEquals(2, migrated.snapshots.size)
        assertEquals(79, migrated.snapshots.last().batteryPercent)
        assertTrue(OptimizerTrendHistory.decode(OptimizerTrendHistory.encode(migrated.snapshots), 1_000_000L).integrityVerified)
    }

    @Test
    fun `malformed legacy data is rejected instead of silently dropped`() {
        val migrated = OptimizerTrendHistory.migrateLegacy(
            "80.0,bad",
            "40.0,41.0",
            "50.0,51.0",
            nowEpochMs = 1_000_000L,
        )
        assertFalse(migrated.valid)
        assertTrue(migrated.snapshots.isEmpty())
    }

    @Test
    fun `future timestamps and evidence score mismatch are rejected`() {
        val future = OptimizerTrendHistory.encode(listOf(snapshot(1_000_000)))
        assertFalse(OptimizerTrendHistory.decode(future, nowEpochMs = 1_000).valid)
        assertTrue(
            runCatching {
                OptimizerSnapshot(1_000, 80, 40, 50, 1)
            }.isFailure
        )
    }

    @Test
    fun `guided recovery is offered only when health needs attention`() {
        assertFalse(OptimizerTrendHistory.needsGuidedRecovery(100))
        assertFalse(OptimizerTrendHistory.needsGuidedRecovery(85))
        assertTrue(OptimizerTrendHistory.needsGuidedRecovery(84))
        assertTrue(OptimizerTrendHistory.needsGuidedRecovery(0))
        assertTrue(runCatching { OptimizerTrendHistory.needsGuidedRecovery(101) }.isFailure)
    }
}
