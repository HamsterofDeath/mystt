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

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from faster_whisper import WhisperModel


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
TMP_DIR = ROOT / ".tmp"
SUPPORTED_LANGUAGES = {"de", "en"}
LANGUAGE_ALIASES = {
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "en": "en",
    "english": "en",
}

load_dotenv(ENV_PATH)


def env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_path(raw_path: str, default_relative: str) -> Path:
    candidate = Path(raw_path.strip() or default_relative)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate


@dataclass
class Settings:
    token: str
    bind_host: str
    port: int
    host_accessible_ip: str
    backend: str
    model_name: str
    requested_device: str
    requested_compute_type: str
    cpu_threads: int
    download_root: Path
    whispercpp_binary_path: Path
    whispercpp_model_path: Path
    whispercpp_server_host: str
    whispercpp_server_port: int
    whispercpp_threads: int
    whispercpp_processors: int
    whispercpp_flash_attn: bool
    whispercpp_managed_server: bool
    whispercpp_timeout_ms: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", "0"))
        if cpu_threads <= 0:
            cpu_threads = max(1, os.cpu_count() or 4)

        download_root = resolve_path(os.getenv("WHISPER_DOWNLOAD_ROOT", "models"), "models")
        whispercpp_binary_path = resolve_path(
            os.getenv("WHISPERCPP_BINARY_PATH", "whisper.cpp/build-vulkan-vs2022/bin/Release/whisper-server.exe"),
            "whisper.cpp/build-vulkan-vs2022/bin/Release/whisper-server.exe",
        )
        whispercpp_model_path = resolve_path(
            os.getenv("WHISPERCPP_MODEL_PATH", "whisper.cpp/models/ggml-small.bin"),
            "whisper.cpp/models/ggml-small.bin",
        )

        return cls(
            token=os.getenv("PTT_TOKEN", "").strip(),
            bind_host=os.getenv("SERVICE_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=int(os.getenv("SERVICE_PORT", "8765")),
            host_accessible_ip=os.getenv("HOST_ACCESSIBLE_IP", "192.168.56.1").strip() or "192.168.56.1",
            backend=os.getenv("ASR_BACKEND", "faster-whisper").strip().lower() or "faster-whisper",
            model_name=os.getenv("WHISPER_MODEL", "small").strip() or "small",
            requested_device=os.getenv("WHISPER_DEVICE", "auto").strip().lower() or "auto",
            requested_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "auto").strip().lower() or "auto",
            cpu_threads=cpu_threads,
            download_root=download_root,
            whispercpp_binary_path=whispercpp_binary_path,
            whispercpp_model_path=whispercpp_model_path,
            whispercpp_server_host=os.getenv("WHISPERCPP_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1",
            whispercpp_server_port=int(os.getenv("WHISPERCPP_SERVER_PORT", "8766")),
            whispercpp_threads=int(os.getenv("WHISPERCPP_THREADS", "8")),
            whispercpp_processors=int(os.getenv("WHISPERCPP_PROCESSORS", "1")),
            whispercpp_flash_attn=env_flag("WHISPERCPP_FLASH_ATTN", True),
            whispercpp_managed_server=env_flag("WHISPERCPP_MANAGED_SERVER", True),
            whispercpp_timeout_ms=int(os.getenv("WHISPERCPP_TIMEOUT_MS", "120000")),
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


def normalize_detected_language(language: str | None, fallback: str | None) -> str:
    if language:
        normalized = LANGUAGE_ALIASES.get(language.strip().lower())
        if normalized:
            return normalized
    return fallback or ""


def clean_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned == "[BLANK_AUDIO]":
        return ""
    return cleaned


class FasterWhisperEngine:
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
            "Loading faster-whisper model '%s' on %s (%s)",
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


class WhisperCppEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"http://{settings.whispercpp_server_host}:{settings.whispercpp_server_port}"
        self.process: subprocess.Popen[str] | None = None
        self.stdout_handle = None
        self.stderr_handle = None
        self.device = "vulkan"

    def _is_ready(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/", timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _stderr_tail(self) -> str:
        stderr_path = ROOT / "whispercpp.stderr.log"
        if not stderr_path.exists():
            return ""
        return "\n".join(stderr_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:])

    def _start_server(self) -> None:
        if self.process and self.process.poll() is None:
            return

        if not self.settings.whispercpp_binary_path.exists():
            raise RuntimeError(f"whisper.cpp server not found at {self.settings.whispercpp_binary_path}")
        if not self.settings.whispercpp_model_path.exists():
            raise RuntimeError(f"whisper.cpp model not found at {self.settings.whispercpp_model_path}")

        stdout_path = ROOT / "whispercpp.stdout.log"
        stderr_path = ROOT / "whispercpp.stderr.log"
        self.stdout_handle = open(stdout_path, "w", encoding="utf-8")
        self.stderr_handle = open(stderr_path, "w", encoding="utf-8")

        args = [
            str(self.settings.whispercpp_binary_path),
            "--host",
            self.settings.whispercpp_server_host,
            "--port",
            str(self.settings.whispercpp_server_port),
            "-m",
            str(self.settings.whispercpp_model_path),
            "-l",
            "auto",
            "-t",
            str(self.settings.whispercpp_threads),
            "-p",
            str(self.settings.whispercpp_processors),
            "-bo",
            "1",
            "-bs",
            "1",
        ]
        if self.settings.whispercpp_flash_attn:
            args.append("-fa")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            args,
            cwd=str(self.settings.whispercpp_binary_path.parent),
            stdout=self.stdout_handle,
            stderr=self.stderr_handle,
            text=True,
            creationflags=creationflags,
        )

    def load(self) -> None:
        if not self.settings.token:
            raise RuntimeError("PTT_TOKEN is missing in .env")

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        if self._is_ready():
            return

        if not self.settings.whispercpp_managed_server:
            raise RuntimeError(f"whisper.cpp backend is not reachable at {self.base_url}")

        logging.info(
            "Starting whisper.cpp Vulkan backend on %s using %s",
            self.base_url,
            self.settings.whispercpp_model_path,
        )
        self._start_server()

        deadline = time.time() + 120
        while time.time() < deadline:
            if self._is_ready():
                return
            if self.process and self.process.poll() is not None:
                raise RuntimeError(
                    "whisper.cpp server exited during startup:\n" + self._stderr_tail()
                )
            time.sleep(1)

        raise RuntimeError("whisper.cpp server did not become ready in time")

    def transcribe(self, audio_path: Path, language: str | None) -> dict[str, object]:
        self.load()

        started_at = time.perf_counter()
        data = {
            "language": language or "auto",
            "response_format": "verbose_json",
            "temperature": "0.0",
            "temperature_inc": "0.0",
        }
        with audio_path.open("rb") as audio_file:
            response = httpx.post(
                f"{self.base_url}/inference",
                data=data,
                files={"file": (audio_path.name, audio_file, "audio/wav")},
                timeout=self.settings.whispercpp_timeout_ms / 1000,
            )
        response.raise_for_status()
        payload = response.json()

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        detected_language = (
            payload.get("detected_language")
            or payload.get("language")
            or language
            or ""
        )

        return {
            "text": clean_text(str(payload.get("text", ""))),
            "language": normalize_detected_language(str(detected_language), language),
            "duration_ms": duration_ms,
            "device": self.device,
            "model": self.settings.model_name,
        }


SETTINGS = Settings.from_env()
configure_logging(SETTINGS.log_level)
ENGINE = WhisperCppEngine(SETTINGS) if SETTINGS.backend == "whispercpp" else FasterWhisperEngine(SETTINGS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ENGINE.load()
    logging.info(
        "ASR service ready at http://%s:%s using backend=%s (reachable from VM at http://%s:%s)",
        SETTINGS.bind_host,
        SETTINGS.port,
        SETTINGS.backend,
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
        "backend": SETTINGS.backend,
        "device": getattr(ENGINE, "device", "unknown"),
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

