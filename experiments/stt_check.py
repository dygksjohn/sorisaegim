r"""STT 검증 스크립트 (1주차).

오디오 파일을 Whisper로 인식해 텍스트를 출력한다.
여러 모델(small/medium)을 지정하면 모델별 인식 결과와 처리 시간을 비교한다.

사용 예 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\stt_check.py 녹음.wav
    .venv\Scripts\python.exe experiments\stt_check.py 녹음.wav --models small,medium
    .venv\Scripts\python.exe experiments\stt_check.py 녹음.wav --temperature 0.6
"""

import argparse
import sys
import time
from pathlib import Path

import whisper

# 모델은 프로세스 내에서 재사용 (여러 파일 처리 시 재로드 방지)
_model_cache: dict[str, "whisper.Whisper"] = {}


def load_model(name: str) -> "whisper.Whisper":
    if name not in _model_cache:
        print(f"[모델 로드] {name} ... ", end="", flush=True)
        t0 = time.perf_counter()
        _model_cache[name] = whisper.load_model(name)
        print(f"완료 ({time.perf_counter() - t0:.1f}s)")
    return _model_cache[name]


def transcribe(
    audio_path: str,
    model_name: str = "small",
    temperature: float = 0.0,
    initial_prompt: str | None = None,
) -> dict:
    """오디오 파일 하나를 인식해 {text, elapsed_sec, model} 반환."""
    model = load_model(model_name)
    t0 = time.perf_counter()
    result = model.transcribe(
        audio_path,
        language="ko",
        temperature=temperature,
        initial_prompt=initial_prompt,
        # 이전 문맥 참조를 끄면 '문맥으로 교정'하는 경향이 줄어든다
        condition_on_previous_text=False,
        fp16=False,  # CPU 환경
    )
    return {
        "model": model_name,
        "text": result["text"].strip(),
        "elapsed_sec": time.perf_counter() - t0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper 한국어 인식 검증")
    parser.add_argument("audio", nargs="+", help="오디오 파일 경로 (wav/mp3/webm 등)")
    parser.add_argument(
        "--models",
        default="small",
        help="쉼표 구분 모델 목록 (예: small,medium). 기본: small",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--initial-prompt",
        default=None,
        help="디코딩 힌트 프롬프트 (기본: 없음 — 교정 실험에서는 없음 유지)",
    )
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    for audio in args.audio:
        if not Path(audio).exists():
            print(f"[오류] 파일 없음: {audio}", file=sys.stderr)
            continue
        print(f"\n=== {audio} ===")
        for model_name in models:
            r = transcribe(
                audio,
                model_name=model_name,
                temperature=args.temperature,
                initial_prompt=args.initial_prompt,
            )
            print(f"[{r['model']:>7}] ({r['elapsed_sec']:5.1f}s) {r['text']}")


if __name__ == "__main__":
    main()
