package pro.antigravity.voice

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class DispatchResult(
    val success: Boolean,
    val dispatchId: String = "",
    val status: String = "",
    val spokenConfirmation: String = "",
    val errorMessage: String = ""
)

data class StatusResult(
    val dispatchId: String,
    val status: String,
    val executionSummary: String? = null,
    val errorMessage: String = ""
)

object AntiVoiceClient {
    // Configurable endpoint (must be configured by user; refuses non-https except debug loopbacks)
    var baseUrl: String = ""
    var sessionToken: String = ""
    var isDebug: Boolean = false
    private const val USER_AGENT = "AntiVoice/1.0 (Android)"
    private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

    fun isUrlAllowed(url: String, debug: Boolean = isDebug): Boolean {
        if (url.isBlank()) return false
        return try {
            val uri = java.net.URI(url.trim())
            val scheme = uri.scheme?.lowercase() ?: return false
            val host = uri.host?.lowercase() ?: return false
            if (scheme == "https") {
                true
            } else if (scheme == "http" && debug) {
                host == "localhost" || host == "127.0.0.1" || host == "10.0.2.2"
            } else {
                false
            }
        } catch (_: Exception) {
            false
        }
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    suspend fun checkHealth(): Boolean = withContext(Dispatchers.IO) {
        if (baseUrl.isBlank() || !isUrlAllowed(baseUrl)) {
            return@withContext false
        }
        try {
            val req = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/health")
                .header("User-Agent", USER_AGENT)
                .get()
                .build()
            httpClient.newCall(req).execute().use { resp ->
                resp.isSuccessful
            }
        } catch (_: Exception) {
            false
        }
    }

    suspend fun dispatchInstruction(instruction: String): DispatchResult = withContext(Dispatchers.IO) {
        if (baseUrl.isBlank()) {
            return@withContext DispatchResult(
                success = false,
                errorMessage = "Relay URL is not configured. Please set the Relay URL in Settings."
            )
        }
        if (!isUrlAllowed(baseUrl)) {
            return@withContext DispatchResult(
                success = false,
                errorMessage = "Insecure or invalid Relay URL. Only HTTPS endpoints are permitted (HTTP allowed only for localhost/10.0.2.2 in debug builds)."
            )
        }
        try {
            val payload = JSONObject().apply {
                put("instruction", instruction)
                put("source", "anti_mobile")
                put("ttl_seconds", 300)
            }

            val reqBuilder = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/agent/dispatch")
                .header("User-Agent", USER_AGENT)
                .post(payload.toString().toRequestBody(JSON_MEDIA))

            if (sessionToken.isNotBlank()) {
                reqBuilder.header("Authorization", "Bearer $sessionToken")
            }

            val req = reqBuilder.build()

            httpClient.newCall(req).execute().use { resp ->
                val bodyStr = resp.body?.string() ?: ""
                if (resp.isSuccessful) {
                    val json = JSONObject(bodyStr)
                    DispatchResult(
                        success = json.optBoolean("success", true),
                        dispatchId = json.optString("dispatch_id", ""),
                        status = json.optString("status", "QUEUED"),
                        spokenConfirmation = json.optString("spoken_confirmation", "Sent to Antigravity on your desktop.")
                    )
                } else {
                    DispatchResult(
                        success = false,
                        errorMessage = "HTTP ${resp.code}: $bodyStr"
                    )
                }
            }
        } catch (e: Exception) {
            DispatchResult(success = false, errorMessage = e.message ?: "Network error")
        }
    }

    suspend fun pollStatus(dispatchId: String): StatusResult = withContext(Dispatchers.IO) {
        if (baseUrl.isBlank() || !isUrlAllowed(baseUrl)) {
            return@withContext StatusResult(
                dispatchId = dispatchId,
                status = "ERROR",
                errorMessage = "Relay URL is not configured or disallowed."
            )
        }
        try {
            val reqBuilder = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/agent/status/$dispatchId")
                .header("User-Agent", USER_AGENT)
                .get()

            if (sessionToken.isNotBlank()) {
                reqBuilder.header("Authorization", "Bearer $sessionToken")
            }

            val req = reqBuilder.build()

            httpClient.newCall(req).execute().use { resp ->
                val bodyStr = resp.body?.string() ?: ""
                if (resp.isSuccessful) {
                    val json = JSONObject(bodyStr)
                    StatusResult(
                        dispatchId = dispatchId,
                        status = json.optString("status", "PENDING"),
                        executionSummary = json.optString("execution_summary").takeIf { it.isNotBlank() && it != "null" }
                    )
                } else {
                    StatusResult(
                        dispatchId = dispatchId,
                        status = "FAILED",
                        errorMessage = "HTTP ${resp.code}: $bodyStr"
                    )
                }
            }
        } catch (e: Exception) {
            StatusResult(
                dispatchId = dispatchId,
                status = "ERROR",
                errorMessage = e.message ?: "Network error"
            )
        }
    }
}
