"""자모 토큰 시퀀스 정렬 (편집거리 + 역추적).

두 JamoToken 시퀀스를 Levenshtein DP로 정렬하고, 연산 목록
(match / substitution / insertion / deletion)을 자모 단위로 산출한다.
"""

from dataclasses import dataclass

from .hangul import JamoToken

MATCH, SUB, INS, DEL = "match", "substitution", "insertion", "deletion"


@dataclass(frozen=True)
class AlignOp:
    op: str                      # match | substitution | insertion | deletion
    ref: JamoToken | None        # 정답 쪽 토큰 (insertion이면 None)
    hyp: JamoToken | None        # 인식 쪽 토큰 (deletion이면 None)


def _equal(a: JamoToken, b: JamoToken) -> bool:
    # 같은 자모라도 성분이 다르면(예: 초성 ㅇ vs 종성 ㅇ) 다른 소리다.
    return a.jamo == b.jamo and a.component == b.component


def align(ref: list[JamoToken], hyp: list[JamoToken]) -> list[AlignOp]:
    """ref(정답 발음형) 대비 hyp(인식 발음형)의 자모 단위 정렬."""
    n, m = len(ref), len(hyp)
    # dp[i][j] = ref[:i] vs hyp[:j] 최소 편집비용
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if _equal(ref[i - 1], hyp[j - 1]) else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,  # match/sub
                dp[i - 1][j] + 1,         # deletion (정답에 있는데 발화에 없음)
                dp[i][j - 1] + 1,         # insertion (발화에 잉여)
            )

    # 역추적 — 대각선(match/sub) 우선
    ops: list[AlignOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if _equal(ref[i - 1], hyp[j - 1]) else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                ops.append(AlignOp(MATCH if cost == 0 else SUB, ref[i - 1], hyp[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(AlignOp(DEL, ref[i - 1], None))
            i -= 1
            continue
        ops.append(AlignOp(INS, None, hyp[j - 1]))
        j -= 1
    ops.reverse()
    return ops
