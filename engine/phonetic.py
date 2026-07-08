"""발음형(평면 자모) 비교 — 음소 인식기(wav2vec2) 출력용.

기존 `engine.compare`는 음절 기반 STT(Whisper) 출력을 g2pk로 발음형 변환해 비교한다.
미세조정한 wav2vec2는 이미 **발음형 자모 시퀀스**(예: "ㄱㅗㅈㅓ")를 출력하므로,
g2p 재적용 없이 그대로 제시어의 기대 발음형과 자모 단위로 정렬한다.

phones 규약(AI Hub 사람 전사와 동일):
  - 초성 무음 ㅇ은 표기하지 않는다 (음가 없음). 받침 ㅇ은 유지.
  - 겹받침은 개별 자모로 분해 (ㄼ→ㄹㅂ). g2pk가 자음군 단순화를 했으면 해당 없음.
  - 특수 토큰 'spn'(발화 잡음)은 무시.

반환 dict는 `engine.compare`와 같은 형태라 API·프론트가 그대로 재사용한다.
"""

from .g2p import to_pronunciation
from .hangul import CHAR, CHO, JONG, JamoToken, decompose_text

MATCH, SUB, INS, DEL = "match", "substitution", "insertion", "deletion"

# 겹받침 → 개별 자모 (g2pk 미단순화 시 폴백)
COMPOSITE_JONG = {
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ",
    "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ",
}
_SPN = set("spn")


def ref_flat_tokens(pron: str) -> list[JamoToken]:
    """발음형 텍스트(음절) → phones 규약 평면 자모 토큰 (성분·음절 메타 유지)."""
    out: list[JamoToken] = []
    for t in decompose_text(pron):
        if t.component == CHAR or not t.jamo:
            continue
        if t.component == CHO and t.jamo == "ㅇ":
            continue  # 무음 초성 ㅇ — 표기 안 함
        if t.component == JONG and t.jamo in COMPOSITE_JONG:
            for j in COMPOSITE_JONG[t.jamo]:
                out.append(JamoToken(j, JONG, t.syllable_index, t.syllable))
        else:
            out.append(JamoToken(t.jamo, t.component, t.syllable_index, t.syllable))
    return out


def phones_to_jamo(phones: str) -> list[str]:
    """모델 출력 문자열 → 개별 자모 리스트 (spn·공백 제거)."""
    return [c for c in phones if c not in _SPN and not c.isspace()]


def _align(ref: list[JamoToken], hyp: list[str]):
    """ref(메타 보유) 대비 hyp(순수 자모) 정렬 — 자모 값만으로 매칭."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1].jamo == hyp[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j - 1] + cost, dp[i - 1][j] + 1, dp[i][j - 1] + 1)
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if ref[i - 1].jamo == hyp[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                ops.append((MATCH if cost == 0 else SUB, ref[i - 1], hyp[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append((DEL, ref[i - 1], None))
            i -= 1
            continue
        ops.append((INS, None, hyp[j - 1]))
        j -= 1
    ops.reverse()
    return ops, dp[n][m]


def compare_phonetic(reference: str, phones: str) -> dict:
    """제시어 표기 vs 모델 발음형 자모 출력 비교.

    Args:
        reference: 제시어 표기. 예: "국물이 좋다"
        phones: 음소 인식기 출력 발음형 자모. 예: "궁무리조타"의 자모열
    Returns:
        engine.compare와 동일 형태 dict (score, errors[type/position/syllable/
        component/expected/actual], reference_pron 등).
    """
    reference = (reference or "").strip()
    ref_pron = to_pronunciation(reference) if reference else ""
    ref_tokens = ref_flat_tokens(ref_pron)
    hyp = phones_to_jamo(phones or "")

    ops, distance = _align(ref_tokens, hyp)
    errors = []
    last_syl = 0
    for op, ref_tok, hyp_jamo in ops:
        if ref_tok is not None:
            last_syl = ref_tok.syllable_index
        if op == MATCH:
            continue
        if op == SUB:
            errors.append({
                "type": SUB, "position": ref_tok.syllable_index,
                "syllable": ref_tok.syllable, "component": ref_tok.component,
                "expected": ref_tok.jamo, "actual": hyp_jamo,
            })
        elif op == DEL:
            errors.append({
                "type": DEL, "position": ref_tok.syllable_index,
                "syllable": ref_tok.syllable, "component": ref_tok.component,
                "expected": ref_tok.jamo, "actual": None,
            })
        else:  # INS — 발화 잉여 자모
            errors.append({
                "type": INS, "position": last_syl, "syllable": None,
                "component": None, "expected": None, "actual": hyp_jamo,
            })

    denom = max(len(ref_tokens), len(hyp), 1)
    score = max(0, round(100 * (1 - distance / denom)))
    return {
        "score": score,
        "reference": reference,
        "reference_pron": ref_pron,
        "recognized": phones,
        "recognized_pron": "".join(hyp),
        "errors": errors,
        "engine": "phonetic",
    }
