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


def _balance_by_region(recs, per):
    """권역 라운드로빈으로 per개 결정적 선택."""
    by_region = defaultdict(list)
    for r in sorted(recs, key=lambda r: (r.region, r.user_id, r.prompt)):
        by_region[r.region].append(r)
    picked, ri, regions = [], 0, sorted(by_region)
    while len(picked) < per and any(by_region.values()):
        reg = regions[ri % len(regions)]
        if by_region[reg]:
            picked.append(by_region[reg].pop(0))
        ri += 1
    return picked


def collect_samples(per: int):
    """성분별 단일-분절-오류 레코드를 권역 균형 있게 per개씩."""
    buckets = defaultdict(list)
    for r in iter_records():
        if r.wav_path is None:
            continue
        seg = [t for t in r.error_tags if t["component"]]
        if len(seg) != 1:
            continue  # 단일 분절 오류만 (깨끗한 귀속)
        buckets[seg[0]["component"]].append(r)
    return {comp: _balance_by_region(buckets[comp], per) for comp in COMPONENTS}


def collect_phon_rule_and_control(per: int):
    """phon_rule 단일 태그(분절 태그 없음) 레코드 + 정발음 대조군."""
    phon, control = [], []
    for r in iter_records():
        if r.wav_path is None:
            continue
        seg = [t for t in r.error_tags if t["component"]]
        rule = [t for t in r.error_tags if t["bucket"] == "phon_rule"]
        if not r.error_tags:
            control.append(r)                       # 정발음 (오탐률 대조군)
        elif len(r.error_tags) == 1 and rule and not seg:
            phon.append(r)                          # 단일 음운규칙 오류
    return _balance_by_region(phon, per), _balance_by_region(control, per)


def run_phon_rule(per: int) -> None:
    """작업 3b: phon_rule 감지율 + 정발음 오탐률 대조. 감지=엔진이 오류 1개라도 플래그."""
    phon, control = collect_phon_rule_and_control(per)
    print(f"표본: phon_rule {len(phon)}, 정발음 대조 {len(control)}", flush=True)
    rule_by = Counter()  # 규칙별 감지
    rule_tot = Counter()
    phon_flag = ctrl_flag = 0
    misses = []
    t0, n = time.perf_counter(), 0
    for r in phon:
        stt_text = stt.transcribe(str(r.wav_path))["text"]
        res = compare(r.prompt, stt_text)
        flagged = bool(res["errors"])
        phon_flag += int(flagged)
        tag = r.error_tags[0]["tag"]
        rule_tot[tag] += 1
        rule_by[tag] += int(flagged)
        if not flagged and len(misses) < 12:
            misses.append((tag, r.prompt, stt_text, res["score"]))
        n += 1
        if n % 25 == 0:
            print(f"  phon {n} ({time.perf_counter()-t0:.0f}s)", flush=True)
    for r in control:
        stt_text = stt.transcribe(str(r.wav_path))["text"]
        res = compare(r.prompt, stt_text)
        ctrl_flag += int(bool(res["errors"]))
        n += 1
        if n % 25 == 0:
            print(f"  +ctrl {n} ({time.perf_counter()-t0:.0f}s)", flush=True)

    pf = phon_flag / len(phon) * 100
    cf = ctrl_flag / len(control) * 100
    lines = ["# phon_rule(음운규칙) 감지율 + 오탐 대조 — 작업 3b\n"]
    lines.append("> 감지 = 엔진이 오류 1개라도 플래그(규칙 위반은 정답발음과의 괴리로 나타남). "
                 "정발음 대조군의 플래그율이 오탐(false positive) 기준선.\n")
    lines.append("## 핵심\n")
    lines.append(f"- **phon_rule 감지율: {phon_flag}/{len(phon)} = {pf:.0f}%**")
    lines.append(f"- **정발음 오탐률: {ctrl_flag}/{len(control)} = {cf:.0f}%** (대조군)")
    lines.append(f"- **순감지 신호(감지−오탐): {pf-cf:+.0f}%p**\n")
    lines.append("## 규칙별 감지율\n| 규칙 | 표본 | 감지 | 감지율 |\n|---|---|---|---|")
    for tag, tot in rule_tot.most_common():
        lines.append(f"| {tag} | {tot} | {rule_by[tag]} | {rule_by[tag]/tot*100:.0f}% |")
    lines.append("\n## 미감지 예시 (Whisper 정규화로 오류 소실)\n")
    for tag, prompt, stt_text, score in misses:
        lines.append(f"- [{tag}] **{prompt}** → `{stt_text}` (점수 {score})")
    lines.append(f"\n---\n총 {n}건, {time.perf_counter()-t0:.0f}s.\n")
    lines.append("**판정**: phon_rule 순감지 신호가 분절음(작업 3의 62~81%)보다 뚜렷이 낮으면, "
                 "그 격차가 wav2vec2 조준 검사의 정당한 표적이자 미세조정 before 지표다.")
    (RESULTS / "aihub_detection_phon_rule.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nphon_rule 감지 {pf:.0f}% / 정발음 오탐 {cf:.0f}% / 순신호 {pf-cf:+.0f}%p")
    print(f"→ {RESULTS / 'aihub_detection_phon_rule.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=120, help="성분별 표본 수")
    ap.add_argument("--mode", choices=["segmental", "phon_rule"], default="segmental")
    args = ap.parse_args()

    if args.mode == "phon_rule":
        run_phon_rule(args.per)
        return

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
