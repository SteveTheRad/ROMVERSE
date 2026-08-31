package com.radforge.romverse.companion

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CompanionUpgradeContinuityInstrumentedTest {
    @Test
    fun seedOrVerifyPrivateStateAcrossRequestedUpdateFixture() {
        val phase = InstrumentationRegistry.getArguments()
            .getString(ARGUMENT_PHASE)
            .orEmpty()
        if (phase.isBlank()) return

        val context = InstrumentationRegistry.getInstrumentation().targetContext
        when (phase) {
            PHASE_SEED -> seed(context)
            PHASE_VERIFY -> verify(context)
            else -> error("Unknown Companion update-continuity phase")
        }
    }

    private fun seed(context: Context) {
        val now = System.currentTimeMillis()
        context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
            .edit()
            .clear()
            .putString("preferred_display_name", EXPECTED_NAME)
            .putString("experience_mode", CompanionExperienceMode.EXPERT.persistedValue)
            .putString("display_mode", CompanionDisplayMode.COSMIC.persistedValue)
            .putBoolean("reduced_motion", true)
            .putBoolean("privacy_curtain_enabled", false)
            .putBoolean("online_intelligence_enabled", true)
            .commit()
            .also(::assertTrue)

        val activity = JSONObject()
            .put("schema_version", 1)
            .put("privacy", "private-local")
            .put(
                "events",
                JSONArray().put(
                    JSONObject()
                        .put("event_id", "upgrade-event")
                        .put("recorded_at_epoch_ms", now - 5_000L)
                        .put("title", EXPECTED_ACTIVITY)
                        .put("source", "ROMVERSE Companion")
                        .put("outcome", "success")
                        .put("dedupe_key", "upgrade-continuity"),
                ),
            )
        preserve(context, "activity", "events_v1", activity.toString())

        val topic = GalaxyTopicData(
            id = "upgrade-topic",
            title = EXPECTED_TOPIC,
            body = "Private local topic preserved across an APK update.",
            createdAt = now - 4_000L,
            vote = 1,
            replies = listOf(
                GalaxyReplyData(
                    "upgrade-reply",
                    "Private local reply preserved.",
                    now - 3_000L,
                ),
            ),
        )
        val topicJson = JSONObject()
            .put("id", topic.id)
            .put("title", topic.title)
            .put("body", topic.body)
            .put("created_at", topic.createdAt)
            .put("vote", topic.vote)
            .put(
                "comments",
                JSONArray().put(
                    JSONObject()
                        .put("id", topic.replies.single().id)
                        .put("body", topic.replies.single().body)
                        .put("created_at", topic.replies.single().createdAt),
                ),
            )
        val galaxy = JSONObject()
            .put("format", "romverse.galaxy.community")
            .put("schema_version", 1)
            .put("mode", "offline-local")
            .put("integrity_version", GalaxyRules.INTEGRITY_VERSION)
            .put("community_digest", GalaxyRules.communityDigest(listOf(topic)))
            .put("exported_at", now)
            .put("topics", JSONArray().put(topicJson))
        preserve(context, "community", "topics_v1", galaxy.toString())

        val optimizer = OptimizerSnapshot(
            capturedAtEpochMs = now - 2_000L,
            batteryPercent = 77,
            storagePercent = 55,
            ramPercent = 40,
            healthScore = OptimizerTrendHistory.healthScore(77, 55, 40),
        )
        preserve(
            context,
            "optimizer_history",
            "history_v1",
            OptimizerTrendHistory.encode(listOf(optimizer)),
        )

        val lifeline = LifelineSessionSnapshot(
            sessionId = "upgrade-lifeline",
            createdAtEpochMs = now - 2_000L,
            updatedAtEpochMs = now - 1_000L,
            status = "active",
            baselineScore = 82,
            baselineFindings = listOf("Upgrade continuity baseline"),
            checkpoints = listOf(
                "Review the original local baseline.",
                "Run a fresh read-only comparison after the update.",
            ),
            reviewed = listOf(false, false),
        )
        val lifelineJson = JSONObject()
            .put("schema_version", 3)
            .put("privacy", "private-local")
            .put("session_id", lifeline.sessionId)
            .put("created_at_epoch_ms", lifeline.createdAtEpochMs)
            .put("updated_at_epoch_ms", lifeline.updatedAtEpochMs)
            .put("status", lifeline.status)
            .put("baseline_score", lifeline.baselineScore)
            .put("baseline_findings", JSONArray(lifeline.baselineFindings))
            .put("checkpoints", JSONArray(lifeline.checkpoints))
            .put("reviewed", JSONArray(lifeline.reviewed))
            .put("device_modified", false)
            .put("session_digest", LifelineSessionIntegrity.digest(lifeline))
        preserve(context, "repair_session", "session_v1", lifelineJson.toString())

        val pairing = context.getSharedPreferences(
            LinkSessionVault.PREFERENCES_NAME,
            Context.MODE_PRIVATE,
        )
        LinkSessionVault(context, pairing).clear()
        pairing.edit()
            .clear()
            .putBoolean("paired", true)
            .putBoolean("desktop_trusted", true)
            .putString("paired_host", "127.0.0.1:65535")
            .putString("certificate_sha256", "a".repeat(64))
            .putInt("link_protocol_version", 3)
            .putLong("session_expires_at_epoch_ms", now + 24L * 60L * 60L * 1_000L)
            .commit()
            .also(::assertTrue)
        assertTrue(LinkSessionVault(context, pairing).store(EXPECTED_LINK_TOKEN))
    }

    private fun verify(context: Context) {
        val settings = context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
        assertEquals(EXPECTED_NAME, settings.getString("preferred_display_name", null))
        assertEquals(
            CompanionExperienceMode.EXPERT.persistedValue,
            settings.getString("experience_mode", null),
        )
        assertTrue(settings.getBoolean("reduced_motion", false))

        val activity = JSONObject(required(context, "activity", "events_v1"))
        assertEquals("private-local", activity.getString("privacy"))
        assertEquals(
            EXPECTED_ACTIVITY,
            activity.getJSONArray("events").getJSONObject(0).getString("title"),
        )

        val galaxy = JSONObject(required(context, "community", "topics_v1"))
        val topic = galaxy.getJSONArray("topics").getJSONObject(0)
        val comments = topic.getJSONArray("comments")
        val topicData = GalaxyTopicData(
            topic.getString("id"),
            topic.getString("title"),
            topic.getString("body"),
            topic.getLong("created_at"),
            topic.getInt("vote"),
            listOf(
                GalaxyReplyData(
                    comments.getJSONObject(0).getString("id"),
                    comments.getJSONObject(0).getString("body"),
                    comments.getJSONObject(0).getLong("created_at"),
                ),
            ),
        )
        assertEquals(EXPECTED_TOPIC, topicData.title)
        assertTrue(
            GalaxyRules.verifyCommunityDigest(
                listOf(topicData),
                galaxy.getString("community_digest"),
            ),
        )

        val optimizer = OptimizerTrendHistory.decode(
            required(context, "optimizer_history", "history_v1"),
        )
        assertTrue(optimizer.valid)
        assertTrue(optimizer.integrityVerified)
        assertEquals(77, optimizer.snapshots.single().batteryPercent)

        val lifelineJson = JSONObject(required(context, "repair_session", "session_v1"))
        val reviewed = lifelineJson.getJSONArray("reviewed")
        val lifeline = LifelineSessionSnapshot(
            lifelineJson.getString("session_id"),
            lifelineJson.getLong("created_at_epoch_ms"),
            lifelineJson.getLong("updated_at_epoch_ms"),
            lifelineJson.getString("status"),
            lifelineJson.getInt("baseline_score"),
            listOf(lifelineJson.getJSONArray("baseline_findings").getString(0)),
            listOf(
                lifelineJson.getJSONArray("checkpoints").getString(0),
                lifelineJson.getJSONArray("checkpoints").getString(1),
            ),
            listOf(reviewed.getBoolean(0), reviewed.getBoolean(1)),
        )
        assertEquals("upgrade-lifeline", lifeline.sessionId)
        assertTrue(
            LifelineSessionIntegrity.verifies(
                lifeline,
                lifelineJson.getString("session_digest"),
            ),
        )

        val pairing = context.getSharedPreferences(
            LinkSessionVault.PREFERENCES_NAME,
            Context.MODE_PRIVATE,
        )
        assertTrue(pairing.getBoolean("paired", false))
        assertEquals("127.0.0.1:65535", pairing.getString("paired_host", null))
        assertEquals(EXPECTED_LINK_TOKEN, LinkSessionVault(context, pairing).load())
        assertFalse(pairing.contains(LinkSessionVault.LEGACY_TOKEN_KEY))
        assertNotNull(pairing.getString(LinkSessionVault.CIPHERTEXT_KEY, null))
    }

    private fun preserve(context: Context, store: String, key: String, value: String) {
        assertTrue(
            context.getSharedPreferences(store, Context.MODE_PRIVATE)
                .edit()
                .clear()
                .putString(key, value)
                .commit(),
        )
    }

    private fun required(context: Context, store: String, key: String): String =
        requireNotNull(
            context.getSharedPreferences(store, Context.MODE_PRIVATE).getString(key, null),
        ) { "$store/$key was not preserved across the APK update" }

    companion object {
        private const val ARGUMENT_PHASE = "romverseUpgradePhase"
        private const val PHASE_SEED = "seed"
        private const val PHASE_VERIFY = "verify"
        private const val EXPECTED_NAME = "Upgrade Voyager"
        private const val EXPECTED_ACTIVITY = "Upgrade continuity fixture seeded"
        private const val EXPECTED_TOPIC = "Upgrade continuity"
        private const val EXPECTED_LINK_TOKEN =
            "UpgradeContinuityToken_0123456789_ABCDEFGHIJKLMN"
    }
}
