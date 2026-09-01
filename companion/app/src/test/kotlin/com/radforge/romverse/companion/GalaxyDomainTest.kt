package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GalaxyDomainTest {
    private val topic = GalaxyTopicData(
        "topic-id",
        "ROM DNA discovery",
        "Verified build evidence",
        1_000,
        0,
        listOf(GalaxyReplyData("reply-id", "Check the payload digest", 2_000)),
    )

    @Test
    fun validatesAndSearchesTitleBodyAndReplies() {
        GalaxyRules.validateTopic(topic)
        GalaxyRules.validateTopics(listOf(topic))
        assertTrue(GalaxyRules.matches(topic, "rom dna"))
        assertTrue(GalaxyRules.matches(topic, "evidence"))
        assertTrue(GalaxyRules.matches(topic, "payload"))
        assertFalse(GalaxyRules.matches(topic, "not present"))
    }

    @Test
    fun voteToggleIsBoundedAndReversible() {
        assertEquals(1, GalaxyRules.toggleVote(0, 1))
        assertEquals(0, GalaxyRules.toggleVote(1, 1))
        assertEquals(-1, GalaxyRules.toggleVote(1, -1))
    }

    @Test
    fun sortsConversationsByNewestHelpfulAndLatestReplyActivity() {
        val olderHelpful = topic.copy(
            id = "older-helpful",
            title = "Older helpful topic",
            createdAt = 1_000,
            vote = 1,
            replies = emptyList(),
        )
        val newest = topic.copy(
            id = "newest",
            title = "Newest topic",
            createdAt = 4_000,
            vote = 0,
            replies = emptyList(),
        )
        val active = topic.copy(
            id = "active",
            title = "Recently active topic",
            createdAt = 2_000,
            vote = -1,
            replies = listOf(GalaxyReplyData("active-reply", "Latest update", 5_000)),
        )
        val topics = listOf(olderHelpful, active, newest)

        assertEquals(
            listOf("newest", "active", "older-helpful"),
            GalaxyRules.sortTopics(topics, GalaxySort.NEWEST).map { it.id },
        )
        assertEquals(
            listOf("older-helpful", "newest", "active"),
            GalaxyRules.sortTopics(topics, GalaxySort.MOST_HELPFUL).map { it.id },
        )
        assertEquals(
            listOf("active", "newest", "older-helpful"),
            GalaxyRules.sortTopics(topics, GalaxySort.RECENTLY_ACTIVE).map { it.id },
        )
    }

    @Test
    fun boundsDraftsBeforePrivatePersistenceWithoutLosingLineBreaks() {
        val draft = GalaxyRules.boundedDraft(
            "A".repeat(130) + "\u0000",
            "first line\n" + "B".repeat(10_100) + "\u0000",
        )

        assertEquals(120, draft.title.length)
        assertEquals(10_000, draft.body.length)
        assertTrue(draft.body.startsWith("first line\n"))
        assertFalse(draft.title.contains('\u0000'))
        assertFalse(draft.body.contains('\u0000'))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsOversizedReply() {
        GalaxyRules.validateReply(GalaxyReplyData("reply", "x".repeat(4_001), 1_000))
    }

    @Test
    fun communityDigestDetectsAnyTopicMutationAndOrderChange() {
        val second = topic.copy(id = "topic-two", title = "Second topic", replies = emptyList())
        val topics = listOf(topic, second)
        val digest = GalaxyRules.communityDigest(topics)

        assertEquals(64, digest.length)
        assertTrue(GalaxyRules.verifyCommunityDigest(topics, digest))
        assertFalse(
            GalaxyRules.verifyCommunityDigest(
                listOf(topic.copy(body = "Changed evidence"), second),
                digest,
            ),
        )
        assertFalse(GalaxyRules.verifyCommunityDigest(topics.reversed(), digest))
        assertFalse(GalaxyRules.verifyCommunityDigest(topics, "not-a-digest"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsDuplicateTopicIdentifiersAcrossTheCollection() {
        GalaxyRules.validateTopics(listOf(topic, topic.copy(title = "Ambiguous duplicate")))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsDuplicateReplyIdentifiersAcrossTopics() {
        val duplicateReply = topic.copy(
            id = "topic-two",
            replies = listOf(GalaxyReplyData("reply-id", "Duplicate identity", 3_000)),
        )
        GalaxyRules.validateTopics(listOf(topic, duplicateReply))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsFutureDatedCommunityEvidence() {
        GalaxyRules.validateTopics(
            listOf(topic.copy(createdAt = 2_000_000)),
            nowEpochMillis = 1_000,
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsRepliesThatPredateTheirTopic() {
        GalaxyRules.validateTopics(
            listOf(
                topic.copy(
                    createdAt = 2_000,
                    replies = listOf(GalaxyReplyData("reply", "Too early", 1_000)),
                ),
            ),
            nowEpochMillis = 3_000,
        )
    }
}
