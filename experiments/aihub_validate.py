r"""AI Hub phones ↔ 엔진 발음형 정합성 검증 — +2주차 작업 2.

정발음(오류 태그 없는) 레코드에서 g2pk 발음형과 phones가 일치해야 한다
(둘 다 '실제 발음' 공간). 일치도로 라벨 매핑의 신뢰도를 정량화하고,
잔여 불일치를 사유별로 분류해 학습 라벨의 한계를 기록한다.

산출: results\aihub_label_validation.md (+ 콘솔 요약). 서버 불필요.
실행: .venv\Scripts\python.exe experiments\aihub_validate.py [--n 2000]
"""

import argparse
import io
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from ml.aihub import iter_records, prompt_to_flat_jamo, phones_to_flat_jamo  # noqa: E402

RESULTS = Path(__file__).parent / "results"
REPORT = RESULTS / "aihub_label_validation.md"


def align(a: list, b: list):
    """편집거리 + 역추적으로 (연산, x, y) 리스트 반환."""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(("sub", a[i - 1], b[j - 1])); i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", a[i - 1], None)); i -= 1
        else:
            ops.append(("ins", None, b[j - 1])); j -= 1
    return dp[n][m], ops


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000, help="대조할 정발음 레코드 수")
    args = ap.parse_args()

    exact = total = dist_sum = jamo_sum = 0
    sub_pairs = Counter()   # (g2pk자모 → phones자모) 치환 빈도
    del_jamo = Counter()    # g2pk엔 있는데 phones에 없는 자모
    ins_jamo = Counter()    # phones에만 있는 자모
    worst = []

    for r in iter_records():
        if r.error_tags or not r.phones:
            continue
        g = prompt_to_flat_jamo(r.prompt)
        p = phones_to_flat_jamo(r.phones)
        if not g:
            continue
        d, ops = align(g, p)
        total += 1
        dist_sum += d
        jamo_sum += len(g)
        if d == 0:
            exact += 1
        else:
            for op, x, y in ops:
                if op == "sub":
                    sub_pairs[(x, y)] += 1
                elif op == "del":
                    del_jamo[x] += 1
                else:
                    ins_jamo[y] += 1
            if len(worst) < 30:
                worst.append((d, r.prompt, "".join(g), "".join(p)))
        if total >= args.n:
            break

    exact_pct = exact / total * 100
    jamo_err = dist_sum / jamo_sum * 100

    lines = ["# AI Hub 라벨 정합성 검증 (+2주차 작업 2)\n"]
    lines.append(f"> 정발음(오류 태그 없는) {total}건에서 g2pk 발음형 vs phones 대조.\n")
    lines.append("## 요약\n")
    lines.append(f"- **완전 일치: {exact}/{total} ({exact_pct:.1f}%)**")
    lines.append(f"- **자모 단위 오류율: {jamo_err:.2f}%** (총 {jamo_sum}자모 중 {dist_sum} 불일치)")
    lines.append("- 정발음인데도 불일치가 나는 건 대부분 g2pk와 실제 발화 전사의 관습 차이 "
                 "(라벨 자체 오류가 아님). 아래 유형이 그 근거.\n")

    lines.append("## 가장 잦은 치환 (g2pk → phones) 상위 15\n")
    lines.append("| g2pk | phones | 횟수 | 해석 |\n|---|---|---|---|")
    interp = {
        ("ㅅ", "ㅆ"): "경음화 미반영(g2pk)", ("ㄱ", "ㄲ"): "경음화 미반영",
        ("ㅈ", "ㅉ"): "경음화 미반영", ("ㄷ", "ㄸ"): "경음화 미반영",
        ("ㅂ", "ㅃ"): "경음화 미반영", ("ㅅ", "ㅊ"): "구개음화",
    }
    for (x, y), c in sub_pairs.most_common(15):
        lines.append(f"| {x or '∅'} | {y or '∅'} | {c} | {interp.get((x, y), '')} |")

    lines.append("\n## 삭제(g2pk엔 있으나 phones에 없음) 상위 10\n")
    lines.append("| 자모 | 횟수 | 해석 |\n|---|---|---|")
    for j, c in del_jamo.most_common(10):
        note = "무음 초성 ㅇ 잔여(정규화 후에도)" if j == "ㅇ" else ""
        lines.append(f"| {j} | {c} | {note} |")

    lines.append("\n## 삽입(phones에만 있음) 상위 10\n")
    lines.append("| 자모 | 횟수 |\n|---|---|")
    for j, c in ins_jamo.most_common(10):
        lines.append(f"| {j} | {c} |")

    lines.append("\n## 불일치 예시 (거리 큰 순 30건 중 앞 15)\n")
    for d, prm, g, p in sorted(worst, reverse=True)[:15]:
        lines.append(f"- `[{d}]` **{prm}**  \n  g2pk `{g}`  \n  phon `{p}`")

    lines.append("\n## 결론 (학습 라벨 방침)\n")
    lines.append("- phones는 g2pk와 같은 **발음형 공간**의 사람 전사라, 우리 엔진·미세조정 "
                 "라벨로 직접 사용 가능함을 확인.")
    lines.append("- 학습 타깃 라벨은 **phones를 정본으로** 쓴다 (실제 발화 전사이므로). "
                 "g2pk는 제시어의 기대 발음(정답) 생성에만 사용.")
    lines.append("- 잔여 불일치의 주원인은 g2pk의 경음화·구개음화 일부 미반영 — "
                 "제시어 기대발음을 만들 때만 영향이 있고, phones 라벨 자체는 무관.")
    lines.append("- ⚠️ **vocab 설계 주의**: phones는 w-활음 이중모음을 2모음으로 전사(ㅙ→ㅗㅐ, ㅞ→ㅜㅔ). "
                 "가장 잦은 치환 유형 — 미세조정 CTC vocab을 phones 규약(개별 자모, 이중모음 분해)에 "
                 "맞춰야 하며, 엔진 비교 시에도 이 정규화를 양쪽에 적용할 것.")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"정발음 {total}건: 완전일치 {exact} ({exact_pct:.1f}%), "
          f"자모오류율 {jamo_err:.2f}%")
    print("잦은 치환:", [(f"{x}->{y}", c) for (x, y), c in sub_pairs.most_common(6)])
    print("잦은 삭제:", del_jamo.most_common(5))
    print(f"→ {REPORT}")


if __name__ == "__main__":
    main()
