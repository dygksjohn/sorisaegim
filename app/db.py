"""SQLite 스키마 + 시드.

시드 10문장 = 1주차 실험 문장과 동일 (수동 테스트에서 1주차 녹음을 그대로 재사용하기 위함).
5주차에 유형별 30문장으로 확장한다.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"
TTS_CACHE_DIR = DATA_DIR / "tts_cache"
UPLOADS_DIR = DATA_DIR / "uploads"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sentences (
    id         INTEGER PRIMARY KEY,
    text       TEXT NOT NULL UNIQUE,
    pron       TEXT NOT NULL,          -- g2pk 발음형 (시드 시점 계산)
    type       TEXT NOT NULL,          -- 발음 규칙 유형 태그
    difficulty INTEGER NOT NULL        -- 1~3
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id),
    audio_path  TEXT NOT NULL,         -- 녹음 원본 보관 (7주차 ML 데이터)
    stt_engine  TEXT NOT NULL,
    stt_text    TEXT NOT NULL,
    score       INTEGER NOT NULL,
    errors_json TEXT NOT NULL,         -- 엔진 오류 리포트 (JSON)
    created_at  TEXT NOT NULL          -- ISO 8601 (KST)
);
"""

# (문장, 유형, 난이도) — 발음형은 시드 시 g2pk로 계산
SEED_SENTENCES = [
    ("국물이 정말 시원하다", "비음화", 1),
    ("밥을 먹었다", "연음", 1),
    ("신라면이 맵다", "유음화", 2),
    ("좋다고 말했다", "격음화", 2),
    ("학교에 갔다", "경음화", 1),
    ("옷이 예쁘다", "연음", 1),
    ("어머니가 오셨다", "종합", 1),
    ("라디오를 켰다", "종합", 1),
    ("읽고 다시 말했다", "겹받침", 2),
    ("같이 갑시다", "구개음화", 2),
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    for d in (DATA_DIR, TTS_CACHE_DIR, UPLOADS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        if count == 0:
            from engine import to_pronunciation
            conn.executemany(
                "INSERT INTO sentences (text, pron, type, difficulty) VALUES (?, ?, ?, ?)",
                [(t, to_pronunciation(t), ty, d) for t, ty, d in SEED_SENTENCES],
            )
        conn.commit()
    finally:
        conn.close()
