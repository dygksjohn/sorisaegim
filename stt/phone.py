"""발음형 음소 인식기 — 미세조정 wav2vec2 래퍼 (후속 +5주차).

Whisper(단어 인식기, stt/__init__.py) 대신 발음형 자모 시퀀스를 직접 출력한다.
출력은 engine.phonetic.compare_phonetic에 그대로 넣어 g2p 재적용 없이 비교한다.

모델 배치(로컬):
  data/models/w2v2-jamo/  (config.json, model.safetensors, preprocessor/tokenizer, vocab.json)
  Colab 학습 산출물(OUTPUT_DIR)을 이 폴더로 복사. 경로는 PHONE_MODEL_DIR 로 덮어쓸 수 있다.

CPU 추론이라 문장당 수 초 — 데모·평가용. 모델이 없으면 available()=False.
"""

import os
import time
from pathlib import Path

import numpy as np

MODEL_DIR = Path(os.environ.get(
    "PHONE_MODEL_DIR",
    Path(__file__).parent.parent / "data" / "models" / "w2v2-jamo"))
SAMPLE_RATE = 16000
_SPN = set("spn")

_model = None
_processor = None


def available() -> bool:
    return (MODEL_DIR / "config.json").exists()


def _load():
    global _model, _processor
    if _model is None:
        import torch  # noqa: F401  (지연 임포트 — 무거운 의존성)
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        _processor = Wav2Vec2Processor.from_pretrained(str(MODEL_DIR))
        _model = Wav2Vec2ForCTC.from_pretrained(str(MODEL_DIR)).eval()
    return _model, _processor


def _clean(text: str) -> str:
    """디코딩 결과 → 발음형 자모 (spn·공백·특수토큰 제거)."""
    return "".join(c for c in text if c not in _SPN and not c.isspace())


def transcribe(audio: "str | np.ndarray") -> dict:
    """오디오(경로 또는 16k float32 배열) → {engine, phones, elapsed_ms}."""
    import torch
    model, processor = _load()
    if isinstance(audio, str):
        from whisper.audio import load_audio
        audio = load_audio(audio)  # 16k mono float32
    t0 = time.perf_counter()
    inputs = processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values).logits
    pred_ids = logits.argmax(-1)
    phones = _clean(processor.batch_decode(pred_ids)[0])
    return {
        "engine": "wav2vec2-jamo",
        "phones": phones,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000),
    }
