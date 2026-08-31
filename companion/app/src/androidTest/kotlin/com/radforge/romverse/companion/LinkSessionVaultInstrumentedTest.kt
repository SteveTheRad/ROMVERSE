package com.radforge.romverse.companion

import android.content.Context
import android.content.SharedPreferences
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LinkSessionVaultInstrumentedTest {
    private lateinit var preferences: SharedPreferences
    private lateinit var vault: LinkSessionVault
    private val token = "Romverse_Test_Link_Token_0123456789abcdef"
    private val alias = "romverse_link_session_instrumented_test"

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        preferences = context.getSharedPreferences("link_session_vault_test", Context.MODE_PRIVATE)
        preferences.edit().clear().commit()
        vault = LinkSessionVault(context, preferences, alias)
        vault.clear()
    }

    @After
    fun tearDown() {
        vault.clear()
        preferences.edit().clear().commit()
    }

    @Test
    fun credentialRoundTripsWithoutPlaintextPreference() {
        assertTrue(vault.store(token))

        assertEquals(token, vault.load())
        assertFalse(preferences.contains(LinkSessionVault.LEGACY_TOKEN_KEY))
        assertTrue(preferences.contains(LinkSessionVault.IV_KEY))
        assertTrue(preferences.contains(LinkSessionVault.CIPHERTEXT_KEY))
        assertFalse(
            preferences.getString(LinkSessionVault.CIPHERTEXT_KEY, "").orEmpty().contains(token),
        )
    }

    @Test
    fun legacyPlaintextCredentialMigratesOneWayIntoKeystoreEnvelope() {
        assertTrue(
            preferences.edit()
                .putString(LinkSessionVault.LEGACY_TOKEN_KEY, token)
                .commit(),
        )

        assertEquals(token, vault.load())
        assertFalse(preferences.contains(LinkSessionVault.LEGACY_TOKEN_KEY))
        assertTrue(preferences.contains(LinkSessionVault.CIPHERTEXT_KEY))
    }

    @Test
    fun tamperedCiphertextFailsClosedAndClearsTheCredential() {
        assertTrue(vault.store(token))
        val ciphertext = preferences.getString(LinkSessionVault.CIPHERTEXT_KEY, "").orEmpty()
        assertTrue(
            preferences.edit()
                .putString(LinkSessionVault.CIPHERTEXT_KEY, ciphertext.reversed())
                .commit(),
        )

        assertNull(vault.load())
        assertFalse(preferences.contains(LinkSessionVault.IV_KEY))
        assertFalse(preferences.contains(LinkSessionVault.CIPHERTEXT_KEY))
        assertFalse(preferences.contains(LinkSessionVault.LEGACY_TOKEN_KEY))
    }
}
