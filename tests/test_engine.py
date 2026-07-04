r"""발음 비교 엔진 단위 테스트.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe -m pytest tests -v

g2p 관련 테스트는 g2pk(+C:\mecab)가 있어야 돈다. 없으면 해당 테스트만 skip.
"""

import pytest

from engine.hangul import CHAR, CHO, JONG, JUNG, decompose_syllable, decompose_text
from engine.align import align
from engine.compare import compare

try:
    from engine.g2p import to_pronunciation
    to_pronunciation("가")
    HAS_G2P = True
except Exception:
    HAS_G2P = False

needs_g2p = pytest.mark.skipif(not HAS_G2P, reason="g2pk 미설치 환경")


# ---------- 자모 분해 ----------

class TestDecompose:
    def test_syllable_with_jongseong(self):
        assert decompose_syllable("밥") == ("ㅂ", "ㅏ", "ㅂ")

    def test_syllable_without_jongseong(self):
        assert decompose_syllable("바") == ("ㅂ", "ㅏ", "")

    def test_double_jongseong(self):
        assert decompose_syllable("읽") == ("ㅇ", "ㅣ", "ㄺ")

    def test_every_syllable_yields_three_tokens(self):
        tokens = decompose_text("바다")
        assert len(tokens) == 6
        assert [t.component for t in tokens] == [CHO, JUNG, JONG, CHO, JUNG, JONG]
        # 종성 없음도 명시적 빈 토큰
        assert tokens[2].jamo == "" and tokens[5].jamo == ""

    def test_spaces_and_punctuation_ignored(self):
        assert decompose_text("바 다.") == decompose_text("바다")

    def test_syllable_index_skips_spaces(self):
        tokens = decompose_text("가 나")
        assert tokens[0].syllable_index == 0
        assert tokens[3].syllable_index == 1
        assert tokens[3].syllable == "나"

    def test_non_hangul_char_is_single_token(self):
        tokens = decompose_text("1고")
        assert tokens[0].component == CHAR
        assert tokens[0].jamo == "1"
        assert len(tokens) == 4  # '1' 1개 + '고' 3개

    def test_empty_text(self):
        assert decompose_text("") == []


# ---------- 정렬 ----------

class TestAlign:
    def test_identical(self):
        a = decompose_text("바다")
        ops = align(a, decompose_text("바다"))
        assert all(op.op == "match" for op in ops)

    def test_single_substitution(self):
        ops = align(decompose_text("밥"), decompose_text("받"))
        subs = [op for op in ops if op.op == "substitution"]
        assert len(subs) == 1
        assert subs[0].ref.jamo == "ㅂ" and subs[0].hyp.jamo == "ㄷ"
        assert subs[0].ref.component == JONG

    def test_missing_syllable_is_three_deletions(self):
        ops = align(decompose_text("바다"), decompose_text("바"))
        dels = [op for op in ops if op.op == "deletion"]
        assert len(dels) == 3

    def test_extra_syllable_is_insertions(self):
        ops = align(decompose_text("바"), decompose_text("바다"))
        ins = [op for op in ops if op.op == "insertion"]
        assert len(ins) == 3

    def test_same_jamo_different_component_not_equal(self):
        # 초성 ㅇ(무음가) vs 종성 ㅇ(받침)은 다른 소리
        ops = align(decompose_text("아"), decompose_text("앙"))
        assert any(op.op != "match" for op in ops)


# ---------- 비교 (g2p 불필요 경로) ----------

class TestCompareNoG2p:
    def test_perfect_match_is_100(self):
        assert compare("바다", "바다", use_g2p=False)["score"] == 100

    def test_jongseong_error_detected(self):
        r = compare("밥", "받", use_g2p=False)
        assert r["score"] < 100
        assert len(r["errors"]) == 1
        e = r["errors"][0]
        assert e["component"] == JONG
        assert e["expected"] == "ㅂ" and e["actual"] == "ㄷ"
        assert e["position"] == 0 and e["syllable"] == "밥"

    def test_score_scales_with_error_count(self):
        one = compare("바다가 좋다", "바다가 조다", use_g2p=False)["score"]
        two = compare("바다가 좋다", "파도가 조다", use_g2p=False)["score"]
        assert two < one < 100

    def test_totally_different(self):
        r = compare("바다", "축구공", use_g2p=False)
        assert r["score"] < 50

    def test_empty_recognized_is_zero(self):
        r = compare("바다", "", use_g2p=False)
        assert r["score"] == 0
        assert all(e["type"] == "deletion" for e in r["errors"])

    def test_both_empty(self):
        assert compare("", "", use_g2p=False)["score"] == 100

    def test_punctuation_and_space_ignored(self):
        assert compare("바다", " 바 다. ", use_g2p=False)["score"] == 100

    def test_insertion_reported(self):
        r = compare("바다", "바다다", use_g2p=False)
        assert r["score"] < 100
        assert any(e["type"] == "insertion" for e in r["errors"])

    def test_error_position_in_second_syllable(self):
        r = compare("바다", "바도", use_g2p=False)
        assert r["errors"][0]["position"] == 1
        assert r["errors"][0]["syllable"] == "다"

    def test_score_never_negative(self):
        r = compare("가", "축구공이좋다바다", use_g2p=False)
        assert 0 <= r["score"] <= 100


# ---------- 비교 (발음형 공간 — 1주차 실험 케이스) ----------

@needs_g2p
class TestCompareWithG2p:
    def test_liaison_same_pronunciation_is_100(self):
        # 표기는 다르지만 발음이 같다 — 1주차 '기타' 케이스의 교훈
        assert compare("밥을 먹었다", "바블 먹었다")["score"] == 100

    def test_wrong02_jongseong_substitution(self):
        # 1주차 wrong_02: "받을"이라 발음 → Whisper "바들"
        r = compare("밥을 먹었다", "바들 먹었다")
        assert r["score"] < 100
        assert any(e["expected"] == "ㅂ" and e["actual"] == "ㄷ" for e in r["errors"])

    def test_nasalization_reference(self):
        r = compare("국물이 정말 시원하다", "궁무리 정말 시원하다")
        assert r["score"] == 100

    def test_rule_not_applied_hidden_by_default_g2p(self):
        # 알려진 한계(1주차 결론의 재확인): 인식 결과에 g2p를 적용하면
        # 비음화가 재적용되어 "국무리"가 "궁무리"로 복원 → 오류가 지워진다.
        # 이 유형의 감지는 음소 인식(wav2vec2) 경로의 몫이다.
        r = compare("국물이 정말 시원하다", "국무리 정말 시원하다")
        assert r["score"] == 100

    def test_rule_not_applied_detected_in_phonetic_mode(self):
        # 음소 인식기 출력(이미 발음형)은 recognized_is_phonetic=True로 비교
        r = compare(
            "국물이 정말 시원하다",
            "국무리 정말 시원하다",
            recognized_is_phonetic=True,
        )
        assert r["score"] < 100
        e = r["errors"][0]
        assert e["syllable"] == "궁" and e["expected"] == "ㅇ" and e["actual"] == "ㄱ"

    def test_phonetic_mode_no_false_error_on_correct_speech(self):
        # 규칙이 제대로 적용된 발화의 음소 출력은 감점 없어야 한다
        r = compare(
            "국물이 정말 시원하다",
            "궁무리 정말 시원하다",
            recognized_is_phonetic=True,
        )
        assert r["score"] == 100

    def test_aspiration(self):
        assert compare("좋다고 말했다", "조타고 말핻따")["score"] == 100

    def test_palatalization(self):
        assert compare("같이 갑시다", "가치 갑시다")["score"] == 100

    def test_reference_pron_exposed(self):
        r = compare("국물이 좋다", "궁무리 조타")
        assert r["reference_pron"].replace(" ", "") == "궁무리조타"
        assert r["score"] == 100
