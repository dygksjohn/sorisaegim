r"""1주차 녹음 20개(Whisper small t=0.0 인식 결과)를 비교 엔진에 통과 (2주차 완료 기준).

재인식 없이 results\correction_results.csv 의 저장된 인식 텍스트를 재사용한다.
기대: 정상 발음(normal_*)은 고득점, 오발음(wrong_*)은 낮은 점수 + 의도한 자모 오류 검출.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\engine_on_week1.py
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # engine 패키지

from engine import compare

CSV_PATH = Path(__file__).parent / "results" / "correction_results.csv"


def main() -> None:
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = [
            r for r in csv.DictReader(f)
            if r["model"] == "small" and float(r["temperature"]) == 0.0
        ]

    print(f"{'파일':<14} {'점수':>4}  {'인식(발음형)':<22} 오류")
    print("-" * 90)
    for row in rows:
        result = compare(row["target_text"], row["recognized"])
        errs = "; ".join(
            f"{e['syllable'] or '+'}[{e['component'][:4]}] "
            f"{e['expected'] or '∅'}→{e['actual'] or '∅'}"
            for e in result["errors"][:4]
        ) or "-"
        print(f"{row['file']:<14} {result['score']:>4}  "
              f"{result['recognized_pron']:<22} {errs}")

    normals = [r for r in rows if r["file"].startswith("normal")]
    wrongs = [r for r in rows if r["file"].startswith("wrong")]
    avg = lambda rs: sum(compare(r["target_text"], r["recognized"])["score"] for r in rs) / len(rs)
    print("-" * 90)
    print(f"정상 발음 평균: {avg(normals):.1f} / 오발음 평균: {avg(wrongs):.1f}")
    print("(직관 체크: 정상 ≈ 100, 오발음은 뚜렷이 낮아야 한다)")


if __name__ == "__main__":
    main()
