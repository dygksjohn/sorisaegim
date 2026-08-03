r"""로컬 실행 재현 — 응답시간 기준선 측정 (7단계 3).

콜드(모델 최초 로딩)와 웜(이후 추론)을 분리 측정한다 — 콜드스타트가 배포 판단의 핵심.
측정 조건을 함께 남긴다(조건 없는 숫자는 비교에 못 쓴다).

대상: whisper 경로(항상) + phone 경로(모델이 data/models/w2v2-jamo/ 에 있을 때만).
1주차 녹음(정발음 5건)으로 측정. 서버 불필요(엔진·STT 직접 호출).

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\bench_local.py
산출: 콘솔 + results\bench_local.md
"""

import io
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from whisper.audio import load_audio  # noqa: E402

REC = Path(__file__).parent / "recordings"
RESULTS = Path(__file__).parent / "results"
FILES = [f"normal_{i:02d}.wav" for i in range(1, 6)]
SENTENCES = {  # 1주차 녹음 제시어 (attempts 1~5 = 시드 1~5)
    "normal_01.wav": "국물이 정말 시원하다", "normal_02.wav": "밥을 먹었다",
    "normal_03.wav": "신라면이 맵다", "normal_04.wav": "좋다고 말했다",
    "normal_05.wav": "학교에 갔다",
}


def bench_whisper(samples_list):
    import stt
    from engine import compare
    t0 = time.perf_counter()
    stt.transcribe(samples_list[0][1])  # 콜드 — 모델 로딩 포함
    cold = time.perf_counter() - t0
    warm, cmp = [], []
    for fn, samples in samples_list:
        t = time.perf_counter()
        r = stt.transcribe(samples)
        warm.append(time.perf_counter() - t)
        t = time.perf_counter()
        compare(SENTENCES[fn], r["text"])
        cmp.append(time.perf_counter() - t)
    return cold, warm, cmp


def bench_phone(samples_list):
    import stt.phone as p
    if not p.available():
        return None
    from engine.phonetic import compare_phonetic
    t0 = time.perf_counter()
    p.transcribe(samples_list[0][1])
    cold = time.perf_counter() - t0
    warm, cmp = [], []
    for fn, samples in samples_list:
        t = time.perf_counter()
        r = p.transcribe(samples)
        warm.append(time.perf_counter() - t)
        t = time.perf_counter()
        compare_phonetic(SENTENCES[fn], r["phones"])
        cmp.append(time.perf_counter() - t)
    return cold, warm, cmp


def fmt(xs):
    return (f"평균 {statistics.mean(xs):.2f}s · p50 {statistics.median(xs):.2f}s · "
            f"최대 {max(xs):.2f}s (n={len(xs)})")


def main() -> None:
    samples_list = [(fn, load_audio(str(REC / fn))) for fn in FILES
                    if (REC / fn).exists()]
    lines = ["# 로컬 실행 시간 기준선 (7단계 3)\n"]
    lines.append(f"> 측정 조건: {platform.system()} · Python {platform.python_version()} · "
                 f"CPU 추론 · 1주차 정발음 {len(samples_list)}건 · 서버 미경유(직접 호출).\n")

    cold, warm, cmp = bench_whisper(samples_list)
    lines.append("## Whisper 경로 (기본 엔진)\n")
    lines.append(f"- **콜드 로딩+첫 추론: {cold:.2f}s** (모델 메모리 적재 포함 — 콜드스타트 기준선)")
    lines.append(f"- 웜 추론: {fmt(warm)}")
    lines.append(f"- 자모 비교 엔진: {fmt(cmp)} (무시할 수준)")
    print(f"[whisper] 콜드 {cold:.2f}s · 웜 {fmt(warm)}")

    ph = bench_phone(samples_list)
    lines.append("\n## 발음형 인식기 경로 (engine=phone)\n")
    if ph is None:
        lines.append("- **모델 미배치 — 측정 보류.** data/models/w2v2-jamo/ 배치 후 재실행 "
                     "(docs/colab_실행가이드.md Step 9). CPU 추론이라 whisper보다 느릴 것으로 예상.")
        print("[phone] 모델 없음 — 측정 보류")
    else:
        pcold, pwarm, pcmp = ph
        lines.append(f"- **콜드 로딩+첫 추론: {pcold:.2f}s**")
        lines.append(f"- 웜 추론: {fmt(pwarm)}")
        lines.append(f"- 발음형 비교: {fmt(pcmp)}")
        print(f"[phone] 콜드 {pcold:.2f}s · 웜 {fmt(pwarm)}")

    lines.append("\n> 참고: 3주차 API 수동 테스트 기준선은 평균 2.1s / 최대 5.0s(Whisper, 로컬, "
                 "서버 경유 콜드 혼재). 이번 값은 콜드/웜 분리 + 서버 미경유라 직접 비교는 주의.")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "bench_local.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {RESULTS / 'bench_local.md'}")


if __name__ == "__main__":
    main()
