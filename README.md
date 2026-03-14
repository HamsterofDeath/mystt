# Local Whisper PTT Service

Lokaler HTTP-Dienst fuer Push-to-Talk-Diktat von einer Ubuntu-VM auf den Windows-Host.

## Aktueller Standard

- Oeffentlicher Endpoint: `POST /transcribe`
- Security: `X-PTT-Token`
- Default-Modell: `small`
- Aktives Backend auf diesem Host: `whisper.cpp` mit `Vulkan`
- Aktives Device auf diesem Host: `AMD Radeon RX 7900 XTX`
- Externe Service-URL fuer die VM: `http://192.168.56.1:8765/transcribe`

Der bisherige `faster-whisper`-Pfad bleibt als CPU-/CUDA-Fallback im Python-Service erhalten. Aktiv ist im Moment aber `ASR_BACKEND=whispercpp`.

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

## Request-Beispiel

Ubuntu-VM:

```bash
curl -s -X POST http://192.168.56.1:8765/transcribe \
  -H "X-PTT-Token: 9368cbde5e5e493485b6b991e8ddb51e" \
  -F "audio=@recording.wav" \
  -F "language=de"
```

Windows-Test:

```powershell
.\test-transcribe.ps1
```

## Konfiguration

Wichtige Werte in `.env`:

- `ASR_BACKEND=whispercpp`
- `WHISPER_MODEL=small`
- `WHISPERCPP_BINARY_PATH=whisper.cpp/build-vulkan-vs2022/bin/Release/whisper-server.exe`
- `WHISPERCPP_MODEL_PATH=whisper.cpp/models/ggml-small.bin`
- `WHISPERCPP_SERVER_PORT=8766`

Wenn du auf den alten CPU-/CUDA-Pfad zurueck willst, setze `ASR_BACKEND=faster-whisper` und starte den Dienst neu.

## Avast-Hinweis

Falls Avast CyberCapture den Vulkan-Build blockiert, fuege am besten eine Ausnahme fuer diesen Ordner hinzu:

```text
C:\Users\dhaup\OneDrive\Dokumente\Playground\whisper.cpp\build-vulkan-vs2022
```
