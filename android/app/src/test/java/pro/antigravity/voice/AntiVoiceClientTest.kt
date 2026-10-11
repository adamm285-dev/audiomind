package pro.antigravity.voice

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class AntiVoiceClientTest {

    @Before
    fun setUp() {
        AntiVoiceClient.baseUrl = ""
        AntiVoiceClient.sessionToken = ""
        AntiVoiceClient.isDebug = false
    }

    @Test
    fun testDefaultConfigurationIsEmpty() {
        assertEquals("", AntiVoiceClient.baseUrl)
        assertEquals("", AntiVoiceClient.sessionToken)
    }

    @Test
    fun testUrlAllowedHttpsPermitted() {
        assertTrue(AntiVoiceClient.isUrlAllowed("https://relay.example.com", debug = false))
        assertTrue(AntiVoiceClient.isUrlAllowed("https://localhost:8443", debug = false))
        assertTrue(AntiVoiceClient.isUrlAllowed("https://10.0.2.2:8443", debug = false))
    }

    @Test
    fun testUrlAllowedHttpRefusedInProduction() {
        assertFalse(AntiVoiceClient.isUrlAllowed("http://api.example.com", debug = false))
        assertFalse(AntiVoiceClient.isUrlAllowed("http://localhost:8000", debug = false))
        assertFalse(AntiVoiceClient.isUrlAllowed("http://127.0.0.1:8000", debug = false))
        assertFalse(AntiVoiceClient.isUrlAllowed("http://10.0.2.2:8000", debug = false))
    }

    @Test
    fun testUrlAllowedHttpLoopbackAllowedOnlyInDebug() {
        assertTrue(AntiVoiceClient.isUrlAllowed("http://localhost:8000", debug = true))
        assertTrue(AntiVoiceClient.isUrlAllowed("http://127.0.0.1:8000", debug = true))
        assertTrue(AntiVoiceClient.isUrlAllowed("http://10.0.2.2:8000", debug = true))
        // External domains are still blocked even in debug
        assertFalse(AntiVoiceClient.isUrlAllowed("http://remote.attacker.com", debug = true))
    }

    @Test
    fun testUrlAllowedRejectsMalformedAndBlankUrls() {
        assertFalse(AntiVoiceClient.isUrlAllowed("", debug = true))
        assertFalse(AntiVoiceClient.isUrlAllowed("   ", debug = true))
        assertFalse(AntiVoiceClient.isUrlAllowed("not_a_valid_url", debug = true))
        assertFalse(AntiVoiceClient.isUrlAllowed("ftp://localhost", debug = true))
    }

    @Test
    fun testDispatchFailsClosedWhenUnconfigured() = runBlocking {
        AntiVoiceClient.baseUrl = ""
        val result = AntiVoiceClient.dispatchInstruction("Anti, run unit tests")
        assertFalse(result.success)
        assertTrue(result.errorMessage.contains("not configured"))
    }

    @Test
    fun testDispatchFailsClosedOnInsecureUrl() = runBlocking {
        AntiVoiceClient.baseUrl = "http://insecure.example.com"
        AntiVoiceClient.isDebug = false
        val result = AntiVoiceClient.dispatchInstruction("Anti, run unit tests")
        assertFalse(result.success)
        assertTrue(result.errorMessage.contains("Insecure or invalid Relay URL"))
    }

    @Test
    fun testCheckHealthFailsClosedWhenUnconfigured() = runBlocking {
        AntiVoiceClient.baseUrl = ""
        assertFalse(AntiVoiceClient.checkHealth())
    }

    @Test
    fun testPollStatusFailsClosedWhenUnconfigured() = runBlocking {
        AntiVoiceClient.baseUrl = ""
        val status = AntiVoiceClient.pollStatus("disp_test")
        assertEquals("ERROR", status.status)
        assertTrue(status.errorMessage.contains("disallowed") || status.errorMessage.contains("not configured"))
    }

    @Test
    fun testDispatchResultCreation() {
        val result = DispatchResult(
            success = true,
            dispatchId = "disp_test123",
            status = "QUEUED",
            spokenConfirmation = "Sent to Antigravity on your desktop."
        )

        assertTrue(result.success)
        assertEquals("disp_test123", result.dispatchId)
        assertEquals("QUEUED", result.status)
        assertEquals("Sent to Antigravity on your desktop.", result.spokenConfirmation)
    }

    @Test
    fun testStatusResultExecuted() {
        val status = StatusResult(
            dispatchId = "disp_test123",
            status = "EXECUTED",
            executionSummary = "All 5 unit tests passed successfully."
        )

        assertEquals("disp_test123", status.dispatchId)
        assertEquals("EXECUTED", status.status)
        assertEquals("All 5 unit tests passed successfully.", status.executionSummary)
    }

    @Test
    fun testStatusResultFailed() {
        val status = StatusResult(
            dispatchId = "disp_fail456",
            status = "FAILED",
            errorMessage = "Execution timed out"
        )

        assertEquals("FAILED", status.status)
        assertEquals("Execution timed out", status.errorMessage)
    }
}
