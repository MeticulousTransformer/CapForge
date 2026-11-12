"""CapForge — local backend.

Run:  python backend/app.py   (or: cd backend && python app.py)
Serves http://127.0.0.1:8765 for the After Effects panel.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import secrets
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERSION = "0.3.3"
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "exports")


def load_env() -> None:
    """Load backend/.env (or backend/config.env). os.environ wins."""
    for name in (".env", "config.env"):
        path = os.path.join(BACKEND_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if v and k not in os.environ:
                    os.environ[k] = v


load_env()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from requests.exceptions import RequestException, Timeout

from services.audio_extract import extract_audio, find_ffmpeg, wav_duration
from services.grouping import GroupingOptions, group_words
from services.local_scan import scan_local
from services.models import Word, build_document
from services.normalize import WordTimingError
from services.studio_settings import local_token, save_provider_key
from services.transcript_validation import validate_document
from services.provider_registry import available_ids, get_provider, list_infos
from services import updates
from providers.base import ProviderError

PANEL_ORIGINS = ["null", "file://"]

app = FastAPI(title="CapForge Backend", version=VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=PANEL_ORIGINS, allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-KCF-Token"]
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    # Pydantic's default validation output includes input values, including keys.
    issues = [{"loc": item["loc"], "msg": item["msg"]} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": "Check the request values.", "issues": issues})


@app.middleware("http")
async def protect_local_service(request: Request, call_next):
    # CEP can send either file:// or null for its installed panel. Neither
    # identifies CapForge: the installation token still protects private APIs.
    origin = request.headers.get("origin")
    if origin is not None and origin not in PANEL_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "This service only accepts the installed CapForge panel."})
    size = request.headers.get("content-length", "0")
    if not size.isdigit() or int(size) > 12 * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": "Request must be smaller than 12 MB."})
    if request.method != "OPTIONS" and request.url.path != "/health":
        if not secrets.compare_digest(request.headers.get("x-kcf-token", ""), local_token(BACKEND_DIR)):
            return JSONResponse(status_code=401, content={"detail": "Panel authorization missing. Start the installed service and check the connection in Setup."})
    if _service_stopping and request.method != "OPTIONS" and request.url.path not in {"/health", "/service/info", "/service/stop"}:
        return JSONResponse(status_code=503, content={"detail": "CapForge is stopping for an update. Start the service again after setup finishes."})
    return await call_next(request)


class GroupingModel(BaseModel):
    minWords: int = Field(default=2, ge=1, le=6)
    maxWords: int = Field(default=4, ge=1, le=6)
    maxChars: int = Field(default=42, ge=4, le=200)
    pauseBreakSeconds: float = Field(default=0.55, ge=0.1, le=5)
    minCaptionDuration: float = Field(default=0.5, ge=0, le=10)
    maxCaptionDuration: float = Field(default=3.5, ge=0.1, le=30)
    removeCommasAndPeriods: bool = False

    @model_validator(mode="after")
    def ordered_limits(self):
        if self.minWords > self.maxWords or self.minCaptionDuration > self.maxCaptionDuration:
            raise ValueError("Minimum grouping values cannot exceed maximums.")
        return self


class ExtractRequest(BaseModel):
    mediaPath: str


class TranscribeRequest(BaseModel):
    mediaPath: str
    language: str = "ka-GE"
    provider: str = "elevenlabs"
    providerOptions: dict = Field(default_factory=dict)
    grouping: GroupingModel = Field(default_factory=GroupingModel)


class RegroupRequest(BaseModel):
    document: dict
    grouping: GroupingModel = Field(default_factory=GroupingModel)


class ProviderKeyRequest(BaseModel):
    name: str
    value: str = Field(min_length=1, max_length=2048, repr=False)
    region: str | None = None


_transcription_lock = Lock()
_shutdown_server = None
_service_stopping = False


def _require_running():
    # Recheck after acquiring the work lock: shutdown can begin after the
    # middleware admitted a request but before its worker thread starts.
    if _service_stopping:
        raise HTTPException(status_code=503, detail="CapForge is stopping for an update. Start the service again after setup finishes.")


def _run_exports() -> str:
    return os.path.join(EXPORTS_DIR, "runs", str(uuid.uuid4()))


def _save_json(path: str, data) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": VERSION,
        "availableProviders": available_ids(),
        "ffmpeg": bool(find_ffmpeg()),
    }


@app.get("/providers")
def providers():
    return {"providers": list_infos(), "local": scan_local()}


@app.get("/service/info")
def service_info():
    return {"runtimeRoot": os.path.realpath(os.path.dirname(BACKEND_DIR)), "version": VERSION}


@app.post("/service/stop")
def stop_service(background: BackgroundTasks):
    global _service_stopping
    if not _transcription_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Wait for the current transcription to finish before updating CapForge.")
    try:
        if _shutdown_server is None:
            raise HTTPException(status_code=409, detail="Close the existing CapForge service window before updating. This service cannot stop itself.")
        if not _service_stopping:
            _service_stopping = True
            background.add_task(_shutdown_server)
        return {"stopping": True, "message": "CapForge is stopping so the installer can safely update it."}
    finally:
        _transcription_lock.release()


@app.get("/updates/check")
def check_updates():
    try:
        return updates.check(os.path.dirname(BACKEND_DIR), VERSION)
    except updates.UpdateError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))


@app.post("/updates/install")
def install_update():
    if not _transcription_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Wait for the current transcription to finish before updating CapForge.")
    try:
        _require_running()
        return updates.install(os.path.dirname(BACKEND_DIR), VERSION)
    except updates.UpdateError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    finally:
        _transcription_lock.release()


@app.post("/extract_audio")
def extract(req: ExtractRequest):
    if not _transcription_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Audio preparation or transcription is already running. Wait for it to finish.")
    try:
        _require_running()
        wav = extract_audio(req.mediaPath, _run_exports())
        return {"audio": wav, "duration": wav_duration(wav)}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        _transcription_lock.release()


@app.post("/transcribe")
def transcribe(req: TranscribeRequest):
    if not _transcription_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A transcription is already running. Wait for it to finish.")
    try:
        _require_running()
        return _transcribe(req)
    finally:
        _transcription_lock.release()


def _transcribe(req: TranscribeRequest):
    if not os.path.isfile(req.mediaPath):
        raise HTTPException(status_code=400, detail=f"Media file not found: {req.mediaPath}")

    provider = get_provider(req.provider)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    ok, detail = provider.availability()
    if not ok:
        raise HTTPException(status_code=400, detail=f"Provider unavailable: {detail}.")

    run_dir = _run_exports()
    try:
        wav = extract_audio(req.mediaPath, run_dir)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = provider.transcribe(wav, req.language, req.providerOptions)
    except WordTimingError as e:
        detail = str(e)
        if e.raw_response is not None:
            _save_json(os.path.join(run_dir, f"raw_{provider.id}.json"), e.raw_response)
            detail += " The raw response was saved for troubleshooting."
        raise HTTPException(status_code=400, detail=detail) from None
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Timeout:
        raise HTTPException(status_code=400, detail=f"{provider.label} timed out. Check the provider account before trying again; the upload may have reached it.") from None
    except RequestException:
        raise HTTPException(status_code=400, detail=f"Could not reach {provider.label}. Check your internet connection and try again.") from None
    except Exception:
        raise HTTPException(status_code=500, detail=f"{provider.id} could not complete transcription. Check its configuration and try again.")

    raw_path = _save_json(
        os.path.join(run_dir, f"raw_{provider.id}.json"), result.raw
    )

    opts = GroupingOptions.from_dict(req.grouping.model_dump())
    captions = group_words(result.words, opts)

    duration = result.duration or wav_duration(wav)
    document = build_document(
        source_media_path=req.mediaPath,
        language=req.language,
        provider=provider.id,
        duration=duration,
        words=result.words,
        captions=captions,
    )
    try:
        document = validate_document(document)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=(f"{provider.label} returned a transcript with unusable word timing or caption data. "
                    "Try another model or provider. The raw response was saved for troubleshooting. "
                    f"Details: {error}"),
        ) from None
    normalized_path = _save_json(os.path.join(run_dir, "normalized.json"), document)

    warnings = list(result.warnings)
    if result.timing_quality != "word":
        warnings.append(f"Timing quality: {result.timing_quality}.")
    if not document["words"]:
        warnings.append("Transcript has text but no word timings. "
                        "Animation requires word timings.")

    return {
        "document": document,
        "debugPaths": {
            "audio": wav,
            "rawProviderJson": raw_path,
            "normalizedJson": normalized_path,
        },
        "timingQuality": result.timing_quality,
        "warnings": warnings,
    }


@app.post("/regroup")
def regroup(req: RegroupRequest):
    try:
        document = validate_document(req.document)
        words = [Word(**{key: value for key, value in word.items() if key in Word.__dataclass_fields__}) for word in document["words"]]
        captions = group_words(words, GroupingOptions.from_dict(req.grouping.model_dump()))
        document["words"] = [word.to_dict() for word in words]
        document["captions"] = [caption.to_dict() for caption in captions]
        return {"document": document}
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/settings/provider-key")
def provider_key(req: ProviderKeyRequest):
    if not _transcription_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Save provider keys after the current transcription finishes.")
    try:
        _require_running()
        save_provider_key(BACKEND_DIR, req.name, req.value, req.region)
        return {"ok": True}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    finally:
        _transcription_lock.release()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("KCF_PORT", "8765"))
    local_token(BACKEND_DIR)
    print(f"CapForge backend v{VERSION} -> http://127.0.0.1:{port}")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port))
    def request_shutdown():
        server.should_exit = True
    _shutdown_server = request_shutdown
    server.run()
