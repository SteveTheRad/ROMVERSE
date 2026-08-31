package com.radforge.romverse.companion

import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

data class GalaxyReplyData(val id: String, val body: String, val createdAt: Long)

data class GalaxyDraftData(val title: String, val body: String)

data class GalaxyTopicData(
    val id: String,
    val title: String,
    val body: String,
    val createdAt: Long,
    val vote: Int,
    val replies: List<GalaxyReplyData>,
)

enum class GalaxySort(val displayName: String) {
    NEWEST("Newest"),
    MOST_HELPFUL("Most helpful"),
    RECENTLY_ACTIVE("Recently active"),
}

object GalaxyRules {
    const val MAX_TOPICS = 500
    const val MAX_REPLIES = 1000
    const val MAX_TOTAL_REPLIES = 5000
    const val MAX_PERSISTED_BYTES = 8 * 1024 * 1024
    const val INTEGRITY_VERSION = 1
    private const val FUTURE_TOLERANCE_MILLIS = 5 * 60 * 1000L

    fun validateTopic(
        topic: GalaxyTopicData,
        nowEpochMillis: Long = System.currentTimeMillis(),
    ): GalaxyTopicData {
        validateIdentifier(topic.id, "topic")
        validateTopicText(topic.title, topic.body)
        validateTimestamp(topic.createdAt, nowEpochMillis, "topic")
        require(topic.vote in -1..1) { "A local topic vote is invalid." }
        require(topic.replies.size <= MAX_REPLIES) { "A local reply list is too large." }
        topic.replies.forEach { reply ->
            validateReply(reply, nowEpochMillis)
            require(reply.createdAt >= topic.createdAt) {
                "A local reply predates its topic."
            }
        }
        return topic
    }

    fun validateReply(
        reply: GalaxyReplyData,
        nowEpochMillis: Long = System.currentTimeMillis(),
    ): GalaxyReplyData {
        validateIdentifier(reply.id, "reply")
        validateReplyText(reply.body)
        validateTimestamp(reply.createdAt, nowEpochMillis, "reply")
        return reply
    }

    fun validateTopics(
        topics: List<GalaxyTopicData>,
        nowEpochMillis: Long = System.currentTimeMillis(),
    ): List<GalaxyTopicData> {
        require(topics.size <= MAX_TOPICS) { "Local Galaxy topic limit exceeded." }
        require(topics.map { it.id }.toSet().size == topics.size) {
            "Duplicate local topic identifiers were rejected."
        }
        val replyIds = mutableSetOf<String>()
        var totalReplies = 0
        topics.forEach { topic ->
            validateTopic(topic, nowEpochMillis)
            totalReplies += topic.replies.size
            topic.replies.forEach { reply ->
                require(replyIds.add(reply.id)) {
                    "Duplicate local reply identifiers were rejected."
                }
            }
        }
        require(totalReplies <= MAX_TOTAL_REPLIES) {
            "The local reply collection exceeds the safe limit."
        }
        return topics
    }

    fun validateTopicText(title: String, body: String) {
        require(title.trim().length in 1..120) { "A local topic title is invalid." }
        require(body.trim().length in 1..10_000) { "A local topic message is invalid." }
        require(!title.contains('\u0000') && !body.contains('\u0000')) {
            "A local topic contains an invalid control character."
        }
    }

    fun validateReplyText(body: String) {
        require(body.trim().length in 1..4_000) { "A local reply message is invalid." }
        require(!body.contains('\u0000')) { "A local reply contains an invalid control character." }
    }

    fun boundedDraft(title: String, body: String): GalaxyDraftData = GalaxyDraftData(
        title.replace("\u0000", "").take(120),
        body.replace("\u0000", "").take(10_000),
    )

    fun matches(topic: GalaxyTopicData, query: String): Boolean {
        val needle = query.trim().lowercase()
        return needle.isBlank() || topic.title.lowercase().contains(needle) ||
            topic.body.lowercase().contains(needle) ||
            topic.replies.any { it.body.lowercase().contains(needle) }
    }

    fun sortTopics(topics: List<GalaxyTopicData>, order: GalaxySort): List<GalaxyTopicData> {
        validateTopics(topics)
        return when (order) {
            GalaxySort.NEWEST -> topics.sortedWith(
                compareByDescending<GalaxyTopicData> { it.createdAt }.thenBy { it.id },
            )
            GalaxySort.MOST_HELPFUL -> topics.sortedWith(
                compareByDescending<GalaxyTopicData> { it.vote }
                    .thenByDescending { it.createdAt }
                    .thenBy { it.id },
            )
            GalaxySort.RECENTLY_ACTIVE -> topics.sortedWith(
                compareByDescending<GalaxyTopicData> { topic ->
                    maxOf(topic.createdAt, topic.replies.maxOfOrNull { it.createdAt } ?: 0L)
                }.thenByDescending { it.replies.size }
                    .thenBy { it.id },
            )
        }
    }

    fun toggleVote(current: Int, requested: Int): Int {
        require(current in -1..1 && requested in setOf(-1, 1)) { "A local vote is invalid." }
        return if (current == requested) 0 else requested
    }

    fun communityDigest(topics: List<GalaxyTopicData>): String {
        validateTopics(topics)
        val digest = MessageDigest.getInstance("SHA-256")
        updateString(digest, "romverse.galaxy.community")
        updateLong(digest, INTEGRITY_VERSION.toLong())
        updateLong(digest, topics.size.toLong())
        topics.forEach { topic ->
            updateString(digest, topic.id)
            updateString(digest, topic.title)
            updateString(digest, topic.body)
            updateLong(digest, topic.createdAt)
            updateLong(digest, topic.vote.toLong())
            updateLong(digest, topic.replies.size.toLong())
            topic.replies.forEach { reply ->
                updateString(digest, reply.id)
                updateString(digest, reply.body)
                updateLong(digest, reply.createdAt)
            }
        }
        return digest.digest().joinToString("") { byte -> "%02x".format(byte) }
    }

    fun verifyCommunityDigest(topics: List<GalaxyTopicData>, expected: String): Boolean {
        if (!expected.matches(Regex("[0-9a-fA-F]{64}"))) return false
        return runCatching {
            MessageDigest.isEqual(
                expected.lowercase().toByteArray(StandardCharsets.US_ASCII),
                communityDigest(topics).toByteArray(StandardCharsets.US_ASCII),
            )
        }.getOrDefault(false)
    }

    private fun validateIdentifier(value: String, kind: String) {
        require(value.isNotBlank() && value.length <= 80 && value.none(Char::isISOControl)) {
            "A local $kind has an invalid identifier."
        }
    }

    private fun validateTimestamp(value: Long, nowEpochMillis: Long, kind: String) {
        require(value > 0L && value <= nowEpochMillis + FUTURE_TOLERANCE_MILLIS) {
            "A local $kind timestamp is invalid."
        }
    }

    private fun updateString(digest: MessageDigest, value: String) {
        val bytes = value.toByteArray(StandardCharsets.UTF_8)
        updateLong(digest, bytes.size.toLong())
        digest.update(bytes)
    }

    private fun updateLong(digest: MessageDigest, value: Long) {
        digest.update(ByteBuffer.allocate(Long.SIZE_BYTES).putLong(value).array())
    }
}
