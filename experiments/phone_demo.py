r"""발음형 인식기 데모 — Whisper vs wav2vec2 오탐 비교 (+5주차).

1주차 녹음(정상 10 + 오발음 10)에 두 엔진을 나란히 돌려, 미세조정 wav2vec2가
**정발음에 헛오류를 덜 낸다**(오탐 52%→6% 서사)를 눈으로 보여준다.

전제: data/models/w2v2-jamo/ 에 미세조정 모델 배치 (docs/colab_실행가이드.md Step 9).
서버 불필요.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\phone_demo.py
산출: 콘솔 표 + results/phone_demo.md
"""

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import stt
import stt.phone as stt_phone
from engine import compare
from engine.phonetic import compare_phonetic
from whisper.audio import load_audio

REC_DIR = Path(__file__).parent / "recordings"
RESULTS = Path(__file__).parent / "results"
REPORT = RESULTS / "phone_demo.md"


def main() -> None:
    if not stt_phone.available():
        print("발음형 모델이 없습니다 — data/models/w2v2-jamo/ 에 배치 후 다시 실행.")
        print("절차: docs/colab_실행가이드.md 'Step 9 — 로컬 통합·데모'.")
        return

    manifest = REC_DIR / "manifest.csv"
    with open(manifest, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    lines = ["# 발음형 인식기 데모 — Whisper vs wav2vec2 (1주차 녹음 20건)\n"]
    lines.append("| 파일 | 제시어 | 의도 | W 점수(오류) | **W2V 점수(오류)** |")
    lines.append("|---|---|---|---|---|")

    # 정발음(normal)에서의 오탐 집계
    agg = {"whisper": {"score": [], "false_err": 0, "n": 0},
           "phone":   {"score": [], "false_err": 0, "n": 0}}

    print(f"{'파일':<14}{'W점수':>6}{'W오류':>6}  {'W2V점수':>8}{'W2V오류':>8}", flush=True)
    for r in rows:
        wav = REC_DIR / r["file"]
        if not wav.exists():
            continue
        samples = load_audio(str(wav))
        target = r["target_text"]
        is_normal = r["file"].startswith("normal")

        w = compare(target, stt.transcribe(samples)["text"])
        p = compare_phonetic(target, stt_phone.transcribe(samples)["phones"])
        we, pe = len(w["errors"]), len(p["errors"])

        if is_normal:  # 정발음 — 오류가 뜨면 오탐
            for eng, res, ne in (("whisper", w, we), ("phone", p, pe)):
                agg[eng]["score"].append(res["score"])
                agg[eng]["n"] += 1
                if ne > 0:
                    agg[eng]["false_err"] += 1

        lines.append(f"| {r['file']} | {target} | "
                     f"{'정발음' if is_normal else '오발음'} | "
                     f"{w['score']}({we}) | **{p['score']}({pe})** |")
        print(f"{r['file']:<14}{w['score']:>6}{we:>6}  {p['score']:>8}{pe:>8}", flush=True)

    lines.append("\n## 정발음 10건에서의 오탐 (핵심 지표)\n")
    lines.append("| 엔진 | 평균 점수 | 오탐(오류 뜬 건수) |\n|---|---|---|")
    for eng, ko in (("whisper", "Whisper"), ("phone", "wav2vec2(발음형)")):
        a = agg[eng]
        avg = sum(a["score"]) / max(a["n"], 1)
        lines.append(f"| {ko} | {avg:.0f} | {a['false_err']}/{a['n']} |")
    lines.append("\n> 정발음인데 오류가 뜨면 오탐. wav2vec2가 Whisper보다 오탐이 적으면 "
                 "AI Hub 실측(오탐 52%→6%)의 로컬 재현이다. (표본 10건이라 방향성 확인용.)")

    RESULTS.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n정발음 오탐 — Whisper {agg['whisper']['false_err']}/10 · "
          f"wav2vec2 {agg['phone']['false_err']}/10")
    print(f"→ {REPORT}")


if __name__ == "__main__":
    main()
