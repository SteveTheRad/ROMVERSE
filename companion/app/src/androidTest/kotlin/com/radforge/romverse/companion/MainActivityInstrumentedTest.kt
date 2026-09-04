package com.radforge.romverse.companion

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Build
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainActivityInstrumentedTest {
    @Before
    fun resetOptionalDisplayPolicies() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
            .edit()
            .putBoolean("privacy_curtain_enabled", false)
            .putString("display_mode", CompanionDisplayMode.COSMIC.persistedValue)
            .putString("experience_mode", CompanionExperienceMode.GUIDED.persistedValue)
            .commit()
        context.getSharedPreferences("pairing", Context.MODE_PRIVATE)
            .edit()
            .clear()
            .commit()
    }

    @Test
    fun oledModeAppliesImmediatelyAndPreservesSettingsRouteAcrossRecreation() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val preferences = context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                waitForIdle()
                scenario.onActivity { activity ->
                    descendants(activity.window.decorView)
                        .single { it.contentDescription?.toString() == "More" }
                        .performClick()
                }
                waitForIdle()
                scenario.onActivity { activity ->
                    descendants(activity.window.decorView)
                        .single { it.contentDescription?.toString() == "Settings" }
                        .performClick()
                }
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    views.filterIsInstance<CheckBox>()
                        .single { it.text.toString().startsWith("Use true-black OLED surfaces") }
                        .isChecked = true
                    views.filterIsInstance<Button>()
                        .single { it.text.toString() == "SAVE SETTINGS" }
                        .performClick()
                }

                assertTrue(waitUntil(scenario, 5_000L) { views ->
                    views.count { it.tag == "romverse-display-oled" } == 1 &&
                        textValues(views).contains("ROMVERSE SETTINGS")
                })
                assertEquals(
                    CompanionDisplayMode.OLED.persistedValue,
                    preferences.getString("display_mode", null),
                )

                scenario.recreate()
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    assertEquals(1, views.count { it.tag == "romverse-display-oled" })
                    assertTrue(textValues(views).contains("ROMVERSE SETTINGS"))
                    val windowBackground = activity.window.decorView.background as? ColorDrawable
                    assertEquals(Color.BLACK, windowBackground?.color)
                }
            }
        } finally {
            preferences.edit()
                .putString("display_mode", CompanionDisplayMode.COSMIC.persistedValue)
                .commit()
        }
    }

    @Test
    fun privacyCurtainObscuresContentBlocksCaptureAndReturnsAfterBackgrounding() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val preferences = context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
        preferences.edit().putBoolean("privacy_curtain_enabled", true).commit()
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    assertEquals(
                        1,
                        views.count { it.contentDescription?.toString() == "Privacy Curtain active" },
                    )
                    assertTrue(
                        activity.window.attributes.flags and
                            WindowManager.LayoutParams.FLAG_SECURE != 0,
                    )
                    views.filterIsInstance<Button>()
                        .single { it.text.toString() == "REVEAL THIS SESSION" }
                        .performClick()
                }
                waitForIdle()
                scenario.onActivity { activity ->
                    assertEquals(
                        0,
                        descendants(activity.window.decorView).count {
                            it.contentDescription?.toString() == "Privacy Curtain active"
                        },
                    )
                    assertTrue(
                        activity.window.attributes.flags and
                            WindowManager.LayoutParams.FLAG_SECURE != 0,
                    )
                }

                scenario.moveToState(Lifecycle.State.CREATED)
                scenario.moveToState(Lifecycle.State.RESUMED)
                waitForIdle()
                scenario.onActivity { activity ->
                    assertEquals(
                        1,
                        descendants(activity.window.decorView).count {
                            it.contentDescription?.toString() == "Privacy Curtain active"
                        },
                    )
                }
            }
        } finally {
            preferences.edit().putBoolean("privacy_curtain_enabled", false).commit()
        }
    }

    @Test
    fun galaxyShellHasOnePersistentStatusAndOneHomeDestination() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForIdle()
            scenario.onActivity { activity ->
                val views = descendants(activity.window.decorView)
                assertEquals(1, views.count { it.contentDescription?.toString() == "Home" })
                assertEquals(1, views.count { it.contentDescription?.toString() == "Link" })
                assertEquals(1, views.count { it.contentDescription?.toString() == "Console" })
                assertEquals(1, views.count { it.contentDescription?.toString() == "Vitalis" })
                assertEquals(1, views.count { it.contentDescription?.toString() == "More" })
                assertEquals(
                    1,
                    views.count {
                        it.contentDescription?.toString() == "ROMVERSE Link PC address"
                    },
                )
                assertEquals(
                    1,
                    views.count {
                        it.contentDescription?.toString() ==
                            "ROMVERSE Link PC certificate SHA-256"
                    },
                )
                assertEquals(
                    1,
                    views.count {
                        it.contentDescription?.toString()
                            ?.startsWith("ROMVERSE Link Flight Path.") == true
                    },
                )
                assertEquals(
                    1,
                    views.count {
                        it.contentDescription?.toString()
                            ?.startsWith("ROMVERSE Link Flight Path progress ") == true
                    },
                )
                assertEquals(
                    1,
                    views.count { view ->
                        val description = view.contentDescription?.toString().orEmpty()
                        description == "Checking ROMVERSE internet connectivity" ||
                            description == "ROMVERSE online intelligence available" ||
                            description == "ROMVERSE online intelligence unavailable"
                    },
                )
                assertTrue(textValues(views).contains("COMMAND DECK"))
            }
        }
    }

    @Test
    fun unlinkedAscensionRouteNeverClaimsDesktopSynchronization() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForIdle()
            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "More" }
                    .performClick()
            }
            waitForIdle()
            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "Ascension" }
                    .performClick()
            }
            waitForIdle()
            scenario.onActivity { activity ->
                val texts = textValues(descendants(activity.window.decorView))
                assertTrue(texts.contains("ASCENSION PROTOCOL  •  AWAITING DESKTOP LINK"))
                assertTrue(texts.contains("PAIR WITH ROMVERSE DESKTOP"))
                assertFalse(texts.contains("ASCENSION PROTOCOL  •  DESKTOP SYNCHRONIZED"))
            }
        }
    }

    @Test
    fun guidedEvidenceCanBeRevealedAndExpertEvidenceOpensAfterRecreation() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val preferences = context.getSharedPreferences("romverse_settings", Context.MODE_PRIVATE)
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                waitForIdle()
                scenario.onActivity { activity ->
                    descendants(activity.window.decorView)
                        .single { it.contentDescription?.toString() == "Vitalis" }
                        .performClick()
                }
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    val technicalEvidence = views.single {
                        it.tag == "romverse-technical-vitalis"
                    }
                    assertEquals(View.GONE, technicalEvidence.visibility)
                    assertTrue(textValues(views).contains("DIAGNOSIS & SAFE NEXT ACTIONS"))
                    views.single {
                        it.contentDescription?.toString() ==
                            "Reveal Vitalis technical evidence"
                    }.performClick()
                }
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    assertEquals(
                        View.VISIBLE,
                        views.single { it.tag == "romverse-technical-vitalis" }.visibility,
                    )
                }

                preferences.edit()
                    .putString("experience_mode", CompanionExperienceMode.EXPERT.persistedValue)
                    .commit()
                scenario.recreate()
                waitForIdle()
                scenario.onActivity { activity ->
                    val views = descendants(activity.window.decorView)
                    assertTrue(textValues(views).contains("VITALIS"))
                    assertEquals(
                        View.VISIBLE,
                        views.single { it.tag == "romverse-technical-vitalis" }.visibility,
                    )
                    assertTrue(
                        textValues(views).contains(
                            "ARCHITECT  •  FULL TECHNICAL EVIDENCE OPEN",
                        ),
                    )
                    assertEquals(
                        0,
                        views.count {
                            it.contentDescription?.toString() ==
                                "Reveal Vitalis technical evidence"
                        },
                    )
                }
            }
        } finally {
            preferences.edit()
                .putString("experience_mode", CompanionExperienceMode.GUIDED.persistedValue)
                .commit()
        }
    }

    @Test
    fun aboutRouteAndOfficialCommunityActionsSurviveActivityRecreation() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForIdle()
            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "More" }
                    .performClick()
            }
            waitForIdle()
            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "About" }
                    .performClick()
            }
            waitForIdle()
            assertAboutRoute(scenario)

            scenario.recreate()
            waitForIdle()
            assertAboutRoute(scenario)
        }
    }

    @Test
    fun sdkEmulatorIdentityNeverMasqueradesAsPhysicalGoogleHardware() {
        val emulator = listOf(Build.MODEL, Build.PRODUCT, Build.DEVICE, Build.HARDWARE)
            .joinToString(" ")
            .lowercase()
            .let { markers ->
                markers.contains("sdk") ||
                    markers.contains("emulator") ||
                    markers.contains("goldfish") ||
                    markers.contains("ranchu")
            }
        if (!emulator) return

        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForIdle()
            scenario.onActivity { activity ->
                val texts = textValues(descendants(activity.window.decorView))
                assertTrue(texts.any { it.contains("Android Emulator") })
                assertFalse(texts.any { it.contains("Google ${Build.MODEL}") })
            }
        }
    }

    @Test
    fun tlsPinnedLinkCarriesLiveConsoleAndReconnectsAfterRecreation() {
        val arguments = InstrumentationRegistry.getArguments()
        val host = arguments.getString("romverseLinkHost").orEmpty()
        val code = arguments.getString("romverseLinkCode").orEmpty()
        val fingerprint = arguments.getString("romverseLinkFingerprint").orEmpty()
        assumeTrue(
            "Run with the contained Desktop Link fixture to exercise the integration contract",
            host.isNotBlank() && code.length == 6 && fingerprint.length == 64,
        )

        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            waitForIdle()
            scenario.onActivity { activity ->
                val views = descendants(activity.window.decorView)
                views.filterIsInstance<EditText>()
                    .single { it.hint?.toString().orEmpty().startsWith("PC address") }
                    .setText(host)
                views.filterIsInstance<EditText>()
                    .single { it.hint?.toString().orEmpty().startsWith("PC certificate") }
                    .setText(fingerprint)
                views.filterIsInstance<EditText>()
                    .single { it.hint?.toString() == "000000" }
                    .setText(code)
                views.filterIsInstance<CheckBox>()
                    .single { it.text.toString().startsWith("I confirmed the Link safety code") }
                    .isChecked = true
                views.filterIsInstance<Button>()
                    .single { it.text.toString() == "CONNECT WIRELESSLY" }
                    .performClick()
            }

            assertTrue(waitUntil(scenario, 20_000L) { views ->
                textValues(views).any { it == "Paired • two-way health sync active" }
            })
            scenario.onActivity { activity ->
                val pairing = activity.getSharedPreferences(
                    LinkSessionVault.PREFERENCES_NAME,
                    Context.MODE_PRIVATE,
                )
                assertFalse(pairing.contains(LinkSessionVault.LEGACY_TOKEN_KEY))
                assertTrue(pairing.contains(LinkSessionVault.CIPHERTEXT_KEY))
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "Console" }
                    .performClick()
            }
            waitForIdle()
            assertTrue(waitUntil(scenario, 5_000L) { views ->
                textValues(views).contains("Emulator Link contract verified")
            })

            scenario.recreate()
            waitForIdle()
            assertTrue(waitUntil(scenario, 20_000L) { views ->
                val texts = textValues(views)
                texts.contains("ROMVERSE LIVE CONSOLE  •  LINK V6") &&
                    texts.contains("Emulator Link contract verified")
            })

            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "More" }
                    .performClick()
            }
            waitForIdle()
            scenario.onActivity { activity ->
                descendants(activity.window.decorView)
                    .single { it.contentDescription?.toString() == "Ascension" }
                    .performClick()
            }
            waitForIdle()
            scenario.onActivity { activity ->
                val views = descendants(activity.window.decorView)
                val texts = textValues(views)
                assertTrue(texts.contains("ASCENSION PROTOCOL  •  DESKTOP SYNCHRONIZED"))
                assertTrue(texts.contains("READY FOR GUARDIAN REVIEW"))
                assertTrue(texts.contains("STAGE 9 OF 9  •  READY FOR FINAL GUARDIAN REVIEW"))
                assertTrue(texts.contains("OFFICIAL ROOT TOOL  •  VERIFIED"))
                assertTrue(
                    views.any {
                        it.contentDescription?.toString() == "Ascension progress 100 percent"
                    },
                )
                assertTrue(texts.any { it.contains("Execution authority: NONE") })
                assertTrue(texts.any { it.contains("Bootloader relock: PERMANENTLY PROHIBITED") })
            }
        }
    }

    private fun assertAboutRoute(scenario: ActivityScenario<MainActivity>) {
        scenario.onActivity { activity ->
            val views = descendants(activity.window.decorView)
            val texts = textValues(views)
            assertTrue(texts.contains("ABOUT ROMVERSE COMPANION"))
            assertTrue(
                views.any {
                    it.contentDescription?.toString() == "ROMVERSE approved animated logo"
                },
            )
            assertEquals(
                1,
                views.count {
                    it.contentDescription?.toString() ==
                        "RadForge Labs official animated company logo"
                },
            )
            assertEquals(
                1,
                views.count { it.contentDescription?.toString().orEmpty().startsWith("Facebook.") },
            )
            assertEquals(
                1,
                views.count { it.contentDescription?.toString().orEmpty().startsWith("Reddit.") },
            )
        }
    }

    private fun waitForIdle() {
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
    }

    private fun waitUntil(
        scenario: ActivityScenario<MainActivity>,
        timeoutMillis: Long,
        predicate: (List<View>) -> Boolean,
    ): Boolean {
        val deadline = SystemClock.elapsedRealtime() + timeoutMillis
        while (SystemClock.elapsedRealtime() < deadline) {
            var matched = false
            scenario.onActivity { activity ->
                matched = predicate(descendants(activity.window.decorView))
            }
            if (matched) return true
            SystemClock.sleep(250L)
            waitForIdle()
        }
        return false
    }

    private fun textValues(views: List<View>): List<String> =
        views.filterIsInstance<TextView>().map { it.text.toString() }

    private fun descendants(root: View): List<View> = buildList {
        fun collect(view: View) {
            add(view)
            if (view is ViewGroup) {
                repeat(view.childCount) { index -> collect(view.getChildAt(index)) }
            }
        }
        collect(root)
    }
}
