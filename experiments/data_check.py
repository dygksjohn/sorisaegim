r"""6주차 — 데이터 축적 점검 (7주차 ML 준비).

시도 데이터·녹음 원본의 양과 품질을 요약한다. 완료 기준: 150건 이상.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\data_check.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import UPLOADS_DIR, get_conn

TARGET = 150


def main() -> None:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    by_source = conn.execute(
        "SELECT source, COUNT(*) n, ROUND(AVG(score),1) avg FROM attempts GROUP BY source"
    ).fetchall()
    by_type = conn.execute(
        "SELECT s.type, COUNT(*) n, ROUND(AVG(a.score),1) avg FROM attempts a"
        " JOIN sentences s ON s.id=a.sentence_id GROUP BY s.type ORDER BY n DESC"
    ).fetchall()
    by_day = conn.execute(
        "SELECT substr(created_at, 1, 10) d, COUNT(*) n FROM attempts GROUP BY d ORDER BY d"
    ).fetchall()
    sentences_covered = conn.execute(
        "SELECT COUNT(DISTINCT sentence_id) FROM attempts"
    ).fetchone()[0]
    n_sentences = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]

    err_counter: Counter = Counter()
    for (ej,) in conn.execute("SELECT errors_json FROM attempts"):
        for e in json.loads(ej):
            err_counter[e["type"]] += 1
    conn.close()

    files = [f for f in UPLOADS_DIR.iterdir() if f.is_file()] if UPLOADS_DIR.exists() else []
    size_mb = sum(f.stat().st_size for f in files) / 1e6

    print(f"== 시도 데이터 ==")
    print(f"  총 {total}건 / 목표 {TARGET}건 ({total / TARGET * 100:.0f}%)"
          + ("  ← 목표 달성" if total >= TARGET else f"  ← {TARGET - total}건 남음"))
    for r in by_source:
        role = "평가용(실사용)" if r["source"] == "user" else "학습용(합성 증강)"
        print(f"  - {r['source']:<5} {r['n']:>4}건  평균 {r['avg']}  ({role})")
    print(f"  문장 커버리지: {sentences_covered}/{n_sentences}문장")
    print(f"  일자별: " + ", ".join(f"{r['d']}({r['n']})" for r in by_day))
    print(f"\n== 유형별 ==")
    for r in by_type:
        print(f"  {r['type']:<8} {r['n']:>4}건  평균 {r['avg']}")
    print(f"\n== 오류 집계 (ML 라벨 후보) ==")
    for t, n in err_counter.most_common():
        print(f"  {t:<14} {n}건")
    print(f"\n== 녹음 원본 ==")
    print(f"  {len(files)}개 파일, {size_mb:.1f} MB (uploads\\)")
    print(f"\n판단 가이드: {TARGET}건 미달이면 본인 반복 사용으로 보충하거나,")
    print(f"7주차를 축소 시나리오(혼동 통계 분석)로 조정한다 (세부계획 7주차 참고).")


if __name__ == "__main__":
    main()
