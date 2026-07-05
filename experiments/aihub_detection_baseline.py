r"""실전 감지율 기준선 — +2주차 작업 3 (이번 주 헤드라인).

현 시스템(Whisper small + 자모 비교 엔진)이 AI Hub 실발화의 '사람이 태그한'
성분 오류를 얼마나 잡아내는가. 합성 기준 과제 D(초성67/중성63/받침35%)의 실데이터 버전.

방법:
  - segmental 오류 태그(초성/종성/모음오류)가 있는 레코드를 성분별로 표집.
  - 깨끗한 귀속을 위해 '단일 분절 오류'(해당 성분 태그 1개 + 다른 분절 태그 없음) 우선.
  - 각 wav → Whisper → compare(prompt, stt) → 엔진이 같은 성분 오류를 냈으면 '감지'.
  - 위치 무관 성분 단위 감지 (합성 과제 D와 동일 기준).

한계: reference는 g2pk 기대발음(정발음 대비 자모오류율 2.63%, 작업2). 이 노이즈가
  소폭 섞이나 방향성 판단엔 무방. 진짜 개선은 wav2vec2 조준 검사(+3~5주차)에서.

산출: results\aihub_detection_baseline.md. 서버 불필요(stt 모듈 직접 사용).
실행: .venv\Scripts\python.exe experiments\aihub_detection_baseline.py [--per 120]
"""

import argparse
import io
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import stt  # noqa: E402
from engine import compare  # noqa: E402
from ml.aihub import iter_records  # noqa: E402

RESULTS = Path(__file__).parent / "results"
REPORT = RESULTS / "aihub_detection_baseline.md"
COMPONENTS = ["choseong", "jungseong", "jongseong"]
COMP_KO = {"choseong": "초성", "jungseong": "중성", "jongseong": "받침"}
SYNTH_BASELINE = {"choseong": 67, "jungseong": 63, "jongseong": 35}  # 과제 D


def collect_samples(per: int):
    """성분별 단일-분절-오류 레코드를 권역 균형 있게 per개씩."""
    buckets = defaultdict(list)  # component -> [record]
    for r in iter_records():
        if r.wav_path is None:
            continue
        seg = [t for t in r.error_tags if t["component"]]
        if len(seg) != 1:
            continue  # 단일 분절 오류만 (깨끗한 귀속)
        comp = seg[0]["component"]
        buckets[comp].append(r)
    # 권역 균형: 라운드로빈으로 per개 선택 (결정적 — 정렬 후 stride)
    chosen = {}
    for comp in COMPONENTS:
        recs = sorted(buckets[comp], key=lambda r: (r.region, r.user_id, r.prompt))
        by_region = defaultdict(list)
        for r in recs:
            by_region[r.region].append(r)
        picked, ri = [], 0
        regions = sorted(by_region)
        while len(picked) < per and any(by_region.values()):
            reg = regions[ri % len(regions)]
            if by_region[reg]:
                picked.append(by_region[reg].pop(0))
            ri += 1
        chosen[comp] = picked
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=120, help="성분별 표본 수")
    args = ap.parse_args()

    chosen = collect_samples(args.per)
    print("표본:", {COMP_KO[c]: len(v) for c, v in chosen.items()}, flush=True)

    detected = Counter()
    total = Counter()
    any_flag = Counter()   # 엔진이 아무 오류라도 낸 비율 (민감도)
    rows = []
    t0 = time.perf_counter()
    n = 0
    for comp in COMPONENTS:
        for r in chosen[comp]:
            stt_text = stt.transcribe(str(r.wav_path))["text"]
            res = compare(r.prompt, stt_text)
            flagged = {e["component"] for e in res["errors"]}
            hit = comp in flagged
            total[comp] += 1
            detected[comp] += int(hit)
            any_flag[comp] += int(bool(flagged))
            rows.append((comp, r.region, r.prompt, stt_text, res["score"], hit))
            n += 1
            if n % 25 == 0:
                el = time.perf_counter() - t0
                print(f"  {n}건 ({el:.0f}s, {el/n:.1f}s/건)", flush=True)

    lines = ["# 실전 감지율 기준선 — AI Hub 실발화 (+2주차 작업 3)\n"]
    lines.append(f"> 현 시스템(Whisper small + 자모 엔진)이 사람이 태그한 성분 오류를 "
                 f"잡는 비율. 단일 분절 오류 레코드 표집.\n")
    lines.append("## 성분별 감지율 — 합성(과제 D) 대비\n")
    lines.append("| 성분 | 표본 | 감지 | **실전 감지율** | 합성 기준 | 차이 |\n|---|---|---|---|---|---|")
    for comp in COMPONENTS:
        rate = detected[comp] / total[comp] * 100 if total[comp] else 0
        base = SYNTH_BASELINE[comp]
        diff = rate - base
        lines.append(f"| {COMP_KO[comp]} | {total[comp]} | {detected[comp]} | "
                     f"**{rate:.0f}%** | {base}% | {diff:+.0f}%p |")
    lines.append("")
    lines.append("## 엔진 민감도 (아무 오류라도 플래그한 비율)\n")
    lines.append("| 성분 | 비율 |\n|---|---|")
    for comp in COMPONENTS:
        lines.append(f"| {COMP_KO[comp]} | {any_flag[comp] / total[comp] * 100:.0f}% |")

    lines.append("\n## 오탐지 예시 — 감지 실패 (받침 위주 10건)\n")
    misses = [r for r in rows if r[0] == "jongseong" and not r[5]][:10]
    for comp, region, prompt, stt_text, score, hit in misses:
        lines.append(f"- **{prompt}** → Whisper `{stt_text}` (점수 {score}) — 받침 오류 미감지")

    el = time.perf_counter() - t0
    lines.append(f"\n---\n총 {n}건, {el:.0f}s ({el/n:.1f}s/건). Whisper small CPU.\n")
    lines.append("**해석**: 실전 감지율이 합성 기준과 크게 다르면, 합성 분석의 한계"
                 "(TTS가 음향적으로 오류를 뚜렷이 못 낸 부분)가 정량화된 것. "
                 "받침 감지율이 낮게 유지되면 wav2vec2 조준 검사의 개선 여지가 그만큼 크다.")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print("\n=== 실전 감지율 ===")
    for comp in COMPONENTS:
        rate = detected[comp] / total[comp] * 100 if total[comp] else 0
        print(f"  {COMP_KO[comp]}: {detected[comp]}/{total[comp]} = {rate:.0f}% "
              f"(합성 {SYNTH_BASELINE[comp]}%)")
    print(f"→ {REPORT}")


if __name__ == "__main__":
    main()
