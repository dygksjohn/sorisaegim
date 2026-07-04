"""발음 비교 — 엔진의 진입점.

compare(정답 표기 문장, STT 인식 문장) → 점수 + 자모 단위 오류 리포트(dict).
반환 dict는 그대로 API 응답이 된다 (docs/api_spec.md).

핵심 원칙: 비교는 항상 **발음형 공간**에서 한다 (1주차 실험 결론).
표기 "밥을"과 인식 "바블"은 발음형이 같으므로 100점이어야 한다.
"""

from .align import DEL, INS, MATCH, SUB, align
from .hangul import decompose_text


def _errors_from_ops(ops) -> list[dict]:
    errors = []
    last_ref_syllable_index = 0
    for op in ops:
        if op.ref is not None:
            last_ref_syllable_index = op.ref.syllable_index
        if op.op == MATCH:
            continue
        if op.op == SUB:
            errors.append({
                "type": SUB,
                "position": op.ref.syllable_index,
                "syllable": op.ref.syllable,
                "component": op.ref.component,
                "expected": op.ref.jamo,
                "actual": op.hyp.jamo,
            })
        elif op.op == DEL:  # 정답에 있는 소리가 발화에서 빠짐
            errors.append({
                "type": DEL,
                "position": op.ref.syllable_index,
                "syllable": op.ref.syllable,
                "component": op.ref.component,
                "expected": op.ref.jamo,
                "actual": None,
            })
        else:  # INS — 발화에 잉여 소리. 위치는 직전 정답 음절에 귀속
            errors.append({
                "type": INS,
                "position": last_ref_syllable_index,
                "syllable": None,
                "component": op.hyp.component,
                "expected": None,
                "actual": op.hyp.jamo,
            })
    return errors


def compare(
    reference: str,
    recognized: str,
    *,
    use_g2p: bool = True,
    recognized_is_phonetic: bool = False,
) -> dict:
    """정답 문장 vs 인식 문장 자모 비교.

    Args:
        reference: 정답 문장 (표기). 예: "국물이 좋다"
        recognized: STT 인식 결과. 예: "궁무리 조타"
        use_g2p: True면 표준 발음형으로 변환 후 비교 (기본).
                 g2pk 없는 환경에서는 False로 표기끼리 직접 비교.
        recognized_is_phonetic: 인식 결과가 이미 발음형일 때 True.
            음소 인식기(wav2vec2 계열) 출력에 g2p를 다시 적용하면
            음운 규칙이 재적용되어 오류가 지워진다
            (예: [국무리]로 발음된 것이 g2p를 거치면 "궁무리"로 복원됨).
            Whisper처럼 표기를 출력하는 STT면 False(기본) 유지.

    Returns:
        {
          "score": 0~100 정수,
          "reference": 원문, "reference_pron": 비교에 쓴 발음형,
          "recognized": 원문, "recognized_pron": 비교에 쓴 발음형,
          "errors": [ {type, position, syllable, component, expected, actual}, ... ],
        }
        position은 reference_pron에서 공백 제외 음절 인덱스.
    """
    reference = (reference or "").strip()
    recognized = (recognized or "").strip()

    if use_g2p:
        from .g2p import to_pronunciation
        ref_pron = to_pronunciation(reference) if reference else ""
        if recognized_is_phonetic:
            rec_pron = recognized
        else:
            rec_pron = to_pronunciation(recognized) if recognized else ""
    else:
        ref_pron, rec_pron = reference, recognized

    ref_tokens = decompose_text(ref_pron)
    rec_tokens = decompose_text(rec_pron)

    ops = align(ref_tokens, rec_tokens)
    errors = _errors_from_ops(ops)

    distance = sum(1 for op in ops if op.op != MATCH)
    denom = max(len(ref_tokens), len(rec_tokens), 1)
    score = max(0, round(100 * (1 - distance / denom)))

    return {
        "score": score,
        "reference": reference,
        "reference_pron": ref_pron,
        "recognized": recognized,
        "recognized_pron": rec_pron,
        "errors": errors,
    }
