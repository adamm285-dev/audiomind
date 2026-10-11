package pro.antigravity.voice

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import android.util.Log
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.lifecycle.lifecycleScope
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.android.material.bottomsheet.BottomSheetDialog
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import pro.antigravity.voice.databinding.ActivityAntiVoiceBinding
import pro.antigravity.voice.databinding.ItemVoiceOptionBinding
import pro.antigravity.voice.databinding.SheetVoiceSelectorBinding
import java.util.Locale

class AntiVoiceActivity : AppCompatActivity(), TextToSpeech.OnInitListener {

    private lateinit var binding: ActivityAntiVoiceBinding
    private var speechRecognizer: SpeechRecognizer? = null
    private var textToSpeech: TextToSpeech? = null
    private var isTtsReady = false

    private var currentSpeechCharIndex = 0
    private var isTtsSpeaking = false
    private var isTtsPaused = false

    private var activePollJob: Job? = null
    private var lastSpokenResponse: String = ""
    private var isListening = false

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            startListening()
        } else {
            Toast.makeText(this, "Microphone permission is required for voice commands.", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAntiVoiceBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Dynamically apply window insets so navigation bar and soft keyboard never obscure input fields
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { view, windowInsets ->
            val navBars = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            val ime = windowInsets.getInsets(WindowInsetsCompat.Type.ime())

            val basePadHoriz = (16 * resources.displayMetrics.density).toInt()
            val basePadTop = (8 * resources.displayMetrics.density).toInt()
            val basePadBottom = (12 * resources.displayMetrics.density).toInt()
            val bottomInset = maxOf(navBars.bottom, ime.bottom)

            view.updatePadding(
                left = basePadHoriz + navBars.left,
                top = navBars.top + basePadTop,
                right = basePadHoriz + navBars.right,
                bottom = bottomInset + basePadBottom
            )
            windowInsets
        }

        initClientConfiguration()
        initTextToSpeech()
        setupListeners()
        checkWorkstationHealth()
        handleIncomingIntent(intent)
    }

    private fun getSecurePreferences(): android.content.SharedPreferences {
        return try {
            val masterKey = MasterKey.Builder(applicationContext)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                applicationContext,
                "anti_voice_secure_prefs",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            Log.w("AntiVoice", "EncryptedSharedPreferences unavailable; falling back to private prefs", e)
            getSharedPreferences("anti_voice_prefs", MODE_PRIVATE)
        }
    }

    private fun initClientConfiguration() {
        AntiVoiceClient.isDebug = BuildConfig.DEBUG
        val prefs = getSecurePreferences()
        prefs.getString("relay_base_url", null)?.let { url ->
            if (url.isNotBlank()) AntiVoiceClient.baseUrl = url.trim()
        }
        prefs.getString("relay_session_token", null)?.let { token ->
            if (token.isNotBlank()) AntiVoiceClient.sessionToken = token.trim()
        }
    }

    override fun onResume() {
        super.onResume()
        if (isTtsReady) {
            applyVoiceConfiguration()
        }
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        val action = intent.action

        // 1. Check for specific action extra (e.g. from shortcuts or App Actions)
        val targetAction = intent.getStringExtra("target_action")
        if (!targetAction.isNullOrBlank()) {
            val prompt = when (targetAction.lowercase()) {
                "tests" -> "Anti, run the unit test suite and report results."
                "git" -> "Anti, check git status and summarize active diffs."
                "health" -> "Anti, check production health and inspect recent logs."
                "deploy" -> "Anti, trigger staging build and deployment pipeline."
                "commits" -> "Anti, summarize recent git commits and changes."
                else -> null // Strictly ignore unknown actions; do NOT construct dynamic prompts
            }
            if (prompt != null) {
                stageCommandForConfirmation(prompt)
            }
            return
        }

        // 2. Check for speech / text passed via Assistant (e.g. SEND, SEARCH, or query)
        val queryText = intent.getStringExtra(Intent.EXTRA_TEXT)
            ?: intent.getStringExtra("query")
            ?: intent.getStringExtra("feature")

        if (!queryText.isNullOrBlank()) {
            stageCommandForConfirmation(queryText.trim())
            return
        }

        // 3. Direct VOICE_COMMAND trigger (e.g. "Hey Google, open Antigravity")
        if (action == "android.intent.action.VOICE_COMMAND") {
            checkPermissionAndListen()
        }
    }

    private fun stageCommandForConfirmation(prompt: String) {
        // Pre-fill the input field
        binding.etCommandInput.setText(prompt)
        binding.etCommandInput.setSelection(prompt.length)

        // Show confirmation dialog before any dispatch
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Confirm Voice Dispatch")
            .setMessage("Ready to send instruction to Antigravity:\n\n\"$prompt\"")
            .setPositiveButton("Dispatch") { _, _ ->
                executeCommand(prompt)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun initTextToSpeech() {
        try {
            val defaultSynth = android.provider.Settings.Secure.getString(contentResolver, "tts_default_synth")
            if (!defaultSynth.isNullOrBlank()) {
                textToSpeech = TextToSpeech(this, this, defaultSynth)
            } else {
                textToSpeech = TextToSpeech(this, this, "com.google.android.tts")
            }
        } catch (_: Exception) {
            textToSpeech = TextToSpeech(this, this)
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            isTtsReady = true
            Log.i("AntiVoice", "--- TTS INIT SUCCESS ---")
            Log.i("AntiVoice", "Default Engine: ${textToSpeech?.defaultEngine}")
            Log.i("AntiVoice", "Current Engine Voice on Init: ${textToSpeech?.voice?.name}")
            Log.i("AntiVoice", "Current Engine DefaultVoice: ${textToSpeech?.defaultVoice?.name}")
            val voices = try { textToSpeech?.voices?.toList() ?: emptyList() } catch (_: Exception) { emptyList() }
            Log.i("AntiVoice", "Total voices reported: ${voices.size}")
            for (v in voices.filter { it.locale.language.equals("en", ignoreCase = true) }) {
                Log.i("AntiVoice", "Voice: ${v.name} | locale=${v.locale} | isNetwork=${v.isNetworkConnectionRequired} | latency=${v.latency} | quality=${v.quality}")
            }
            applyVoiceConfiguration()
            textToSpeech?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {
                    isTtsSpeaking = true
                    isTtsPaused = false
                    runOnUiThread {
                        binding.tvMicPrompt.text = "Speaking response..."
                        binding.btnReplayVoice.text = "⏸ Pause Voice"
                    }
                }

                override fun onRangeStart(utteranceId: String?, start: Int, end: Int, frame: Int) {
                    currentSpeechCharIndex = start
                }

                override fun onDone(utteranceId: String?) {
                    isTtsSpeaking = false
                    isTtsPaused = false
                    currentSpeechCharIndex = 0
                    runOnUiThread {
                        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                        binding.btnReplayVoice.text = getString(R.string.btn_replay)
                    }
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    isTtsSpeaking = false
                    isTtsPaused = false
                    currentSpeechCharIndex = 0
                    runOnUiThread {
                        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                        binding.btnReplayVoice.text = getString(R.string.btn_replay)
                    }
                }
            })
        }
    }

    private fun applyVoiceConfiguration() {
        if (!isTtsReady) return
        val tts = textToSpeech ?: return

        // 1. Inherit pitch & speech rate from Android Settings
        val sysPitch = try {
            val p = android.provider.Settings.Secure.getInt(contentResolver, "tts_default_pitch", 100)
            (p / 100f).coerceIn(0.5f, 2.0f)
        } catch (_: Exception) { 1.0f }

        val sysRate = try {
            val r = android.provider.Settings.Secure.getInt(contentResolver, "tts_default_rate", 100)
            (r / 100f).coerceIn(0.5f, 2.0f)
        } catch (_: Exception) { 1.0f }

        tts.setPitch(sysPitch)
        tts.setSpeechRate(sysRate)

        // 2. Select voice
        val prefs = getSharedPreferences("anti_voice_prefs", MODE_PRIVATE)
        val savedVoiceName = prefs.getString("preferred_voice_name", null)

        val allVoices = try { tts.voices?.toList() ?: emptyList() } catch (_: Exception) { emptyList() }
        val defaultVoice = tts.defaultVoice

        val targetVoice = when {
            // Explicit user preference saved in app
            !savedVoiceName.isNullOrBlank() && savedVoiceName != "SYSTEM_DEFAULT" -> {
                allVoices.firstOrNull { it.name == savedVoiceName }
            }
            // Explicitly do NOT override for System Default
            else -> null
        }

        if (targetVoice != null) {
            tts.voice = targetVoice
            Log.i("AntiVoice", "Explicit voice applied: ${targetVoice.name} (pitch=$sysPitch, rate=$sysRate)")
        } else {
            Log.i("AntiVoice", "System Default mode: voice untouched, inheriting OS settings (current voice: ${tts.voice?.name})")
        }

        // 3. Update top bar voice pill
        val activeName = targetVoice?.name ?: tts.voice?.name
        val friendly = if (targetVoice == null) "System Default" else getFriendlyVoiceName(activeName, defaultVoice?.name)
        val displayShort = when {
            friendly.contains("System Default") -> "Voice: System"
            friendly.contains("•") -> "Voice: " + friendly.substringBefore(" •")
            else -> "Voice: " + friendly.take(12)
        }
        binding.tvHeaderVoiceName.text = displayShort
    }

    private fun getFriendlyVoiceName(voiceName: String?, defaultVoiceName: String?): String {
        if (voiceName.isNullOrBlank()) return "System Voice"
        val isDefault = (voiceName == defaultVoiceName)
        val tag = if (isDefault) " [System Default]" else ""

        return when {
            voiceName.contains("iom", ignoreCase = true) -> "Voice I • Clear Male$tag"
            voiceName.contains("iol", ignoreCase = true) -> "Voice II • Conversational Female$tag"
            voiceName.contains("iob", ignoreCase = true) -> "Voice III • Deep Male$tag"
            voiceName.contains("iod", ignoreCase = true) -> "Voice IV • Warm Female (Ava Style)$tag"
            voiceName.contains("tpd", ignoreCase = true) -> "Voice V • Expressive Male$tag"
            voiceName.contains("tpc", ignoreCase = true) -> "Voice VI • Articulate Female$tag"
            voiceName.contains("female_1", ignoreCase = true) -> "Voice VII • Female Studio$tag"
            voiceName.contains("female_2", ignoreCase = true) -> "Voice VIII • Female Studio 2$tag"
            voiceName.contains("male_1", ignoreCase = true) -> "Voice IX • Male Studio$tag"
            voiceName.contains("female", ignoreCase = true) -> "Natural Female$tag"
            voiceName.contains("male", ignoreCase = true) -> "Natural Male$tag"
            else -> "${voiceName.substringAfterLast('#').substringAfterLast('-')}$tag"
        }
    }

    private fun testVoice(voice: Voice?) {
        if (!isTtsReady) return
        if (voice != null) {
            textToSpeech?.voice = voice
        }
        textToSpeech?.speak(
            "Hi, I'm Anti, your voice pair programmer.",
            TextToSpeech.QUEUE_FLUSH,
            null,
            "test_sample_${System.currentTimeMillis()}"
        )
    }

    private fun showVoiceSelectionBottomSheet() {
        val dialog = BottomSheetDialog(this)
        val sheetBinding = SheetVoiceSelectorBinding.inflate(layoutInflater)
        dialog.setContentView(sheetBinding.root)

        val prefs = getSharedPreferences("anti_voice_prefs", MODE_PRIVATE)
        val savedVoiceName = prefs.getString("preferred_voice_name", null)
        val activeVoice = textToSpeech?.voice
        val defaultVoice = textToSpeech?.defaultVoice

        val activeFriendlyName = getFriendlyVoiceName(activeVoice?.name, defaultVoice?.name)
        sheetBinding.tvActiveVoiceTitle.text = activeFriendlyName

        val sysPitch = try {
            val p = android.provider.Settings.Secure.getInt(contentResolver, "tts_default_pitch", 100)
            p / 100f
        } catch (_: Exception) { 1.0f }
        val sysRate = try {
            val r = android.provider.Settings.Secure.getInt(contentResolver, "tts_default_rate", 100)
            r / 100f
        } catch (_: Exception) { 1.0f }

        sheetBinding.tvActiveVoiceDetails.text = "Pitch: ${"%.2f".format(sysPitch)} • Rate: ${"%.2f".format(sysRate)} • Engine: ${textToSpeech?.defaultEngine ?: "Google TTS"}"

        sheetBinding.btnCloseSheet.setOnClickListener { dialog.dismiss() }

        sheetBinding.btnOpenSystemTtsSettings.setOnClickListener {
            dialog.dismiss()
            try {
                val intent = Intent("com.android.settings.TTS_SETTINGS")
                intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                startActivity(intent)
            } catch (e: Exception) {
                Toast.makeText(this, "Could not open TTS settings: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }

        val container = sheetBinding.containerVoiceList
        container.removeAllViews()

        // 1. System Default Option
        val isSystemSelected = (savedVoiceName == null || savedVoiceName == "SYSTEM_DEFAULT")
        val sysItemBinding = ItemVoiceOptionBinding.inflate(layoutInflater, container, false)
        sysItemBinding.tvVoiceFriendlyName.text = "🌟 System Default (Android Settings)"
        sysItemBinding.tvVoiceId.text = "${defaultVoice?.name ?: "System Selected"} • Inherits phone settings"
        sysItemBinding.ivSelectedCheck.visibility = if (isSystemSelected) View.VISIBLE else View.INVISIBLE
        if (isSystemSelected) {
            sysItemBinding.rowVoice.setBackgroundResource(R.drawable.bg_status_pill)
        }

        sysItemBinding.btnTestVoice.setOnClickListener {
            testVoice(defaultVoice)
        }

        sysItemBinding.rowVoice.setOnClickListener {
            prefs.edit().remove("preferred_voice_name").apply()
            applyVoiceConfiguration()
            testVoice(textToSpeech?.voice)
            dialog.dismiss()
            Toast.makeText(this, "Using System Default Voice", Toast.LENGTH_SHORT).show()
        }
        container.addView(sysItemBinding.root)

        // 2. Available Voices List
        val allVoices = try { textToSpeech?.voices?.toList() ?: emptyList() } catch (_: Exception) { emptyList() }
        val usVoices = allVoices.filter {
            it.locale.language.equals("en", ignoreCase = true) &&
            (it.locale.country.equals("US", ignoreCase = true) || it.locale.country.isBlank())
        }.sortedBy { it.name }

        for (voice in usVoices) {
            val isSelected = (!isSystemSelected && savedVoiceName == voice.name)
            val itemBinding = ItemVoiceOptionBinding.inflate(layoutInflater, container, false)

            val friendly = getFriendlyVoiceName(voice.name, defaultVoice?.name)
            itemBinding.tvVoiceFriendlyName.text = friendly
            itemBinding.tvVoiceId.text = "${voice.name} • ${if (voice.isNetworkConnectionRequired) "Cloud Neural" else "On-Device"}"
            itemBinding.ivSelectedCheck.visibility = if (isSelected) View.VISIBLE else View.INVISIBLE
            if (isSelected) {
                itemBinding.rowVoice.setBackgroundResource(R.drawable.bg_status_pill)
            }

            itemBinding.btnTestVoice.setOnClickListener {
                testVoice(voice)
            }

            itemBinding.rowVoice.setOnClickListener {
                prefs.edit().putString("preferred_voice_name", voice.name).apply()
                applyVoiceConfiguration()
                testVoice(voice)
                dialog.dismiss()
                Toast.makeText(this, "Selected $friendly", Toast.LENGTH_SHORT).show()
            }

            container.addView(itemBinding.root)
        }

        dialog.show()
    }

    private fun showRelaySettingsDialog() {
        val context = this
        val layout = android.widget.LinearLayout(context).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }

        val tvUrlLabel = android.widget.TextView(context).apply {
            text = "Cloud Relay URL (HTTPS required):"
            setTextColor(ContextCompat.getColor(context, R.color.text_primary))
            textSize = 14f
        }
        layout.addView(tvUrlLabel)

        val etUrl = android.widget.EditText(context).apply {
            hint = if (BuildConfig.DEBUG) "https://... or http://10.0.2.2:8000" else "https://relay.yourdomain.com"
            setText(AntiVoiceClient.baseUrl)
            setSingleLine(true)
            setTextColor(ContextCompat.getColor(context, R.color.cyan_accent))
            setHintTextColor(ContextCompat.getColor(context, R.color.text_secondary))
        }
        layout.addView(etUrl)

        val tvTokenLabel = android.widget.TextView(context).apply {
            text = "Relay Session Bearer Token:"
            setTextColor(ContextCompat.getColor(context, R.color.text_primary))
            textSize = 14f
            setPadding(0, (12 * resources.displayMetrics.density).toInt(), 0, 0)
        }
        layout.addView(tvTokenLabel)

        val etToken = android.widget.EditText(context).apply {
            hint = "Bearer token"
            setText(AntiVoiceClient.sessionToken)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            setTextColor(ContextCompat.getColor(context, R.color.cyan_accent))
            setHintTextColor(ContextCompat.getColor(context, R.color.text_secondary))
        }
        layout.addView(etToken)

        androidx.appcompat.app.AlertDialog.Builder(context)
            .setTitle("Relay Endpoint Configuration")
            .setView(layout)
            .setPositiveButton("Save") { _, _ ->
                val inputUrl = etUrl.text.toString().trim()
                val inputToken = etToken.text.toString().trim()

                if (inputUrl.isNotBlank() && !AntiVoiceClient.isUrlAllowed(inputUrl, BuildConfig.DEBUG)) {
                    Toast.makeText(
                        context,
                        "Insecure or invalid URL: Only HTTPS endpoints are permitted (HTTP allowed only for localhost in debug builds).",
                        Toast.LENGTH_LONG
                    ).show()
                    return@setPositiveButton
                }

                AntiVoiceClient.baseUrl = inputUrl
                AntiVoiceClient.sessionToken = inputToken

                val prefs = getSecurePreferences()
                prefs.edit()
                    .putString("relay_base_url", inputUrl)
                    .putString("relay_session_token", inputToken)
                    .apply()

                Toast.makeText(context, "Relay settings saved securely.", Toast.LENGTH_SHORT).show()
                checkWorkstationHealth()
            }
            .setNeutralButton("Test Connection") { _, _ ->
                val inputUrl = etUrl.text.toString().trim()
                val inputToken = etToken.text.toString().trim()
                if (inputUrl.isNotBlank() && !AntiVoiceClient.isUrlAllowed(inputUrl, BuildConfig.DEBUG)) {
                    Toast.makeText(context, "Cannot test: Insecure URL.", Toast.LENGTH_SHORT).show()
                    return@setNeutralButton
                }
                AntiVoiceClient.baseUrl = inputUrl
                AntiVoiceClient.sessionToken = inputToken
                checkWorkstationHealth()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun checkWorkstationHealth() {
        lifecycleScope.launch {
            binding.tvWorkstationStatus.text = getString(R.string.status_connecting)
            val isOnline = AntiVoiceClient.checkHealth()
            if (isOnline) {
                binding.tvWorkstationStatus.text = getString(R.string.status_online)
                binding.tvWorkstationStatus.setTextColor(ContextCompat.getColor(this@AntiVoiceActivity, R.color.status_online))
                binding.dotStatus.setBackgroundResource(R.drawable.bg_pulse_dot)
            } else {
                binding.tvWorkstationStatus.text = "WORKSTATION: OFFLINE"
                binding.tvWorkstationStatus.setTextColor(ContextCompat.getColor(this@AntiVoiceActivity, R.color.status_offline))
            }
        }
    }

    private fun setupListeners() {
        // Central glowing mic button
        binding.btnMic.setOnClickListener {
            if (isListening) {
                stopListening()
            } else {
                checkPermissionAndListen()
            }
        }

        // Quick developer action chips
        binding.chipTests.setOnClickListener {
            executeCommand("Anti, run the unit test suite and report results.")
        }
        binding.chipGit.setOnClickListener {
            executeCommand("Anti, check git status and modified files.")
        }
        binding.chipHealth.setOnClickListener {
            executeCommand("Anti, check production health and server logs.")
        }
        binding.chipDeploy.setOnClickListener {
            executeCommand("Anti, deploy the latest changes to production.")
        }
        binding.chipCommits.setOnClickListener {
            executeCommand("Anti, summarize recent commits on this branch.")
        }

        // Response actions: Play / Pause / Resume
        binding.btnReplayVoice.setOnClickListener {
            if (lastSpokenResponse.isBlank()) return@setOnClickListener

            if (isTtsSpeaking || (textToSpeech?.isSpeaking == true)) {
                // User clicked while speaking -> PAUSE
                textToSpeech?.stop()
                isTtsSpeaking = false
                isTtsPaused = true
                binding.btnReplayVoice.text = "▶ Resume Voice"
                binding.tvMicPrompt.text = "Voice paused • Tap to resume"
            } else if (isTtsPaused) {
                // User clicked while paused -> RESUME from last spoken character position
                val remainingText = if (currentSpeechCharIndex > 0 && currentSpeechCharIndex < lastSpokenResponse.length) {
                    lastSpokenResponse.substring(currentSpeechCharIndex).trim()
                } else {
                    lastSpokenResponse
                }
                isTtsPaused = false
                speak(if (remainingText.isNotBlank()) remainingText else lastSpokenResponse)
            } else {
                // Idle -> REPLAY from beginning
                currentSpeechCharIndex = 0
                isTtsPaused = false
                speak(lastSpokenResponse)
            }
        }
        binding.btnHeaderVoice.setOnClickListener {
            showVoiceSelectionBottomSheet()
        }
        binding.btnVoiceSettings.setOnClickListener {
            showRelaySettingsDialog()
        }

        // Manual text input
        binding.btnSend.setOnClickListener {
            val text = binding.etCommandInput.text.toString().trim()
            if (text.isNotBlank()) {
                binding.etCommandInput.text?.clear()
                executeCommand(text)
            }
        }
        binding.etCommandInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                val text = binding.etCommandInput.text.toString().trim()
                if (text.isNotBlank()) {
                    binding.etCommandInput.text?.clear()
                    executeCommand(text)
                }
                true
            } else false
        }
    }

    private fun checkPermissionAndListen() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Toast.makeText(this, "Speech recognition not available on device", Toast.LENGTH_SHORT).show()
            return
        }

        speechRecognizer?.destroy()
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    isListening = true
                    binding.tvMicPrompt.text = getString(R.string.listening_prompt)
                    binding.progressWorking.visibility = View.VISIBLE
                }

                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}

                override fun onEndOfSpeech() {
                    isListening = false
                    binding.tvMicPrompt.text = "Processing speech..."
                }

                override fun onError(error: Int) {
                    isListening = false
                    binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                    binding.progressWorking.visibility = View.INVISIBLE
                }

                override fun onResults(results: Bundle?) {
                    isListening = false
                    binding.progressWorking.visibility = View.INVISIBLE
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val spokenText = matches?.firstOrNull()
                    if (!spokenText.isNullOrBlank()) {
                        executeCommand(spokenText)
                    } else {
                        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) {}
                override fun onEvent(eventType: Int, params: Bundle?) {}
            })
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toString())
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        }

        speechRecognizer?.startListening(intent)
    }

    private fun stopListening() {
        isListening = false
        speechRecognizer?.stopListening()
        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
        binding.progressWorking.visibility = View.INVISIBLE
    }

    private fun executeCommand(command: String) {
        activePollJob?.cancel()
        textToSpeech?.stop()
        isTtsSpeaking = false
        isTtsPaused = false
        currentSpeechCharIndex = 0
        binding.btnReplayVoice.text = getString(R.string.btn_replay)

        // Display spoken card
        binding.cardWelcome.visibility = View.GONE
        binding.cardSpoken.visibility = View.VISIBLE
        binding.tvSpokenText.text = "> $command"

        // Update working state
        binding.tvMicPrompt.text = "Relaying to Antigravity IDE..."
        binding.progressWorking.visibility = View.VISIBLE

        lifecycleScope.launch {
            val dispatch = AntiVoiceClient.dispatchInstruction(command)
            if (!dispatch.success) {
                binding.progressWorking.visibility = View.INVISIBLE
                binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                Toast.makeText(this@AntiVoiceActivity, "Dispatch failed: ${dispatch.errorMessage}", Toast.LENGTH_LONG).show()
                return@launch
            }

            // Speak brief confirmation
            speak(dispatch.spokenConfirmation)
            binding.tvMicPrompt.text = "Working in desktop IDE..."

            // Poll for execution completion
            activePollJob = launch {
                val dispatchId = dispatch.dispatchId
                var attempts = 0
                val maxAttempts = 60 // 60s timeout

                while (attempts < maxAttempts) {
                    delay(1200)
                    attempts++

                    val status = AntiVoiceClient.pollStatus(dispatchId)
                    if (status.status == "EXECUTED") {
                        val summary = status.executionSummary ?: "Execution completed."
                        lastSpokenResponse = summary

                        // Update response card with formatted text
                        binding.cardResponse.visibility = View.VISIBLE
                        binding.tvExecutionStatus.text = "EXECUTED"
                        binding.tvExecutionStatus.setTextColor(ContextCompat.getColor(this@AntiVoiceActivity, R.color.status_online))
                        binding.tvResponseText.text = renderFormattedResponse(summary)

                        // Speak full response via WaveNet
                        speak(summary)

                        binding.progressWorking.visibility = View.INVISIBLE
                        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                        break
                    } else if (status.status == "FAILED") {
                        binding.cardResponse.visibility = View.VISIBLE
                        binding.tvExecutionStatus.text = "FAILED"
                        binding.tvExecutionStatus.setTextColor(ContextCompat.getColor(this@AntiVoiceActivity, R.color.status_offline))
                        binding.tvResponseText.text = "Execution failed on desktop workstation."

                        binding.progressWorking.visibility = View.INVISIBLE
                        binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                        speak("Execution failed on desktop workstation.")
                        break
                    }
                }

                if (attempts >= maxAttempts) {
                    binding.progressWorking.visibility = View.INVISIBLE
                    binding.tvMicPrompt.text = getString(R.string.tap_to_speak)
                }
            }
        }
    }

    private fun cleanMarkdownForSpeech(raw: String): String {
        if (raw.isBlank()) return ""
        var text = raw
        // 1. Remove code blocks
        text = text.replace(Regex("```[\\s\\S]*?```"), "")
        // 2. Remove inline code backticks: `code` -> code
        text = text.replace(Regex("`([^`]+)`"), "$1")
        // 3. Clean markdown links: [Title](url) -> Title
        text = text.replace(Regex("\\[([^\\]]+)\\]\\([^\\)]+\\)"), "$1")
        // 4. Remove raw URLs and file paths
        text = text.replace(Regex("https?://\\S+"), "")
        text = text.replace(Regex("file:///\\S+"), "")
        // 5. Remove bold/italic markers (*, _)
        text = text.replace(Regex("[*_]{1,3}([^*_]+)[*_]{1,3}"), "$1")
        // 6. Remove headers (#, ##, ###)
        text = text.replace(Regex("(?m)^#+\\s*"), "")
        // 7. Remove bullet points
        text = text.replace(Regex("(?m)^[*-]\\s+"), "")
        // 8. Remove blockquotes (> )
        text = text.replace(Regex("(?m)^>\\s*"), "")
        // 9. Normalize 'Anti' pronunciation to 'Ante' for natural inflection
        text = text.replace(Regex("\\bAnti\\b", RegexOption.IGNORE_CASE), "Ante")
        // 10. Collapse multiple spaces and newlines
        text = text.replace(Regex("\\s+"), " ").trim()
        return text
    }

    private fun speak(text: String) {
        if (!isTtsReady || text.isBlank()) return
        val speechText = cleanMarkdownForSpeech(text)
        if (speechText.isBlank()) return
        textToSpeech?.speak(speechText, TextToSpeech.QUEUE_FLUSH, null, "anti_utterance_${System.currentTimeMillis()}")
    }

    private fun renderFormattedResponse(raw: String): CharSequence {
        if (raw.isBlank()) return ""

        var html = raw
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")

        // Code blocks: ```...``` -> monospace cyan formatted block
        html = html.replace(Regex("```([a-zA-Z]*)\\n([\\s\\S]*?)```")) { match ->
            val code = match.groupValues[2].trim()
            "<br/><tt><font color=\"#00F0FF\">${code.replace("\n", "<br/>")}</font></tt><br/>"
        }

        // Inline code: `...` -> monospace cyan
        html = html.replace(Regex("`([^`]+)`")) { match ->
            "<tt><font color=\"#00F0FF\">${match.groupValues[1]}</font></tt>"
        }

        // Headers: ### or ##
        html = html.replace(Regex("(?m)^#{2,3}\\s+(.+)$")) { match ->
            "<br/><b><font color=\"#00F0FF\">${match.groupValues[1]}</font></b><br/>"
        }

        // Bold: **text**
        html = html.replace(Regex("\\*\\*([^*]+)\\*\\*")) { match ->
            "<b><font color=\"#FFFFFF\">${match.groupValues[1]}</font></b>"
        }

        // Italic: *text*
        html = html.replace(Regex("(?<!\\*)\\*([^*]+)\\*(?!\\*)")) { match ->
            "<i>${match.groupValues[1]}</i>"
        }

        // Bullet lists: * item or - item
        html = html.replace(Regex("(?m)^[*-]\\s+(.+)$")) { match ->
            "&nbsp;&nbsp;&bull;&nbsp;${match.groupValues[1]}<br/>"
        }

        // Numbered lists: 1. item
        html = html.replace(Regex("(?m)^(\\d+)\\.\\s+(.+)$")) { match ->
            "&nbsp;&nbsp;<b>${match.groupValues[1]}.</b> ${match.groupValues[2]}<br/>"
        }

        // Convert standard newlines
        html = html.replace("\n", "<br/>")

        return androidx.core.text.HtmlCompat.fromHtml(html, androidx.core.text.HtmlCompat.FROM_HTML_MODE_LEGACY)
    }

    override fun onDestroy() {
        super.onDestroy()
        speechRecognizer?.destroy()
        textToSpeech?.stop()
        textToSpeech?.shutdown()
        activePollJob?.cancel()
    }
}
