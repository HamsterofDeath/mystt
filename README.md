# Local Whisper PTT Service

Kleiner lokaler HTTP-Service fuer Push-to-Talk-Diktat von einer Ubuntu-VM auf den Windows-Host.

## Design

- Backend: `faster-whisper`
- HTTP: FastAPI
- Security: Shared secret ueber `X-PTT-Token`
- Default-Modell: `small`
- Device auf diesem Host: CPU

Warum CPU auf diesem Rechner: Es ist eine AMD Radeon RX 7900 XTX vorhanden, aber `faster-whisper` nutzt auf Windows fuer GPU-Beschleunigung praktisch CUDA und damit NVIDIA. Deshalb ist hier CPU der robuste und funktionierende Pfad.

## Installieren

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-whisper-service.ps1
```

Das Skript erstellt `.venv`, installiert die Python-Abhaengigkeiten, laedt das `small`-Modell vor und versucht eine Firewall-Regel fuer den Port anzulegen.

Wenn die Ubuntu-VM den Dienst nicht erreicht, fuehre das Installationsskript einmal in einer als Administrator gestarteten PowerShell aus, damit die Firewall-Regel wirklich gesetzt werden kann.

## Starten

```powershell
.\start-whisper-service.ps1
```

Alternativ:

```cmd
start-whisper-service.cmd
```

## VM-Zieladresse

Fuer eine VirtualBox-VM auf diesem Host ist die passende Host-Adresse:

```text
http://192.168.56.1:8765/transcribe
```

Der Dienst lauscht auf `0.0.0.0`, also auch auf anderen Host-Interfaces wie `192.168.0.199`, aber fuer die Host-Only-VM ist `192.168.56.1` die passende Adresse.

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

- `PTT_TOKEN`: Shared secret
- `SERVICE_PORT`: Standard `8765`
- `WHISPER_MODEL`: Standard `small`, fuer spaeter auch `medium` moeglich
- `WHISPER_DEVICE`: `auto`, `cpu` oder `cuda`

Wenn du spaeter auf einem NVIDIA/CUDA-Host landest, kannst du `WHISPER_DEVICE=auto` lassen und bei Bedarf `WHISPER_MODEL=medium` setzen.
