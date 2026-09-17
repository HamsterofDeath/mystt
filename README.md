# Local Whisper PTT Service

Lokaler HTTP-Dienst fuer Push-to-Talk-Diktat von einer Ubuntu-VM auf den Windows-Host.

## Aktueller Standard

- Oeffentlicher Endpoint: `POST /transcribe`
- Security: `X-PTT-Token`
- Aktives Backend auf diesem Host: `openai` (OpenAI Audio Transcriptions API)
- Default-Modell: `gpt-4o-transcribe`
- Externe Service-URL fuer die VM: `http://192.168.56.1:8765/transcribe`
- Startverhalten: HTTP-Dienst beim Login, Modell per Lazy-Load beim ersten Request
- Anti-Halluzinationen fuer den OpenAI-Pfad: vorgelagerte WAV-Silence-Gate; die lokalen VAD-/No-Context-Optionen gelten nur fuer `whispercpp`

Der API-Key wird aus der Windows-Benutzerumgebung (`OPENAI_API_KEY`) gelesen, optional zusaetzlich aus `.env`. Der Download des OpenAI-Modells entfaellt, daher kein GPU-Build und keine lokalen Modelle noetig. Die lokalen Backends `whispercpp` (Vulkan) und `faster-whisper` (CPU/CUDA) bleiben als Fallback im Python-Service erhalten.

## Schnellstart

Python-Umgebung:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-whisper-service.ps1
```

Vulkan-Binary + Modell bauen:

```powershell
.\build-whispercpp-vulkan.ps1
```

Oeffentlichen Dienst starten:

```powershell
.\start-whisper-service.ps1
```

Optionaler Autostart:

```powershell
.\register-whisper-service-task.ps1
```

Der geplante Login-Start startet nur den leichten Python-HTTP-Dienst. Das eigentliche ASR-Modell wird erst beim ersten `/transcribe` geladen und nach Leerlauf wieder entladen.

Bei grossen Modellen wie `large-v3` ist der erste Request nach dem Idle-Zustand deutlich langsamer als Folge-Requests. Wenn dir dieser Cold-Start zu teuer ist, setze `ASR_PRELOAD_ON_START=true` oder erhoehe `ASR_IDLE_UNLOAD_SECONDS`.

## Request-Beispiel

Ubuntu-VM:

```bash
curl -s -X POST http://192.168.56.1:8765/transcribe \
  -H "X-PTT-Token: $PTT_TOKEN" \
  -F "audio=@recording.wav" \
  -F "language=de"
```

Windows-Test:

```powershell
.\test-transcribe.ps1
```

## Konfiguration

Wichtige Werte in `.env` (OpenAI-Backend):

- `ASR_BACKEND=openai`
- `OPENAI_MODEL=gpt-4o-transcribe`
- `OPENAI_TIMEOUT_MS=120000`
- `OPENAI_BASE_URL=https://api.openai.com/v1`

Nur fuer den lokalen `whispercpp`-Fallback:

- `WHISPER_MODEL=small`
- `WHISPERCPP_BINARY_PATH=whisper.cpp/build-vulkan-vs2022/bin/Release/whisper-server.exe`
- `WHISPERCPP_MODEL_PATH=whisper.cpp/models/ggml-small.bin`
- `WHISPERCPP_SERVER_PORT=8766`
- `WHISPERCPP_VAD_ENABLED=true`
- `WHISPERCPP_VAD_MODEL_PATH=whisper.cpp/models/ggml-silero-v6.2.0.bin`
- `WHISPERCPP_VAD_THRESHOLD=0.6`
- `WHISPERCPP_NO_CONTEXT=true`
- `WHISPERCPP_SUPPRESS_NST=true`
- `WHISPERCPP_NO_FALLBACK=true`
- `WHISPERCPP_NO_SPEECH_THRESHOLD=0.75`
- `WAV_SILENCE_GATE_ENABLED=true`
- `WAV_SILENCE_PEAK_DBFS=-45`
- `WAV_SILENCE_RMS_DBFS=-55`
- `ASR_PRELOAD_ON_START=false`
- `ASR_IDLE_UNLOAD_SECONDS=900`
- `ASR_IDLE_CHECK_SECONDS=15`

Wenn du auf den alten CPU-/CUDA-Pfad zurueck willst, setze `ASR_BACKEND=faster-whisper` und starte den Dienst neu.

## Avast-Hinweis

Falls Avast CyberCapture den Vulkan-Build blockiert, fuege am besten eine Ausnahme fuer diesen Ordner hinzu:

```text
C:\Users\dhaup\OneDrive\Dokumente\Playground\whisper.cpp\build-vulkan-vs2022
```
