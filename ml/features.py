"""문장 특징 추출 — 학습(train.py)과 서빙(recommend.py)이 같은 코드를 쓴다.

특징 = 발음형의 자모 구성(bag-of-jamo) + 구조 통계 + 발음 규칙 유형 one-hot.
오류는 발음형 공간에서 일어나므로 표기가 아닌 발음형(pron)에서 뽑는다.
"""

from collections import Counter

from engine.hangul import (
    CHO, JONG, JUNG, CHOSEONG, JUNGSEONG, JONGSEONG, decompose_text,
)

SENTENCE_TYPES = [
    "비음화", "연음", "유음화", "격음화", "경음화",
    "구개음화", "겹받침", "받침대표음", "종합",
]
DOUBLE_JONG = {"ㄳ", "ㄵ", "ㄶ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅄ"}

# 빈 종성('')은 제외한 종성 목록
_JONG_NONEMPTY = [j for j in JONGSEONG if j]

LABELS = ["none", "choseong", "jungseong", "jongseong"]


def feature_names() -> list[str]:
    return (
        ["n_syllables", "n_jongseong", "n_double_jongseong"]
        + [f"cho_{c}" for c in CHOSEONG]
        + [f"jung_{v}" for v in JUNGSEONG]
        + [f"jong_{j}" for j in _JONG_NONEMPTY]
        + [f"type_{t}" for t in SENTENCE_TYPES]
    )


def sentence_features(pron: str, sentence_type: str) -> list[float]:
    """발음형 문장 + 유형 태그 → 특징 벡터 (feature_names() 순서)."""
    tokens = decompose_text(pron)
    cho = Counter(t.jamo for t in tokens if t.component == CHO)
    jung = Counter(t.jamo for t in tokens if t.component == JUNG)
    jong = Counter(t.jamo for t in tokens if t.component == JONG and t.jamo)

    n_syll = sum(1 for t in tokens if t.component == CHO)
    n_jong = sum(jong.values())
    n_double = sum(n for j, n in jong.items() if j in DOUBLE_JONG)

    vec: list[float] = [float(n_syll), float(n_jong), float(n_double)]
    vec += [float(cho.get(c, 0)) for c in CHOSEONG]
    vec += [float(jung.get(v, 0)) for v in JUNGSEONG]
    vec += [float(jong.get(j, 0)) for j in _JONG_NONEMPTY]
    vec += [1.0 if sentence_type == t else 0.0 for t in SENTENCE_TYPES]
    return vec


def dominant_error_component(errors: list[dict]) -> str:
    """시도의 오류 목록 → 지배적 오류 성분 라벨 (없으면 'none').

    char(비한글) 오류는 발음 평가 대상이 아니므로 제외.
    """
    counts = Counter(
        e["component"] for e in errors
        if e["component"] in ("choseong", "jungseong", "jongseong")
    )
    if not counts:
        return "none"
    return counts.most_common(1)[0][0]
