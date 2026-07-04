"""TTS 모듈 — Edge-TTS 래퍼 (1주차 검증: 무료, 한국어 음질 합격).

음원은 파일로 캐싱한다 — 문장 세트가 고정이라 문장당 1회만 생성된다.
"""

from pathlib import Path

import edge_tts

VOICE = "ko-KR-SunHiNeural"


async def get_or_create_audio(text: str, cache_path: Path) -> Path:
    """캐시가 있으면 그대로, 없으면 Edge-TTS로 생성 후 반환."""
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(cache_path))
    return cache_path
