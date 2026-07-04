r"""소리새김 백엔드 (3주차) — docs\api_spec.md 구현.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\uvicorn.exe app.main:app --port 8000

첫 평가 요청 시 Whisper 모델을 로드하므로 수 초~수십 초 걸린다 (이후 요청은 빠름).
"""

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import stt
import tts
from engine import compare
from .db import TTS_CACHE_DIR, UPLOADS_DIR, get_conn, init_db

KST = timezone(timedelta(hours=9))
MIN_AUDIO_SEC = 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="소리새김 API", version="0.1", lifespan=lifespan)

# 4주차 프론트는 같은 서버에서 서빙 예정이지만, 개발 중 file:// 접근을 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(status: int, code: str, message: str = "") -> JSONResponse:
    body = {"error": code}
    if message:
        body["message"] = message
    return JSONResponse(status_code=status, content=body)


@app.get("/sentences")
def list_sentences(type: str | None = None, difficulty: int | None = None):
    query = "SELECT id, text, pron, type, difficulty FROM sentences WHERE 1=1"
    params: list = []
    if type:
        query += " AND type = ?"
        params.append(type)
    if difficulty:
        query += " AND difficulty = ?"
        params.append(difficulty)
    conn = get_conn()
    try:
        rows = conn.execute(query + " ORDER BY id", params).fetchall()
    finally:
        conn.close()
    return {"sentences": [dict(r) for r in rows]}


def _get_sentence(sentence_id: int):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT id, text, pron FROM sentences WHERE id = ?", (sentence_id,)
        ).fetchone()
    finally:
        conn.close()


@app.get("/sentences/{sentence_id}/audio")
async def sentence_audio(sentence_id: int):
    row = _get_sentence(sentence_id)
    if row is None:
        return error_response(404, "sentence_not_found")
    cache_path = TTS_CACHE_DIR / f"sentence_{sentence_id}.mp3"
    path = await tts.get_or_create_audio(row["text"], cache_path)
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/attempts")
async def create_attempt(sentence_id: int = Form(...), audio: UploadFile = File(...)):
    sentence = _get_sentence(sentence_id)
    if sentence is None:
        return error_response(404, "sentence_not_found")

    # 녹음 원본 보관 (7주차 ML 데이터)
    suffix = Path(audio.filename or "rec.webm").suffix or ".webm"
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S_%f")
    audio_path = UPLOADS_DIR / f"att_{stamp}_s{sentence_id}{suffix}"
    audio_path.write_bytes(await audio.read())

    # 디코딩(ffmpeg) + 길이 검증
    from whisper.audio import SAMPLE_RATE, load_audio
    try:
        samples = load_audio(str(audio_path))
    except Exception:
        return error_response(400, "audio_decode_failed", "오디오 형식을 해석할 수 없습니다")
    if len(samples) / SAMPLE_RATE < MIN_AUDIO_SEC:
        return error_response(400, "audio_too_short", "1초 이상 녹음해 주세요")

    stt_result = stt.transcribe(samples)
    if not stt_result["text"]:
        return error_response(422, "stt_empty", "음성을 인식하지 못했습니다. 다시 녹음해 주세요")

    analysis = compare(sentence["text"], stt_result["text"])
    created_at = datetime.now(KST).isoformat(timespec="seconds")

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO attempts (sentence_id, audio_path, stt_engine, stt_text,"
            " score, errors_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sentence_id,
                str(audio_path),
                stt_result["engine"],
                stt_result["text"],
                analysis["score"],
                json.dumps(analysis["errors"], ensure_ascii=False),
                created_at,
            ),
        )
        conn.commit()
        attempt_id = cur.lastrowid
    finally:
        conn.close()

    return {
        "attempt_id": attempt_id,
        "sentence_id": sentence_id,
        "stt": stt_result,
        "analysis": analysis,
        "created_at": created_at,
    }


# 프론트 (4주차) — API 라우트가 먼저 매칭되고, 나머지 경로는 static/ 에서 서빙
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent.parent / "static", html=True),
    name="static",
)
