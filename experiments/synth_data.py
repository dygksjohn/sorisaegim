r"""TTS 오발음 주입 합성 데이터 생성 — v2 (+1주차 ML 고도화).

원리(v1과 동일): TTS는 입력 텍스트의 표준 발음대로 읽는다. 자모를 의도적으로 치환한
"틀린 텍스트"를 합성하면 "틀린 발음" 음성이 나오고, 라벨이 공짜로 정확하다.

v2 변경 (근거: docs\l2_error_distribution.md — 표와 이 코드는 함께 수정할 것):
  - 혼동 쌍을 L2 문헌 기반 가중치로 선택 (ICPhS 2023, 5개 모어권 통합 분포)
  - 성분 비중 초성30/중성25/받침45 (받침 감지율 35% 개선 과제에 표본 집중)
  - 무효 변형 기각: g2pk(변형)==g2pk(원문)이면 재시도 (v1에서 라벨 오류 5건 검출된 문제)
  - ㅐ↔ㅔ 제외 (현대 서울말 병합 — TTS 동음이라 라벨 노이즈)
  - 보이스 3종 + 속도/피치 지터로 화자 다양성 확보 (Edge-TTS 한국어 보이스가 3종뿐)
  - 라벨: results\synth_labels_v2.csv (v1 라벨 csv는 그대로 보존)

전제: 서버 실행 중.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\synth_data.py            # 3보이스 전체
    .venv\Scripts\python.exe experiments\synth_data.py --voice ko-KR-SunHiNeural
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
from engine import to_pronunciation  # noqa: E402
from engine.hangul import (  # noqa: E402
    CHOSEONG, JUNGSEONG, JONGSEONG, HANGUL_BASE,
    decompose_syllable, is_hangul_syllable,
)

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
RESULTS_DIR = Path(__file__).parent / "results"
LABELS_CSV = RESULTS_DIR / "synth_labels_v2.csv"
VARIANTS_PER_SENTENCE = 2
SEED = 20260705  # v2 (v1: 20260704)
VOICES = ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural", "ko-KR-HyunsuMultilingualNeural"]
RATES = ["-10%", "-5%", "+0%", "+5%", "+10%"]   # 화자 다양성용 지터
PITCHES = ["-20Hz", "-10Hz", "+0Hz", "+10Hz", "+20Hz"]

# ---- L2 통합 분포 가중 혼동 쌍 (docs\l2_error_distribution.md 표 2 미러) ----
# {from: [(to, weight), ...]}
CHO_CONFUSION = {
    "ㅋ": [("ㄱ", 3)], "ㅌ": [("ㄷ", 3)], "ㅍ": [("ㅂ", 3)], "ㅊ": [("ㅈ", 3)],
    "ㄲ": [("ㄱ", 3)], "ㄸ": [("ㄷ", 3)], "ㅃ": [("ㅂ", 3)], "ㅆ": [("ㅅ", 3)],
    "ㅉ": [("ㅈ", 3)],
    "ㄹ": [("ㄴ", 2)],
    "ㄱ": [("ㅋ", 1)], "ㄷ": [("ㅌ", 1)], "ㅂ": [("ㅍ", 1)],
    "ㅈ": [("ㅊ", 1), ("ㅅ", 1)], "ㅅ": [("ㅆ", 1)], "ㄴ": [("ㄹ", 1)],
}
JUNG_CONFUSION = {
    "ㅓ": [("ㅗ", 3)], "ㅗ": [("ㅓ", 3)],
    "ㅜ": [("ㅓ", 2), ("ㅡ", 2)], "ㅡ": [("ㅜ", 2)],
    "ㅟ": [("ㅣ", 2)],
    "ㅕ": [("ㅛ", 1)], "ㅛ": [("ㅕ", 1)],
}
JONG_DELETE_WEIGHT = 5  # 모든 받침 공통 — 공통 오류 2위 (받침 삭제)
JONG_CONFUSION = {
    "ㅇ": [("ㄴ", 3)],
    "ㄴ": [("ㅇ", 2), ("ㅁ", 1)],
    "ㅁ": [("ㄴ", 1), ("ㅇ", 1)],
    "ㄱ": [("ㄷ", 1), ("ㅂ", 1)], "ㄷ": [("ㄱ", 1), ("ㅂ", 1)], "ㅂ": [("ㄱ", 1), ("ㄷ", 1)],
}
COMPONENT_WEIGHTS = {"cho": 30, "jung": 25, "jong": 45}


def compose(cho: str, jung: str, jong: str) -> str:
    return chr(
        HANGUL_BASE
        + (CHOSEONG.index(cho) * 21 + JUNGSEONG.index(jung)) * 28
        + JONGSEONG.index(jong)
    )


def weighted_pick(rng: random.Random, pairs: list[tuple[str, int]]) -> str:
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def perturb(text: str, orig_pron: str, rng: random.Random) -> tuple[str, dict] | None:
    """문장에서 음절 하나의 자모 하나를 L2 가중 분포로 치환.

    발음형이 원문과 같아지는 무효 변형(예: 같이→가치)은 기각하고 재시도 —
    TTS 출력이 동일해져 라벨 오류가 되기 때문 (v1 데이터에서 5건 검출).
    """
    idxs = [i for i, ch in enumerate(text) if is_hangul_syllable(ch)]
    if not idxs:
        return None
    for _ in range(30):
        i = rng.choice(idxs)
        cho, jung, jong = decompose_syllable(text[i])
        component = rng.choices(
            list(COMPONENT_WEIGHTS), weights=list(COMPONENT_WEIGHTS.values()))[0]
        if component == "cho":
            if cho not in CHO_CONFUSION:
                continue
            new = weighted_pick(rng, CHO_CONFUSION[cho])
            new_syl, label = compose(new, jung, jong), ("choseong", cho, new)
        elif component == "jung":
            if jung not in JUNG_CONFUSION:
                continue
            new = weighted_pick(rng, JUNG_CONFUSION[jung])
            new_syl, label = compose(cho, new, jong), ("jungseong", jung, new)
        else:
            if not jong:
                continue  # 없는 받침에 추가는 배제 (v3 과제 — 분포 문서 3절)
            pairs = [("", JONG_DELETE_WEIGHT)] + JONG_CONFUSION.get(jong, [])
            new = weighted_pick(rng, [p for p in pairs if p[0] != jong])
            new_syl, label = compose(cho, jung, new), ("jongseong", jong, new)
        if new_syl == text[i]:
            continue
        variant = text[:i] + new_syl + text[i + 1:]
        if to_pronunciation(variant) == orig_pron:
            continue  # 무효 변형 — 표준 발음이 같아짐
        return variant, {
            "position": i, "orig_syllable": text[i], "new_syllable": new_syl,
            "component": label[0], "from": label[1], "to": label[2] or "(삭제)",
        }
    return None


async def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: str) -> None:
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out_path)


def post_attempt(sentence_id: int, mp3_path: str) -> dict:
    with open(mp3_path, "rb") as f:
        r = requests.post(f"{BASE}/attempts",
                          data={"sentence_id": sentence_id, "source": "synth"},
                          files={"audio": ("synth.mp3", f, "audio/mpeg")}, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS 오발음 주입 합성 v2")
    parser.add_argument("--voice", default=None, help="미지정 시 3보이스 전체")
    parser.add_argument("--variants", type=int, default=VARIANTS_PER_SENTENCE)
    args = parser.parse_args()
    voices = [args.voice] if args.voice else VOICES

    sentences = requests.get(f"{BASE}/sentences", timeout=30).json()["sentences"]
    RESULTS_DIR.mkdir(exist_ok=True)
    write_header = not LABELS_CSV.exists()

    # 이어받기: 이미 라벨이 있는 (보이스, 문장)은 건너뛴다 — 중단 후 재실행해도 중복 생성 없음
    done: set[tuple[str, int]] = set()
    if LABELS_CSV.exists():
        with open(LABELS_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                done.add((row["voice"], int(row["sentence_id"])))

    n_ok = 0
    t_start = time.perf_counter()
    with open(LABELS_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["attempt_id", "sentence_id", "voice", "rate", "pitch",
                             "original_text", "spoken_text", "kind", "component",
                             "from", "to", "position", "score", "stt_text"])
        for voice in voices:
            for s in sentences:
                if (voice, s["id"]) in done:
                    continue
                rng = random.Random(f"{SEED}:{s['id']}:{voice}")
                orig_pron = to_pronunciation(s["text"])
                jobs = [(s["text"], None)]
                for _ in range(args.variants):
                    p = perturb(s["text"], orig_pron, rng)
                    if p:
                        jobs.append(p)
                for spoken, label in jobs:
                    rate, pitch = rng.choice(RATES), rng.choice(PITCHES)
                    with tempfile.TemporaryDirectory() as td:
                        mp3 = str(Path(td) / "synth.mp3")
                        asyncio.run(synthesize(spoken, voice, rate, pitch, mp3))
                        body = post_attempt(s["id"], mp3)
                    kind = "normal" if label is None else "perturbed"
                    writer.writerow([
                        body["attempt_id"], s["id"], voice, rate, pitch,
                        s["text"], spoken, kind,
                        label["component"] if label else "",
                        label["from"] if label else "",
                        label["to"] if label else "",
                        label["position"] if label else "",
                        body["analysis"]["score"], body["stt"]["text"],
                    ])
                    n_ok += 1
                    print(f"[{n_ok:>3}] {voice.split('-')[2][:5]:<5} s{s['id']:>2}"
                          f" {kind:<9} {body['analysis']['score']:>3}점"
                          f"  「{spoken}」 → 「{body['stt']['text']}」", flush=True)

    print(f"\n완료: {n_ok}건 생성 ({time.perf_counter() - t_start:.0f}s). "
          f"라벨: {LABELS_CSV}")


if __name__ == "__main__":
    main()
