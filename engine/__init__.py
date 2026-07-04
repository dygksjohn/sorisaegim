"""소리새김 발음 비교 엔진.

정답 문장과 STT 인식 문장을 자모(초/중/종성) 단위로 정렬·비교해
점수(0~100)와 오류 목록을 반환한다.

사용:
    from engine import compare
    result = compare("국물이 좋다", "궁무리 조타")
    result["score"], result["errors"]

의존성: 표준 발음 변환에만 g2pk 필요 (use_g2p=False면 없어도 동작 — 해커톤 재사용용).
"""

from .compare import compare
from .g2p import to_pronunciation
from .hangul import decompose_text, is_hangul_syllable

__all__ = ["compare", "to_pronunciation", "decompose_text", "is_hangul_syllable"]
