"""취약 발음 추천 (모델 2) — 학습된 오류 발생 예측 모델로 문장 랭킹.

점수 = P(오류 | 문장 특징)  ×  (1 + 0.5 × 취약자모 겹침 비율)
  - P(오류): ml.train [A]에서 학습한 이진 분류기 (실사용 데이터 기반)
  - 취약자모 보정: 사용자가 최근 자주 틀린 (성분, 자모)를 포함한 문장 가중
"""

import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np

from engine.hangul import decompose_text
from ml.features import sentence_features

MODEL_PATH = Path(__file__).parent.parent / "data" / "models" / "error_clf.joblib"
WEAK_BOOST = 0.5
_bundle = None


def _get_model():
    global _bundle
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


def model_available() -> bool:
    return MODEL_PATH.exists()


def _weak_jamo_counter(conn) -> Counter:
    weak: Counter = Counter()
    for (ej,) in conn.execute("SELECT errors_json FROM attempts WHERE source='user'"):
        for e in json.loads(ej):
            # 빈 종성('')은 음절 누락의 부산물이라 '취약 자모'로서 설명력이 없음 — 제외
            if e["component"] in ("choseong", "jungseong", "jongseong") and e["expected"]:
                weak[(e["component"], e["expected"])] += 1
    return weak


def recommend(conn, top: int = 3) -> list[dict]:
    """문장 추천 상위 top개. conn은 app.db.get_conn() 커넥션."""
    bundle = _get_model()
    sentences = conn.execute(
        "SELECT id, text, pron, type, difficulty FROM sentences"
    ).fetchall()
    weak = _weak_jamo_counter(conn)
    top_weak = {key for key, _ in weak.most_common(5)}

    X = np.array([sentence_features(s["pron"], s["type"]) for s in sentences])
    p_error = bundle["model"].predict_proba(X)[:, 1]

    items = []
    for s, p in zip(sentences, p_error):
        tokens = decompose_text(s["pron"])
        hits = [(t.component, t.jamo) for t in tokens if (t.component, t.jamo) in top_weak]
        overlap = len(hits) / max(len(tokens), 1)
        score = float(p) * (1 + WEAK_BOOST * overlap)
        reason_parts = [f"오류 확률 {p * 100:.0f}%"]
        if hits:
            comp_ko = {"choseong": "초성", "jungseong": "중성", "jongseong": "받침"}
            uniq = sorted({f"{comp_ko[c]} {j or '(없음)'}" for c, j in hits})
            reason_parts.append("취약 자모 포함: " + ", ".join(uniq[:3]))
        items.append({
            "id": s["id"], "text": s["text"], "pron": s["pron"],
            "type": s["type"], "difficulty": s["difficulty"],
            "score": round(score, 3),
            "reason": " · ".join(reason_parts),
        })
    items.sort(key=lambda x: -x["score"])
    return items[:top]
