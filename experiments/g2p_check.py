r"""g2p 검증 스크립트 (2주차 준비).

g2pk가 표기 문장 → 발음형 변환을 제대로 하는지 확인한다.
1주차 실험 문장 기준으로 기대 발음형과 대조한다.

전제: C:\mecab 에 mecab-ko(mecab-ko-msvc) 설치 — experiments\README.md '알려진 이슈' 참고.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\g2p_check.py
"""

from g2pk import G2p

# (표기, 기대 발음형, 검증하는 규칙)
CASES = [
    ("국물이 정말 시원하다", "궁무리 정말 시원하다", "비음화 + 연음"),
    ("밥을 먹었다", "바블 머걷따", "연음 + 받침 대표음 + 경음화"),
    ("신라면이 맵다", "실라며니 맵따", "유음화 + 연음 + 경음화"),
    ("좋다고 말했다", "조타고 말핻따", "격음화 + 경음화"),
    ("학교에 갔다", "학꾜에 갇따", "경음화"),
    ("옷이 예쁘다", "오시 예쁘다", "연음"),
    ("읽고 다시 말했다", "일꼬 다시 말핻따", "겹받침 + 경음화"),
    ("같이 갑시다", "가치 갑씨다", "구개음화 + 경음화"),
]


def main() -> None:
    g2p = G2p()
    ok = 0
    print(f"{'표기':<20} {'변환 결과':<20} {'기대':<20} 판정")
    print("-" * 80)
    for text, expected, rule in CASES:
        got = g2p(text)
        match = "O" if got == expected else "X"
        ok += got == expected
        print(f"{text:<20} {got:<20} {expected:<20} {match}  ({rule})")
    print("-" * 80)
    print(f"{ok}/{len(CASES)} 일치. 불일치 항목은 기대값이 틀렸을 수도 있으니 국어 규범 기준으로 직접 판단할 것.")


if __name__ == "__main__":
    main()
