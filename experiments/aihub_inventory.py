r"""AI Hub 4종 인벤토리 — +2주차 작업 1.

산출:
  results\aihub_manifest.csv   레코드별 (권역·화자·숙달도·제시어·실발화·오류버킷·wav)
  results\aihub_inventory.md   집계 요약 (권역/숙달도/오류 성분별 분포, 받침 표본 수)
콘솔에도 요약을 출력한다. 서버 불필요.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\aihub_inventory.py
"""

import csv
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ml.aihub import iter_records  # noqa: E402

RESULTS = Path(__file__).parent / "results"
MANIFEST = RESULTS / "aihub_manifest.csv"
REPORT = RESULTS / "aihub_inventory.md"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    rows = []
    by_region = Counter()
    by_prof = Counter()
    tag_counts = Counter()
    bucket_counts = Counter()
    comp_counts = Counter()               # segmental 오류 성분별
    region_comp = defaultdict(Counter)    # 권역 × 성분
    speakers = defaultdict(set)           # 권역별 화자 집합
    n_missing_wav = 0
    n_with_error = 0

    for r in iter_records():
        if r.wav_path is None:
            n_missing_wav += 1
        by_region[r.region] += 1
        by_prof[r.proficiency] += 1
        speakers[r.region].add(r.user_id)
        if r.error_tags:
            n_with_error += 1
        for t in r.error_tags:
            tag_counts[t["tag"]] += 1
            bucket_counts[t["bucket"]] += 1
            if t["component"]:
                comp_counts[t["component"]] += 1
                region_comp[r.region][t["component"]] += 1
        rows.append({
            "region": r.region, "user_id": r.user_id,
            "proficiency": r.proficiency, "nationality": r.nationality,
            "prompt": r.prompt, "phones": r.phones,
            "pronun_eval": r.pronun_eval,
            "n_errors": len(r.error_tags),
            "error_buckets": ";".join(sorted(r.error_buckets)),
            "error_components": ";".join(sorted(r.error_components)),
            "error_tags": ";".join(t["tag"] for t in r.error_tags),
            "wav_path": (r.wav_path.relative_to(Path(__file__).parent.parent).as_posix()
                         if r.wav_path else ""),
        })

    with open(MANIFEST, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total = len(rows)
    comp_ko = {"choseong": "초성", "jungseong": "중성", "jongseong": "종성"}

    lines = ["# AI Hub 4종 인벤토리 (+2주차 작업 1)\n"]
    lines.append(f"> pronunciation 라벨 전수 {total}건. wav 누락 {n_missing_wav}건. "
                 f"오류 태그 보유 {n_with_error}건 ({n_with_error / total * 100:.0f}%).\n")
    lines.append("## 권역별 (레코드 / 화자 수)\n")
    lines.append("| 권역 | 레코드 | 화자 |\n|---|---|---|")
    for reg in ("asia", "china_japan", "english", "europe"):
        lines.append(f"| {reg} | {by_region[reg]} | {len(speakers[reg])} |")
    lines.append(f"| **합계** | **{total}** | **{sum(len(s) for s in speakers.values())}** |\n")

    lines.append("## 숙달도별\n")
    lines.append("| 숙달도 | 건수 |\n|---|---|")
    for p in ("Beginner", "Intermediate", "Advance", "Fluent"):
        lines.append(f"| {p} | {by_prof[p]} |")

    lines.append("\n## 오류 버킷별 (태그 총 개수 기준)\n")
    lines.append("| 버킷 | 태그 수 | 설명 |\n|---|---|---|")
    desc = {"segmental": "초성·종성·모음 — 자모 엔진 직접 판정",
            "phon_rule": "음운규칙 — 표기 수렴 문제, wav2vec2 조준 대상",
            "prosodic": "운율·반복·기타 — 범위 밖"}
    for b in ("segmental", "phon_rule", "prosodic"):
        lines.append(f"| {b} | {bucket_counts[b]} | {desc[b]} |")

    lines.append("\n## segmental 성분별 (핵심 — 받침 표본)\n")
    lines.append("| 성분 | 전체 | asia | china_japan | english | europe |\n|---|---|---|---|---|---|")
    for comp in ("choseong", "jungseong", "jongseong"):
        cells = " | ".join(str(region_comp[reg][comp]) for reg in
                           ("asia", "china_japan", "english", "europe"))
        lines.append(f"| {comp_ko[comp]} | {comp_counts[comp]} | {cells} |")

    lines.append("\n## 음운규칙(phon_rule) 세부 — 1주차 표기 수렴 문제의 실데이터\n")
    lines.append("| 규칙 | 태그 수 |\n|---|---|")
    for tag, n in tag_counts.most_common():
        if tag in {"비음화", "경음화", "유음화", "구개음화", "격음화",
                   "연음규칙", "ㄴ-첨가", "음운탈락", "모음삽입"}:
            lines.append(f"| {tag} | {n} |")

    lines.append(f"\n---\n원본 매니페스트: `{MANIFEST.name}` ({total}행)\n")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    # 콘솔 요약
    print(f"레코드 {total}건 · 화자 {sum(len(s) for s in speakers.values())}명 · "
          f"오류보유 {n_with_error}건 · wav누락 {n_missing_wav}\n")
    print("권역별:", dict(by_region))
    print("숙달도:", dict(by_prof))
    print("버킷:", dict(bucket_counts))
    print("성분(segmental):", {comp_ko[k]: v for k, v in comp_counts.items()})
    print(f"\n→ {MANIFEST}\n→ {REPORT}")


if __name__ == "__main__":
    main()
