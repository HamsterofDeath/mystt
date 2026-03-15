from __future__ import annotations

import math
import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from array import array
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import gc

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
    whispercpp_vad_enabled: bool
    whispercpp_vad_model_path: Path
    whispercpp_vad_threshold: float
    whispercpp_no_context: bool
    whispercpp_suppress_nst: bool
    whispercpp_no_fallback: bool
    whispercpp_no_speech_threshold: float
    wav_silence_gate_enabled: bool
    wav_silence_peak_dbfs: float
    wav_silence_rms_dbfs: float
    preload_on_start: bool
    idle_unload_seconds: int
    idle_check_seconds: int
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
        whispercpp_vad_model_path = resolve_path(
            os.getenv("WHISPERCPP_VAD_MODEL_PATH", "whisper.cpp/models/ggml-silero-v6.2.0.bin"),
            "whisper.cpp/models/ggml-silero-v6.2.0.bin",
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
            whispercpp_vad_enabled=env_flag("WHISPERCPP_VAD_ENABLED", True),
            whispercpp_vad_model_path=whispercpp_vad_model_path,
            whispercpp_vad_threshold=float(os.getenv("WHISPERCPP_VAD_THRESHOLD", "0.6")),
            whispercpp_no_context=env_flag("WHISPERCPP_NO_CONTEXT", True),
            whispercpp_suppress_nst=env_flag("WHISPERCPP_SUPPRESS_NST", True),
            whispercpp_no_fallback=env_flag("WHISPERCPP_NO_FALLBACK", True),
            whispercpp_no_speech_threshold=float(os.getenv("WHISPERCPP_NO_SPEECH_THRESHOLD", "0.75")),
            wav_silence_gate_enabled=env_flag("WAV_SILENCE_GATE_ENABLED", True),
            wav_silence_peak_dbfs=float(os.getenv("WAV_SILENCE_PEAK_DBFS", "-45")),
            wav_silence_rms_dbfs=float(os.getenv("WAV_SILENCE_RMS_DBFS", "-55")),
            preload_on_start=env_flag("ASR_PRELOAD_ON_START", False),
            idle_unload_seconds=int(os.getenv("ASR_IDLE_UNLOAD_SECONDS", "600")),
            idle_check_seconds=int(os.getenv("ASR_IDLE_CHECK_SECONDS", "15")),
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


@dataclass
class WavLevelInfo:
    duration_ms: int
    peak_dbfs: float
    rms_dbfs: float


def format_dbfs(value: float) -> str:
    if math.isinf(value):
        return "-inf"
    return f"{value:.1f}"


def inspect_wav_levels(audio_path: Path) -> WavLevelInfo | None:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(frame_count)
    except (wave.Error, EOFError):
        return None

    if frame_rate <= 0 or frame_count <= 0 or not frames:
        return WavLevelInfo(duration_ms=0, peak_dbfs=-math.inf, rms_dbfs=-math.inf)

    duration_ms = int((frame_count / frame_rate) * 1000)

    if sample_width == 1:
        max_possible = 127
        max_abs = 0
        sum_squares = 0.0
        sample_count = len(frames)
        for raw_sample in frames:
            centered = raw_sample - 128
            abs_sample = abs(centered)
            if abs_sample > max_abs:
                max_abs = abs_sample
            sum_squares += centered * centered
    elif sample_width == 2:
        samples = array("h")
        samples.frombytes(frames)
        if not samples:
            return WavLevelInfo(duration_ms=duration_ms, peak_dbfs=-math.inf, rms_dbfs=-math.inf)
        max_possible = 32767
        max_abs = 0
        sum_squares = 0.0
        sample_count = len(samples)
        for sample in samples:
            abs_sample = abs(sample)
            if abs_sample > max_abs:
                max_abs = abs_sample
            sum_squares += sample * sample
    elif sample_width == 4:
        samples = array("i")
        samples.frombytes(frames)
        if not samples:
            return WavLevelInfo(duration_ms=duration_ms, peak_dbfs=-math.inf, rms_dbfs=-math.inf)
        max_possible = 2147483647
        max_abs = 0
        sum_squares = 0.0
        sample_count = len(samples)
        for sample in samples:
            abs_sample = abs(sample)
            if abs_sample > max_abs:
                max_abs = abs_sample
            sum_squares += sample * sample
    else:
        return None

    if sample_count <= 0 or max_abs <= 0:
        return WavLevelInfo(duration_ms=duration_ms, peak_dbfs=-math.inf, rms_dbfs=-math.inf)

    peak_ratio = min(1.0, max_abs / max_possible)
    rms_ratio = min(1.0, math.sqrt(sum_squares / sample_count) / max_possible)
    peak_dbfs = 20.0 * math.log10(peak_ratio) if peak_ratio > 0 else -math.inf
    rms_dbfs = 20.0 * math.log10(rms_ratio) if rms_ratio > 0 else -math.inf

    return WavLevelInfo(duration_ms=duration_ms, peak_dbfs=peak_dbfs, rms_dbfs=rms_dbfs)


def should_skip_as_silence(audio_path: Path, settings: Settings) -> WavLevelInfo | None:
    if not settings.wav_silence_gate_enabled:
        return None

    levels = inspect_wav_levels(audio_path)
    if levels is None:
        return None

    if levels.peak_dbfs <= settings.wav_silence_peak_dbfs and levels.rms_dbfs <= settings.wav_silence_rms_dbfs:
        return levels
    return None


class FasterWhisperEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: WhisperModel | None = None
        self.device = "uninitialized"
        self.compute_type = "unknown"
        self._state_lock = threading.RLock()
        self._active_uses = 0
        self._last_used_at = 0.0

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

    def _begin_use(self) -> None:
        with self._state_lock:
            self._active_uses += 1

    def _end_use(self) -> None:
        with self._state_lock:
            self._active_uses = max(0, self._active_uses - 1)
            self._last_used_at = time.monotonic()

    def load(self) -> None:
        if not self.settings.token:
            raise RuntimeError("PTT_TOKEN is missing in .env")

        with self._state_lock:
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
                self._last_used_at = time.monotonic()
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
            self._last_used_at = time.monotonic()

    def is_loaded(self) -> bool:
        with self._state_lock:
            return self.model is not None

    def reported_device(self) -> str:
        if self.is_loaded():
            return self.device
        return self.requested_device()

    def unload(self) -> bool:
        with self._state_lock:
            if self.model is None:
                return False
            logging.info("Unloading faster-whisper model '%s' after idle timeout", self.settings.model_name)
            self.model = None
            gc.collect()
            return True

    def maybe_unload_idle(self) -> bool:
        if self.settings.idle_unload_seconds <= 0:
            return False

        with self._state_lock:
            if self.model is None or self._active_uses > 0:
                return False
            if self._last_used_at <= 0:
                return False
            if (time.monotonic() - self._last_used_at) < self.settings.idle_unload_seconds:
                return False

        return self.unload()

    def shutdown(self) -> None:
        self.unload()

    def transcribe(self, audio_path: Path, language: str | None) -> dict[str, object]:
        self._begin_use()
        try:
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
        finally:
            self._end_use()


class WhisperCppEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"http://{settings.whispercpp_server_host}:{settings.whispercpp_server_port}"
        self.process: subprocess.Popen[str] | None = None
        self.stdout_handle = None
        self.stderr_handle = None
        self.device = "vulkan"
        self._state_lock = threading.RLock()
        self._active_uses = 0
        self._last_used_at = 0.0

    def _is_ready(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/", timeout=2.0)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _begin_use(self) -> None:
        with self._state_lock:
            self._active_uses += 1

    def _end_use(self) -> None:
        with self._state_lock:
            self._active_uses = max(0, self._active_uses - 1)
            self._last_used_at = time.monotonic()

    def _stderr_tail(self) -> str:
        stderr_path = ROOT / "whispercpp.stderr.log"
        if not stderr_path.exists():
            return ""
        return "\n".join(stderr_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:])

    def _close_logs(self) -> None:
        if self.stdout_handle:
            self.stdout_handle.close()
            self.stdout_handle = None
        if self.stderr_handle:
            self.stderr_handle.close()
            self.stderr_handle = None

    def _start_server(self) -> None:
        if self.process and self.process.poll() is None:
            return

        if not self.settings.whispercpp_binary_path.exists():
            raise RuntimeError(f"whisper.cpp server not found at {self.settings.whispercpp_binary_path}")
        if not self.settings.whispercpp_model_path.exists():
            raise RuntimeError(f"whisper.cpp model not found at {self.settings.whispercpp_model_path}")
        if self.settings.whispercpp_vad_enabled and not self.settings.whispercpp_vad_model_path.exists():
            raise RuntimeError(f"whisper.cpp VAD model not found at {self.settings.whispercpp_vad_model_path}")

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
            "-nth",
            str(self.settings.whispercpp_no_speech_threshold),
        ]
        if self.settings.whispercpp_flash_attn:
            args.append("-fa")
        if self.settings.whispercpp_no_context:
            args.extend(["-mc", "0"])
        if self.settings.whispercpp_suppress_nst:
            args.append("-sns")
        if self.settings.whispercpp_no_fallback:
            args.append("-nf")
        if self.settings.whispercpp_vad_enabled:
            args.extend([
                "--vad",
                "-vm",
                str(self.settings.whispercpp_vad_model_path),
                "-vt",
                str(self.settings.whispercpp_vad_threshold),
            ])

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

        with self._state_lock:
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            if self._is_ready():
                self._last_used_at = time.monotonic()
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
                with self._state_lock:
                    self._last_used_at = time.monotonic()
                return
            if self.process and self.process.poll() is not None:
                raise RuntimeError(
                    "whisper.cpp server exited during startup:\n" + self._stderr_tail()
                )
            time.sleep(1)

        raise RuntimeError("whisper.cpp server did not become ready in time")

    def is_loaded(self) -> bool:
        with self._state_lock:
            process_running = self.process is not None and self.process.poll() is None
        if process_running:
            return self._is_ready()
        return False

    def reported_device(self) -> str:
        return self.device

    def unload(self) -> bool:
        with self._state_lock:
            if self.process is None or self.process.poll() is not None:
                self._close_logs()
                self.process = None
                return False
            logging.info("Stopping whisper.cpp backend after idle timeout")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
            self._close_logs()
            return True

    def maybe_unload_idle(self) -> bool:
        if self.settings.idle_unload_seconds <= 0:
            return False

        with self._state_lock:
            if self._active_uses > 0:
                return False
            if self.process is None or self.process.poll() is not None:
                return False
            if self._last_used_at <= 0:
                return False
            if (time.monotonic() - self._last_used_at) < self.settings.idle_unload_seconds:
                return False

        return self.unload()

    def shutdown(self) -> None:
        self.unload()

    def transcribe(self, audio_path: Path, language: str | None) -> dict[str, object]:
        self._begin_use()
        try:
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
        finally:
            self._end_use()


class IdleUnloadMonitor:
    def __init__(self, engine: FasterWhisperEngine | WhisperCppEngine, interval_seconds: int) -> None:
        self.engine = engine
        self.interval_seconds = max(1, interval_seconds)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="asr-idle-monitor", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.engine.maybe_unload_idle()
            except Exception:
                logging.exception("Idle unload check failed")


SETTINGS = Settings.from_env()
configure_logging(SETTINGS.log_level)
ENGINE = WhisperCppEngine(SETTINGS) if SETTINGS.backend == "whispercpp" else FasterWhisperEngine(SETTINGS)
IDLE_MONITOR = IdleUnloadMonitor(ENGINE, SETTINGS.idle_check_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    IDLE_MONITOR.start()
    if SETTINGS.preload_on_start:
        ENGINE.load()
    logging.info(
        "ASR service ready at http://%s:%s using backend=%s preload_on_start=%s idle_unload_seconds=%s (reachable from VM at http://%s:%s)",
        SETTINGS.bind_host,
        SETTINGS.port,
        SETTINGS.backend,
        SETTINGS.preload_on_start,
        SETTINGS.idle_unload_seconds,
        SETTINGS.host_accessible_ip,
        SETTINGS.port,
    )
    try:
        yield
    finally:
        IDLE_MONITOR.stop()
        ENGINE.shutdown()


app = FastAPI(title="Local Whisper PTT Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "backend": SETTINGS.backend,
        "device": ENGINE.reported_device(),
        "loaded": ENGINE.is_loaded(),
        "model": SETTINGS.model_name,
        "preload_on_start": SETTINGS.preload_on_start,
        "idle_unload_seconds": SETTINGS.idle_unload_seconds,
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
    started_at = time.perf_counter()

    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=TMP_DIR) as handle:
            shutil.copyfileobj(audio.file, handle)
            temp_path = Path(handle.name)
        silent_levels = should_skip_as_silence(temp_path, SETTINGS)
        if silent_levels is not None:
            logging.info(
                "Skipping ASR for silent WAV (%sms, peak=%s dBFS, rms=%s dBFS)",
                silent_levels.duration_ms,
                format_dbfs(silent_levels.peak_dbfs),
                format_dbfs(silent_levels.rms_dbfs),
            )
            return {
                "text": "",
                "language": selected_language or "",
                "duration_ms": int((time.perf_counter() - started_at) * 1000),
                "device": ENGINE.reported_device(),
                "model": SETTINGS.model_name,
            }
        try:
            return ENGINE.transcribe(temp_path, selected_language)
        except Exception as exc:
            logging.exception("Transcription request failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
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
