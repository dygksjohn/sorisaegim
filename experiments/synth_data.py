r"""6주차 — TTS 오발음 주입 합성 데이터 생성 (지인 테스트의 데이터 축적 역할 대체).

원리: TTS는 입력 텍스트의 표준 발음대로 읽는다. 따라서 자모를 의도적으로 치환한
"틀린 텍스트"를 합성하면 "틀린 발음" 음성이 나오고, 어떤 자모를 어떻게 틀렸는지
라벨이 공짜로 정확하다 (7주차 ML 학습용).

- 정상 1 + 오류 변형 2 per (문장 × 보이스). 치환은 학습자 혼동 쌍 위주.
- attempts에 source='synth'로 저장되어 실사용 통계와 분리된다.
- 라벨은 results\synth_labels.csv 에 기록 (7주차 데이터셋 구성 재료).

전제: 서버 실행 중.

실행 (CMD, 프로젝트 루트에서 — 보이스별로 나눠 실행):
    .venv\Scripts\python.exe experiments\synth_data.py --voice ko-KR-SunHiNeural
    .venv\Scripts\python.exe experiments\synth_data.py --voice ko-KR-InJoonNeural
"""

import argparse
import asyncio
import csv
import os
import random
import sys
import tempfile
import time
from pathlib import Path

import edge_tts
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.hangul import (  # noqa: E402
    CHOSEONG, JUNGSEONG, JONGSEONG, HANGUL_BASE,
    decompose_syllable, is_hangul_syllable,
)

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
RESULTS_DIR = Path(__file__).parent / "results"
LABELS_CSV = RESULTS_DIR / "synth_labels.csv"
VARIANTS_PER_SENTENCE = 2
SEED = 20260704  # 재현 가능성

# 학습자 혼동 쌍 (외국인 화자가 실제로 자주 내는 오류 위주)
CHO_CONFUSION = {
    "ㄹ": ["ㄴ"], "ㄴ": ["ㄹ"],
    "ㅂ": ["ㅍ", "ㅁ"], "ㅍ": ["ㅂ"],
    "ㄷ": ["ㅌ", "ㄴ"], "ㅌ": ["ㄷ"],
    "ㄱ": ["ㅋ"], "ㅋ": ["ㄱ"],
    "ㅈ": ["ㅊ"], "ㅊ": ["ㅈ"],
    "ㅅ": ["ㅆ"], "ㅆ": ["ㅅ"],
    "ㄲ": ["ㄱ"], "ㄸ": ["ㄷ"], "ㅃ": ["ㅂ"], "ㅉ": ["ㅈ"],
}
JUNG_CONFUSION = {
    "ㅓ": ["ㅗ"], "ㅗ": ["ㅓ", "ㅜ"], "ㅜ": ["ㅗ", "ㅡ"], "ㅡ": ["ㅜ"],
    "ㅐ": ["ㅔ"], "ㅔ": ["ㅐ"], "ㅕ": ["ㅛ"], "ㅛ": ["ㅕ"],
}
JONG_SUBSTITUTES = ["", "ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅇ"]


def compose(cho: str, jung: str, jong: str) -> str:
    return chr(
        HANGUL_BASE
        + (CHOSEONG.index(cho) * 21 + JUNGSEONG.index(jung)) * 28
        + JONGSEONG.index(jong)
    )


def perturb(text: str, rng: random.Random) -> tuple[str, dict] | None:
    """문장에서 음절 하나의 자모 하나를 치환. (변형 문장, 라벨) 반환."""
    idxs = [i for i, ch in enumerate(text) if is_hangul_syllable(ch)]
    if not idxs:
        return None
    for _ in range(20):  # 유효한 치환이 나올 때까지 재시도
        i = rng.choice(idxs)
        cho, jung, jong = decompose_syllable(text[i])
        component = rng.choices(["cho", "jung", "jong"], weights=[35, 35, 30])[0]
        if component == "cho":
            new = rng.choice(CHO_CONFUSION.get(cho, [c for c in "ㄴㄷㅂㅅㅈ" if c != cho]))
            new_syl, label = compose(new, jung, jong), ("choseong", cho, new)
        elif component == "jung":
            new = rng.choice(JUNG_CONFUSION.get(jung, [v for v in "ㅏㅓㅗㅜㅡㅣ" if v != jung]))
            new_syl, label = compose(cho, new, jong), ("jungseong", jung, new)
        else:
            if not jong:
                continue  # 없는 받침 치환은 의미 없음 — 다른 시도
            new = rng.choice([j for j in JONG_SUBSTITUTES if j != jong])
            new_syl, label = compose(cho, jung, new), ("jongseong", jong, new)
        if new_syl != text[i]:
            variant = text[:i] + new_syl + text[i + 1:]
            return variant, {
                "position": i, "orig_syllable": text[i], "new_syllable": new_syl,
                "component": label[0], "from": label[1], "to": label[2] or "(삭제)",
            }
    return None


async def synthesize(text: str, voice: str, out_path: str) -> None:
    await edge_tts.Communicate(text, voice).save(out_path)


def post_attempt(sentence_id: int, mp3_path: str) -> dict:
    with open(mp3_path, "rb") as f:
        r = requests.post(f"{BASE}/attempts",
                          data={"sentence_id": sentence_id, "source": "synth"},
                          files={"audio": ("synth.mp3", f, "audio/mpeg")}, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS 오발음 주입 합성 데이터 생성")
    parser.add_argument("--voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--variants", type=int, default=VARIANTS_PER_SENTENCE)
    args = parser.parse_args()

    sentences = requests.get(f"{BASE}/sentences", timeout=30).json()["sentences"]
    RESULTS_DIR.mkdir(exist_ok=True)
    write_header = not LABELS_CSV.exists()

    n_ok = 0
    t_start = time.perf_counter()
    with open(LABELS_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["attempt_id", "sentence_id", "voice", "original_text",
                             "spoken_text", "kind", "component", "from", "to",
                             "position", "score", "stt_text"])
        for s in sentences:
            rng = random.Random(f"{SEED}:{s['id']}:{args.voice}")  # 재현 가능
            jobs = [(s["text"], None)]
            for _ in range(args.variants):
                p = perturb(s["text"], rng)
                if p:
                    jobs.append(p)
            for spoken, label in jobs:
                with tempfile.TemporaryDirectory() as td:
                    mp3 = str(Path(td) / "synth.mp3")
                    asyncio.run(synthesize(spoken, args.voice, mp3))
                    body = post_attempt(s["id"], mp3)
                kind = "normal" if label is None else "perturbed"
                writer.writerow([
                    body["attempt_id"], s["id"], args.voice, s["text"], spoken, kind,
                    label["component"] if label else "", label["from"] if label else "",
                    label["to"] if label else "", label["position"] if label else "",
                    body["analysis"]["score"], body["stt"]["text"],
                ])
                n_ok += 1
                print(f"[{n_ok:>3}] s{s['id']:>2} {kind:<9} {body['analysis']['score']:>3}점"
                      f"  「{spoken}」 → 「{body['stt']['text']}」", flush=True)

    print(f"\n완료: {n_ok}건 생성 ({time.perf_counter() - t_start:.0f}s). "
          f"라벨: {LABELS_CSV}")


if __name__ == "__main__":
    main()
