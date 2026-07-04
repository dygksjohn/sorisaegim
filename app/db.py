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

# (문장, 유형, 난이도) — 발음형은 시드 시 g2pk로 계산.
# 유형 태그는 문장의 대표 규칙 1개. 숫자·외래어는 피한다 (Whisper 표기 변환 문제).
# 기존 문장의 순서·텍스트를 바꾸면 안 된다 — attempts가 id를 참조 (추가는 뒤에만).
SEED_SENTENCES = [
    # ---- 1~4주차 초기 10문장 ----
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
    # ---- 5주차 확장 (연음 +4 → 6) ----
    ("웃음이 절로 나온다", "연음", 1),
    ("구름이 하늘에 떠 있다", "연음", 1),
    ("꽃이 활짝 피었다", "연음", 1),
    ("얼음이 녹아 물이 되었다", "연음", 2),
    # ---- 경음화 +4 → 5 ----
    ("숙제를 먼저 끝냈다", "경음화", 1),
    ("책상 위에 책이 있다", "경음화", 2),
    ("국밥이 뜨겁다", "경음화", 2),
    ("약속 장소로 걸어갔다", "경음화", 2),
    # ---- 비음화 +4 → 5 ----
    ("박물관에 다녀왔다", "비음화", 1),
    ("앞마당에 눈이 쌓였다", "비음화", 2),
    ("겉모습만 보면 모른다", "비음화", 2),
    ("밥맛이 정말 좋다", "비음화", 2),
    # ---- 격음화 +3 → 4 ----
    ("축하 인사를 건넸다", "격음화", 1),
    ("입학을 축하한다", "격음화", 2),
    ("따뜻한 국을 먹었다", "격음화", 2),
    # ---- 받침 대표음 +5 ----
    ("낮잠을 잤다", "받침대표음", 1),
    ("낮과 밤이 다르다", "받침대표음", 2),
    ("숲 속은 시원하다", "받침대표음", 2),
    ("꽃다발을 받았다", "받침대표음", 2),
    ("빗소리가 들린다", "받침대표음", 2),
    # ---- 종합 (복합 규칙, 난이도 3) +3 ----
    ("부엌문을 닫았다", "종합", 3),
    ("값비싼 옷을 샀다", "종합", 3),
    ("닭고기를 볶아 먹었다", "종합", 3),
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
        # text UNIQUE + INSERT OR IGNORE → 재실행해도 기존 문장 id 불변, 새 문장만 추가
        existing = {r[0] for r in conn.execute("SELECT text FROM sentences")}
        new_rows = [s for s in SEED_SENTENCES if s[0] not in existing]
        if new_rows:
            from engine import to_pronunciation
            conn.executemany(
                "INSERT OR IGNORE INTO sentences (text, pron, type, difficulty)"
                " VALUES (?, ?, ?, ?)",
                [(t, to_pronunciation(t), ty, d) for t, ty, d in new_rows],
            )
        conn.commit()
    finally:
        conn.close()
