r"""발음형(평면 자모) 비교 테스트 — engine.phonetic (음소 인식기 경로).

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe -m pytest tests/test_phonetic.py -v

g2p(g2pk+C:\mecab) 필요 — 없으면 전체 skip.
"""

import pytest

from engine.hangul import CHO, JONG, JUNG

try:
    from engine.g2p import to_pronunciation
    to_pronunciation("가")
    HAS_G2P = True
except Exception:
    HAS_G2P = False

from engine.phonetic import compare_phonetic, phones_to_jamo, ref_flat_tokens

pytestmark = pytest.mark.skipif(not HAS_G2P, reason="g2pk 미설치 환경")


def jamo_str(text_pron_syllables: str) -> str:
    """테스트 편의: 발음형 음절 문자열을 phones 규약 평면 자모로."""
    return "".join(t.jamo for t in ref_flat_tokens(text_pron_syllables))


class TestRefFlatTokens:
    def test_drops_onset_ieung(self):
        # "야" = ㅇㅑ → 초성 ㅇ 제외 → ㅑ 하나
        toks = ref_flat_tokens("야")
        assert [t.jamo for t in toks] == ["ㅑ"]

    def test_keeps_coda_ieung(self):
        # "강" = ㄱㅏㅇ → 받침 ㅇ 유지
        toks = ref_flat_tokens("강")
        assert [t.jamo for t in toks] == ["ㄱ", "ㅏ", "ㅇ"]
        assert toks[2].component == JONG

    def test_splits_composite_jong(self):
        # "값" = ㄱㅏㅄ → ㅂㅅ 분해, 둘 다 종성·같은 음절
        toks = ref_flat_tokens("값")
        assert [t.jamo for t in toks] == ["ㄱ", "ㅏ", "ㅂ", "ㅅ"]
        assert toks[2].component == JONG and toks[3].component == JONG
        assert toks[2].syllable_index == toks[3].syllable_index


class TestPhonesToJamo:
    def test_strips_spn_and_space(self):
        assert phones_to_jamo("ㄱㅗ spn ㅈㅓ") == ["ㄱ", "ㅗ", "ㅈ", "ㅓ"]


class TestComparePhonetic:
    def test_perfect_match_scores_100(self):
        # "밥을" 발음형 = 바블 → ㅂㅏㅂㅡㄹ
        phones = jamo_str(to_pronunciation("밥을"))
        res = compare_phonetic("밥을", phones)
        assert res["score"] == 100
        assert res["errors"] == []

    def test_no_g2p_reapplication(self):
        # 음소 인식기가 [궁무리]로 냈으면 그대로 비교 — g2p 재적용 없음.
        # 제시어 "국물이"의 기대 발음형과 일치해야 100.
        phones = jamo_str(to_pronunciation("국물이"))  # 궁무리
        res = compare_phonetic("국물이", phones)
        assert res["score"] == 100

    def test_jongseong_substitution_flagged(self):
        # 제시어 "밥" (발음형 밥=ㅂㅏㅂ) 를 받침 ㄷ으로 발음 → ㅂㅏㄷ
        res = compare_phonetic("밥", "ㅂㅏㄷ")
        assert res["score"] < 100
        jong_errs = [e for e in res["errors"] if e["component"] == JONG]
        assert len(jong_errs) == 1
        assert jong_errs[0]["expected"] == "ㅂ" and jong_errs[0]["actual"] == "ㄷ"

    def test_deletion_flagged(self):
        # 받침 탈락: "강" → "가"(ㄱㅏ)
        res = compare_phonetic("강", "ㄱㅏ")
        dels = [e for e in res["errors"] if e["type"] == "deletion"]
        assert len(dels) == 1
        assert dels[0]["component"] == JONG and dels[0]["expected"] == "ㅇ"

    def test_error_carries_syllable_for_highlight(self):
        # 두 번째 음절 오류 위치가 정확히 잡혀야 (UI 하이라이트용)
        res = compare_phonetic("바다", "ㅂㅏㄷㅓ")  # 다→더 (중성 오류)
        errs = [e for e in res["errors"] if e["type"] == "substitution"]
        assert errs and errs[0]["position"] == 1
        assert errs[0]["component"] == JUNG

    def test_empty_recognized(self):
        res = compare_phonetic("밥", "")
        assert res["score"] == 0
        assert all(e["type"] == "deletion" for e in res["errors"])

    def test_response_shape_matches_compare(self):
        res = compare_phonetic("밥을", jamo_str(to_pronunciation("밥을")))
        for key in ("score", "reference", "reference_pron", "recognized",
                    "recognized_pron", "errors"):
            assert key in res
