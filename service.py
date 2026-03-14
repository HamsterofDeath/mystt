from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from faster_whisper import WhisperModel


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
TMP_DIR = ROOT / ".tmp"
SUPPORTED_LANGUAGES = {"de", "en"}

load_dotenv(ENV_PATH)


@dataclass
class Settings:
    token: str
    bind_host: str
    port: int
    host_accessible_ip: str
    model_name: str
    requested_device: str
    requested_compute_type: str
    cpu_threads: int
    download_root: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", "0"))
        if cpu_threads <= 0:
            cpu_threads = max(1, os.cpu_count() or 4)

        download_root_raw = os.getenv("WHISPER_DOWNLOAD_ROOT", "models")
        download_root = Path(download_root_raw)
        if not download_root.is_absolute():
            download_root = ROOT / download_root

        return cls(
            token=os.getenv("PTT_TOKEN", "").strip(),
            bind_host=os.getenv("SERVICE_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=int(os.getenv("SERVICE_PORT", "8765")),
            host_accessible_ip=os.getenv("HOST_ACCESSIBLE_IP", "192.168.56.1").strip() or "192.168.56.1",
            model_name=os.getenv("WHISPER_MODEL", "small").strip() or "small",
            requested_device=os.getenv("WHISPER_DEVICE", "auto").strip().lower() or "auto",
            requested_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "auto").strip().lower() or "auto",
            cpu_threads=cpu_threads,
            download_root=download_root,
            log_level=os.getenv("LOG_LEVEL", "info").strip().lower() or "info",
        )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def has_nvidia_cuda() -> bool:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False

    return completed.returncode == 0 and "GPU" in completed.stdout


def normalize_language(language: str | None) -> str | None:
    if language is None:
        return None

    normalized = language.strip().lower()
    if not normalized:
        return None
    if normalized not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="language must be empty, 'de', or 'en'",
        )
    return normalized


class TranscriptionEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: WhisperModel | None = None
        self.device = "uninitialized"
        self.compute_type = "unknown"

    def requested_device(self) -> str:
        if self.settings.requested_device in {"cpu", "cuda"}:
            return self.settings.requested_device
        if has_nvidia_cuda():
            return "cuda"
        return "cpu"

    def requested_compute_type(self, device: str) -> str:
        if self.settings.requested_compute_type != "auto":
            return self.settings.requested_compute_type
        if device == "cuda":
            return "float16"
        return "int8"

    def load(self) -> None:
        if not self.settings.token:
            raise RuntimeError("PTT_TOKEN is missing in .env")

        if self.model is not None:
            return

        self.settings.download_root.mkdir(parents=True, exist_ok=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        requested_device = self.requested_device()
        requested_compute_type = self.requested_compute_type(requested_device)
        logging.info(
            "Loading model '%s' on %s (%s)",
            self.settings.model_name,
            requested_device,
            requested_compute_type,
        )

        try:
            self.model = WhisperModel(
                self.settings.model_name,
                device=requested_device,
                compute_type=requested_compute_type,
                cpu_threads=self.settings.cpu_threads,
                download_root=str(self.settings.download_root),
            )
            self.device = requested_device
            self.compute_type = requested_compute_type
            return
        except Exception as exc:
            if requested_device != "cuda":
                raise
            logging.warning("CUDA init failed, falling back to CPU: %s", exc)

        self.model = WhisperModel(
            self.settings.model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=self.settings.cpu_threads,
            download_root=str(self.settings.download_root),
        )
        self.device = "cpu"
        self.compute_type = "int8"

    def transcribe(self, audio_path: Path, language: str | None) -> dict[str, object]:
        self.load()
        assert self.model is not None

        started_at = time.perf_counter()
        segments, info = self.model.transcribe(
            str(audio_path),
            task="transcribe",
            language=language,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            vad_filter=False,
            temperature=0.0,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        duration_ms = int((time.perf_counter() - started_at) * 1000)

        return {
            "text": text,
            "language": info.language or language or "",
            "duration_ms": duration_ms,
            "device": self.device,
            "model": self.settings.model_name,
        }


SETTINGS = Settings.from_env()
configure_logging(SETTINGS.log_level)
ENGINE = TranscriptionEngine(SETTINGS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ENGINE.load()
    logging.info(
        "Whisper service ready at http://%s:%s (reachable from VM at http://%s:%s)",
        SETTINGS.bind_host,
        SETTINGS.port,
        SETTINGS.host_accessible_ip,
        SETTINGS.port,
    )
    yield


app = FastAPI(title="Local Whisper PTT Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    ENGINE.load()
    return {
        "status": "ok",
        "device": ENGINE.device,
        "model": SETTINGS.model_name,
        "host_accessible_url": f"http://{SETTINGS.host_accessible_ip}:{SETTINGS.port}",
    }


@app.post("/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    x_ptt_token: str | None = Header(default=None, alias="X-PTT-Token"),
) -> dict[str, object]:
    if not x_ptt_token or not secrets.compare_digest(x_ptt_token, SETTINGS.token):
        raise HTTPException(status_code=401, detail="invalid token")

    selected_language = normalize_language(request.query_params.get("language") or language)

    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=TMP_DIR) as handle:
            shutil.copyfileobj(audio.file, handle)
            temp_path = Path(handle.name)
        return ENGINE.transcribe(temp_path, selected_language)
    finally:
        await audio.close()
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def preload_from_env() -> None:
    ENGINE.load()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=SETTINGS.bind_host,
        port=SETTINGS.port,
        log_level=SETTINGS.log_level,
    )

