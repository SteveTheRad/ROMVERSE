package com.radforge.romverse.companion

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Android-Keystore envelope for the reusable local Link bearer credential. */
internal class LinkSessionVault(
    context: Context,
    private val preferences: SharedPreferences = context.getSharedPreferences(
        PREFERENCES_NAME,
        Context.MODE_PRIVATE,
    ),
    private val keyAlias: String = DEFAULT_KEY_ALIAS,
) {
    @Synchronized
    fun store(token: String): Boolean {
        if (!validToken(token)) return false
        return runCatching {
            val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION).apply {
                init(Cipher.ENCRYPT_MODE, loadOrCreateKey())
            }
            val ciphertext = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
            val stored = preferences.edit()
                .putString(IV_KEY, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString(CIPHERTEXT_KEY, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
                .commit()
            val legacyRemoved = preferences.edit().remove(LEGACY_TOKEN_KEY).commit()
            check(stored && legacyRemoved) { "Link credential storage was not committed" }
            true
        }.getOrElse {
            clear()
            false
        }
    }

    @Synchronized
    fun load(): String? {
        val encodedIv = preferences.getString(IV_KEY, null)
        val encodedCiphertext = preferences.getString(CIPHERTEXT_KEY, null)
        if (encodedIv == null && encodedCiphertext == null) {
            return migrateLegacyToken()
        }
        if (encodedIv == null || encodedCiphertext == null) {
            clear()
            return null
        }
        return runCatching {
            val iv = Base64.decode(encodedIv, Base64.NO_WRAP)
            val ciphertext = Base64.decode(encodedCiphertext, Base64.NO_WRAP)
            require(iv.size == GCM_IV_BYTES && ciphertext.size in MIN_CIPHERTEXT_BYTES..MAX_CIPHERTEXT_BYTES)
            val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION).apply {
                init(Cipher.DECRYPT_MODE, loadExistingKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
            }
            cipher.doFinal(ciphertext).toString(Charsets.UTF_8).takeIf(::validToken)
                ?: error("Decrypted Link credential is invalid")
        }.getOrElse {
            clear()
            null
        }
    }

    @Synchronized
    fun clear() {
        preferences.edit()
            .remove(IV_KEY)
            .remove(CIPHERTEXT_KEY)
            .remove(LEGACY_TOKEN_KEY)
            .commit()
        runCatching { keyStore().deleteEntry(keyAlias) }
    }

    private fun migrateLegacyToken(): String? {
        val legacy = preferences.getString(LEGACY_TOKEN_KEY, null) ?: return null
        return legacy.takeIf(::validToken)?.takeIf(::store)
            ?: run {
                clear()
                null
            }
    }

    private fun loadExistingKey(): SecretKey =
        (keyStore().getKey(keyAlias, null) as? SecretKey)
            ?: error("ROMVERSE Link key is unavailable")

    private fun loadOrCreateKey(): SecretKey = runCatching { loadExistingKey() }.getOrElse {
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).apply {
            init(
                KeyGenParameterSpec.Builder(
                    keyAlias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
        }.generateKey()
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    private fun validToken(token: String): Boolean =
        token.length in MIN_TOKEN_LENGTH..MAX_TOKEN_LENGTH &&
            token.all { it.isLetterOrDigit() || it == '-' || it == '_' }

    companion object {
        const val PREFERENCES_NAME = "pairing"
        const val LEGACY_TOKEN_KEY = "session_token"
        const val IV_KEY = "session_token_iv_v1"
        const val CIPHERTEXT_KEY = "session_token_ciphertext_v1"
        const val DEFAULT_KEY_ALIAS = "romverse_link_session_v1"
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val CIPHER_TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_TAG_BITS = 128
        private const val GCM_IV_BYTES = 12
        private const val MIN_TOKEN_LENGTH = 32
        private const val MAX_TOKEN_LENGTH = 256
        private const val MIN_CIPHERTEXT_BYTES = MIN_TOKEN_LENGTH + (GCM_TAG_BITS / 8)
        private const val MAX_CIPHERTEXT_BYTES = MAX_TOKEN_LENGTH + (GCM_TAG_BITS / 8)
    }
}
