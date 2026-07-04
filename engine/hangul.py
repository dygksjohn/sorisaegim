"""한글 자모 분해.

음절을 초성/중성/종성 토큰으로 분해한다. 종성이 없어도 빈 토큰('')을
명시적으로 만들어, 모든 한글 음절이 정확히 3개 토큰이 되도록 한다
(정렬 안정성 + 토큰 위치 → 음절 역산이 쉬워짐).

외부 라이브러리 없이 유니코드 산술로 처리한다.
"""

from dataclasses import dataclass

CHOSEONG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]
JUNGSEONG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
]
JONGSEONG = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

HANGUL_BASE = 0xAC00
HANGUL_END = 0xD7A3

# 토큰의 component 값
CHO, JUNG, JONG = "choseong", "jungseong", "jongseong"
CHAR = "char"  # 한글 음절이 아닌 문자 (숫자, 라틴 등)


@dataclass(frozen=True)
class JamoToken:
    """자모 하나. syllable_index는 원문에서 몇 번째 음절(공백 제외)인지."""

    jamo: str            # 'ㄱ', 'ㅏ', '' (빈 종성) 등
    component: str       # choseong | jungseong | jongseong | char
    syllable_index: int  # 소속 음절 위치
    syllable: str        # 소속 음절 문자 (하이라이트용)


def is_hangul_syllable(ch: str) -> bool:
    return HANGUL_BASE <= ord(ch) <= HANGUL_END


def decompose_syllable(ch: str) -> tuple[str, str, str]:
    """음절 하나 → (초성, 중성, 종성). 종성 없으면 ''."""
    code = ord(ch) - HANGUL_BASE
    cho, rest = divmod(code, 21 * 28)
    jung, jong = divmod(rest, 28)
    return CHOSEONG[cho], JUNGSEONG[jung], JONGSEONG[jong]


def decompose_text(text: str) -> list[JamoToken]:
    """문장 → 자모 토큰 시퀀스. 공백·문장부호는 버린다.

    한글 음절은 (초, 중, 종) 3토큰, 그 외 문자는 1토큰(component='char').
    """
    tokens: list[JamoToken] = []
    idx = 0
    for ch in text:
        if ch.isspace() or ch in ".,!?~‘’“”'\"·…-":
            continue
        if is_hangul_syllable(ch):
            cho, jung, jong = decompose_syllable(ch)
            tokens.append(JamoToken(cho, CHO, idx, ch))
            tokens.append(JamoToken(jung, JUNG, idx, ch))
            tokens.append(JamoToken(jong, JONG, idx, ch))
        else:
            tokens.append(JamoToken(ch, CHAR, idx, ch))
        idx += 1
    return tokens
