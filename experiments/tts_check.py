r"""TTS 검증 스크립트 (1주차).

문장을 Edge-TTS로 mp3 생성해 한국어 음질을 확인한다.
생성 파일은 experiments\tts_out\ 에 저장된다.

사용 예 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\tts_check.py
    .venv\Scripts\python.exe experiments\tts_check.py --text "국물이 정말 시원하다"
    .venv\Scripts\python.exe experiments\tts_check.py --voice ko-KR-InJoonNeural
"""

import argparse
import asyncio
from pathlib import Path

import edge_tts

OUT_DIR = Path(__file__).parent / "tts_out"

# 발음 규칙이 섞인 기본 검증 문장 (연음/경음화/비음화/받침)
DEFAULT_SENTENCES = [
    "국물이 정말 시원하다",      # 비음화: 국물 → [궁물]
    "밥을 먹고 학교에 갔다",     # 연음 + 경음화
    "옷이 젖어서 갈아입었다",    # 받침 대표음 + 연음
    "좋은 하루 보내세요",        # 격음화/축약
    "닭고기를 볶아 먹었다",      # 겹받침 + 경음화
]

# 한국어 보이스 후보: ko-KR-SunHiNeural(여), ko-KR-InJoonNeural(남), ko-KR-HyunsuMultilingualNeural(남)
DEFAULT_VOICE = "ko-KR-SunHiNeural"


async def synthesize(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
    print(f"[생성] {out_path}  ({out_path.stat().st_size:,} bytes)  \"{text}\"")


async def run(sentences: list[str], voice: str) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for i, text in enumerate(sentences, 1):
        out_path = OUT_DIR / f"tts_{voice}_{i:02d}.mp3"
        await synthesize(text, voice, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Edge-TTS 한국어 음질 검증")
    parser.add_argument("--text", help="단일 문장 지정 (없으면 기본 5문장)")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    args = parser.parse_args()

    sentences = [args.text] if args.text else DEFAULT_SENTENCES
    asyncio.run(run(sentences, args.voice))
    print(f"\n완료. {OUT_DIR} 폴더의 mp3를 직접 들어보고 음질을 판단할 것.")


if __name__ == "__main__":
    main()
