"""표기 → 표준 발음형 변환 (g2pk 래퍼).

g2pk는 초기화가 느리므로 모듈 수준에서 1회만 생성한다.
g2pk가 없는 환경(해커톤 이식 등)에서는 use_g2p=False 경로로 엔진이 동작하도록
임포트를 지연시킨다.
"""

from functools import lru_cache

_g2p = None


def _get_g2p():
    global _g2p
    if _g2p is None:
        from g2pk import G2p  # 지연 임포트 — 설치 안 된 환경 보호
        _g2p = G2p()
    return _g2p


@lru_cache(maxsize=4096)
def to_pronunciation(text: str) -> str:
    """표기 문장 → 표준 발음 문장. 예: '국물이 좋다' → '궁무리 조타'.

    같은 문장 세트가 반복 평가되므로 캐싱한다.
    """
    return _get_g2p()(text)
