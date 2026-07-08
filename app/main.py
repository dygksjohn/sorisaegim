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
import stt.phone as stt_phone
import tts
from engine import compare
from engine.phonetic import compare_phonetic
from .db import TTS_CACHE_DIR, UPLOADS_DIR, get_conn, init_db

KST = timezone(timedelta(hours=9))
MIN_AUDIO_SEC = 1.0
# 무음 판정 임계값 (float32 진폭). 실측: 게임바 충돌 시 무음 녹음이 -84dB(≈0.00006),
# 정상 발화는 통상 0.05 이상 — 0.005면 확실히 가른다.
SILENCE_PEAK_THRESHOLD = 0.005


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
async def create_attempt(
    sentence_id: int = Form(...),
    audio: UploadFile = File(...),
    source: str = Form("user"),  # user(브라우저 실사용) | synth(합성 증강 스크립트)
    engine: str = Form("whisper"),  # whisper(기본) | phone(미세조정 wav2vec2 발음형)
):
    if source not in ("user", "synth"):
        return error_response(400, "invalid_source")
    if engine not in ("whisper", "phone"):
        return error_response(400, "invalid_engine")
    if engine == "phone" and not stt_phone.available():
        return error_response(
            503, "phone_model_missing",
            "발음형 인식기 모델이 없습니다. data/models/w2v2-jamo/ 에 배치하세요 "
            "(docs/colab_실행가이드.md).")
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
        audio_path.unlink(missing_ok=True)  # 거부된 업로드는 보관하지 않음 (고아 파일 방지)
        return error_response(400, "audio_decode_failed", "오디오 형식을 해석할 수 없습니다")
    if len(samples) / SAMPLE_RATE < MIN_AUDIO_SEC:
        audio_path.unlink(missing_ok=True)
        return error_response(400, "audio_too_short", "1초 이상 녹음해 주세요")
    if float(abs(samples).max()) < SILENCE_PEAK_THRESHOLD:
        audio_path.unlink(missing_ok=True)
        return error_response(
            400, "audio_silent",
            "소리가 녹음되지 않았습니다. 마이크 연결과 입력 장치 설정을 확인해 주세요",
        )

    if engine == "phone":
        # 발음형 인식기: 자모를 직접 출력 → g2p 재적용 없이 발음형 비교
        phone_result = stt_phone.transcribe(samples)
        if not phone_result["phones"]:
            return error_response(422, "stt_empty", "음성을 인식하지 못했습니다. 다시 녹음해 주세요")
        stt_result = {"engine": phone_result["engine"], "text": phone_result["phones"],
                      "elapsed_ms": phone_result["elapsed_ms"]}
        analysis = compare_phonetic(sentence["text"], phone_result["phones"])
    else:
        stt_result = stt.transcribe(samples)
        if not stt_result["text"]:
            return error_response(422, "stt_empty", "음성을 인식하지 못했습니다. 다시 녹음해 주세요")
        analysis = compare(sentence["text"], stt_result["text"])
    created_at = datetime.now(KST).isoformat(timespec="seconds")

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO attempts (sentence_id, audio_path, stt_engine, stt_text,"
            " score, errors_json, created_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sentence_id,
                # 프로젝트 루트 기준 상대 경로 — 폴더 이동/이름 변경에도 참조가 깨지지 않게
                f"data/uploads/{audio_path.name}",
                stt_result["engine"],
                stt_result["text"],
                analysis["score"],
                json.dumps(analysis["errors"], ensure_ascii=False),
                created_at,
                source,
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


# ---------- 통계 (6주차) ----------

def _source_clause(source: str) -> tuple[str, list]:
    """통계 필터. 기본 user — 합성 증강(synth)이 학습 기록을 오염시키지 않게 한다."""
    if source == "all":
        return "1=1", []
    return "a.source = ?", [source if source in ("user", "synth") else "user"]


@app.get("/stats/summary")
def stats_summary(source: str = "user"):
    """전체 요약 + 유형별 평균 + 점수 추이 (기록 화면용)."""
    clause, params = _source_clause(source)
    conn = get_conn()
    try:
        overall = conn.execute(
            f"SELECT COUNT(*) AS n, ROUND(AVG(score), 1) AS avg_score"
            f" FROM attempts a WHERE {clause}", params
        ).fetchone()
        by_type = conn.execute(
            f"SELECT s.type, COUNT(*) AS n, ROUND(AVG(a.score), 1) AS avg_score"
            f" FROM attempts a JOIN sentences s ON s.id = a.sentence_id"
            f" WHERE {clause} GROUP BY s.type ORDER BY avg_score", params
        ).fetchall()
        trend = conn.execute(
            f"SELECT id, score, created_at FROM attempts a WHERE {clause} ORDER BY id",
            params,
        ).fetchall()
    finally:
        conn.close()
    return {
        "total": overall["n"],
        "avg_score": overall["avg_score"],
        "by_type": [dict(r) for r in by_type],
        "trend": [dict(r) for r in trend],
    }


@app.get("/stats/weak-jamo")
def stats_weak_jamo(top: int = 5, source: str = "user"):
    """자주 틀리는 자모 TOP N — attempts.errors_json 집계.

    7주차 ML(취약 발음 예측)의 규칙 기반 대조군이 되는 집계다.
    """
    from collections import Counter

    clause, params = _source_clause(source)
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT errors_json FROM attempts a WHERE {clause}", params
        ).fetchall()
    finally:
        conn.close()

    counter: Counter = Counter()
    for r in rows:
        for e in json.loads(r["errors_json"]):
            counter[(e["type"], e["component"], e["expected"], e["actual"])] += 1

    items = [
        {"error_type": t, "component": c, "expected": ex, "actual": ac, "count": n}
        for (t, c, ex, ac), n in counter.most_common(top)
    ]
    return {"weak_jamo": items, "total_errors": sum(counter.values())}


@app.get("/stats/attempts")
def stats_attempts(limit: int = 20, source: str = "user"):
    """최근 시도 목록 (기록 화면 테이블용)."""
    clause, params = _source_clause(source)
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT a.id, a.score, a.stt_text, a.created_at, s.text, s.type"
            f" FROM attempts a JOIN sentences s ON s.id = a.sentence_id"
            f" WHERE {clause} ORDER BY a.id DESC LIMIT ?",
            params + [max(1, min(limit, 200))],
        ).fetchall()
    finally:
        conn.close()
    return {"attempts": [dict(r) for r in rows]}


# ---------- 추천 (7주차 — ML 모델 사용) ----------

@app.get("/recommend")
def recommend_sentences(top: int = 3):
    """취약 발음 기반 연습 문장 추천. ml.train 으로 학습된 모델을 사용한다."""
    from ml import recommend as rec
    if not rec.model_available():
        return error_response(
            503, "model_not_trained",
            "모델이 없습니다. 먼저 `python -m ml.train`을 실행하세요")
    conn = get_conn()
    try:
        items = rec.recommend(conn, top=max(1, min(top, 10)))
    finally:
        conn.close()
    return {"recommendations": items}


# 프론트 (4주차) — API 라우트가 먼저 매칭되고, 나머지 경로는 static/ 에서 서빙
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).parent.parent / "static", html=True),
    name="static",
)
