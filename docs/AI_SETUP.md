# Choose your AI

Inside AE, open CapForge → **Setup**. Click **Start service** and wait for **Studio connected**.
Choose an AI service for its three-step guide. **Open account** opens your regular
browser; your captions workflow stays inside After Effects.

An API key is a private access code for your AI account. Paste it, then choose
**Save key & use this AI**. The field clears and Source selects that provider.
Saving checks the key’s format and stores it; it does not verify the account,
check billing or spend transcription credits. Try a short clip first.

| Service | What you need | Official instructions |
| --- | --- | --- |
| ElevenLabs | API key with Speech to Text permission; check API credits | [Keys](https://elevenlabs.io/app/settings/api-keys), [transcription guide](https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/batch/telegram-bot) |
| OpenAI | Project API key and API billing; leave Model blank for whisper-1 word timing | [Keys](https://platform.openai.com/api-keys), [speech-to-text guide](https://platform.openai.com/docs/guides/speech-to-text) |
| Gladia | Dashboard API key; check credits and plan limits | [Dashboard](https://app.gladia.io), [key guide](https://support.gladia.io/article/how-to-get-the-api-key-from-my-account) |
| AssemblyAI | Project API key; check usage and billing | [Dashboard](https://www.assemblyai.com/dashboard), [account management](https://www.assemblyai.com/docs/faq/how-to-get-your-api-key) |
| Azure Speech | Speech resource key and exact region, from Keys and Endpoint | [Portal](https://portal.azure.com), [resource credentials](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-private-link) |

OpenAI API billing is separate from ChatGPT. Cloud providers process your audio
and may charge your account. Language quality and provider limits vary. The first
transcription verifies the account. Review words and timing before generating.

Keys are saved as plaintext in the installation’s `backend/.env`, rather than
browser storage or exported looks. Keep that file private. Show/Hide controls the
password field; leaving the panel hides it again. Switching providers clears it.

## Optional advanced setup

Google and local Whisper need additional software or models. Stop the service
before installing packages and restart it afterwards. Use the environment inside
your **installed CapForge folder**, so no separate system Python is needed.
Install only the package for your chosen provider:

```powershell
# Windows: choose one
& .\.venv\Scripts\python.exe -m pip install google-cloud-speech
& .\.venv\Scripts\python.exe -m pip install faster-whisper
```

```sh
# macOS: choose one; MLX requires Apple Silicon
./.venv/bin/python -m pip install google-cloud-speech
./.venv/bin/python -m pip install faster-whisper
./.venv/bin/python -m pip install mlx-whisper
```

**Google Chirp:** follow [Google’s setup guide](https://cloud.google.com/speech-to-text/v2/docs/before-you-begin)
for a project, billing, Speech-to-Text access and credentials. Set these values
in the installed `backend/.env`. Credentials is a file path, not a pasted key.
Choose a location that supports your language and model.

```text
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/credentials.json
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=eu
```

**whisper.cpp:** follow the [official guide](https://github.com/ggml-org/whisper.cpp).
CapForge scans `/opt/homebrew/bin`, `/usr/local/bin`, `~/whisper.cpp/build/bin`,
`C:\whisper.cpp\build\bin`, `C:\whisper\bin`, and the service’s PATH for
`whisper-cli`, `whisper-cpp`, or `main`. Place a multilingual `ggml-*.bin` model
in `~/models/whisper` (Windows: your user folder’s `models\whisper`).
`ggml-large-v3-turbo.bin` is preferred first. Word timing is experimental.
Avoid `.en` models for Georgian. A custom model path can go in Source → Advanced
transcription → Model once a scanned model makes the provider available.

**faster-whisper:** install its package, then leave Model blank for `large-v3`,
or enter a multilingual model name such as `medium`. First use downloads the
model. Larger models need more memory and time; CPU processing can be slow.
See the [official guide](https://github.com/SYSTRAN/faster-whisper).

**MLX Whisper:** requires Apple Silicon and its optional package. Leave Model
blank for the adapter’s default, or enter a compatible MLX model repository.
See the [official guide](https://github.com/ml-explore/mlx-examples/tree/main/whisper).

Local transcription can run offline once the model is installed and cached.
Availability means the required software is found, rather than a model download
or a successful transcription being verified. Restart the service and check
connection after configuring these integrations.

## When something needs attention

- **Cannot save a key:** use the panel inside AE, start the service and check
  connection. Avoid spaces, quotes and line breaks in the key.
- **Account rejected:** replace the key from the correct account; check its
  permissions and credits. Do not share your key in support messages.
- **Azure region error:** use the resource’s region code, not its display name
  or endpoint URL.
- **Provider needs setup:** optional packages belong in CapForge’s private
  environment. Restart the service after changing `.env`.
- **Audio preparation unavailable:** rerun the guided installer to repair audio
  support; no manual FFmpeg installation is needed.
