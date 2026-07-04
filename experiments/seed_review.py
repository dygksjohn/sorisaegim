r"""5주차 — 시드 문장 발음형 전수 검수용 출력 (완료 기준: 30문장 눈 검수).

시드를 적용(init_db)한 뒤 DB의 전체 문장을 유형별로 출력한다.
발음형(pron)이 국어 규범과 다르면 해당 문장을 교체할 것 (g2pk를 고치는 것보다 빠르다).

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\seed_review.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import get_conn, init_db


def main() -> None:
    init_db()  # 새 시드 반영 (기존 id 불변)
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text, pron, type, difficulty FROM sentences ORDER BY type, difficulty, id"
    ).fetchall()
    conn.close()

    cur_type = None
    for r in rows:
        if r["type"] != cur_type:
            cur_type = r["type"]
            n = sum(1 for x in rows if x["type"] == cur_type)
            print(f"\n== {cur_type} ({n}문장) ==")
        print(f"  [{r['id']:>2}] 난이도{r['difficulty']}  {r['text']:<16} →  {r['pron']}")
    print(f"\n총 {len(rows)}문장. 발음형이 규범과 다른 항목이 있으면 알려주세요 (문장 교체).")


if __name__ == "__main__":
    main()
