"""STT 모듈 — Whisper small 래퍼 (1주차 결정: small, t=0.0 고정).

모델은 프로세스당 1회만 로드한다. 입력은 파일 경로 또는
whisper.audio.load_audio()가 돌려준 float32 배열 둘 다 허용
(업로드 검증에서 이미 디코딩한 배열을 재사용해 ffmpeg 중복 호출을 피한다).
"""

import time

import numpy as np
import whisper

MODEL_NAME = "small"
_model = None


def _get_model() -> "whisper.Whisper":
    global _model
    if _model is None:
        _model = whisper.load_model(MODEL_NAME)
    return _model


def transcribe(audio: "str | np.ndarray") -> dict:
    """오디오 → {"engine", "text", "elapsed_ms"}."""
    model = _get_model()
    t0 = time.perf_counter()
    result = model.transcribe(
        audio,
        language="ko",
        temperature=0.0,
        initial_prompt=None,
        condition_on_previous_text=False,
        fp16=False,
    )
    return {
        "engine": f"whisper-{MODEL_NAME}",
        "text": result["text"].strip(),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000),
    }
