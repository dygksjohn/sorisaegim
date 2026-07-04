r"""7주차 — ML 학습·평가 (docs/ml_report.md 의 근거 산출).

설계 노트 (중요): 처음 설계(합성으로 학습→실사용 평가)는 폐기했다.
합성 데이터의 오류 성분은 무작위 주입이라 문장 특징과 독립 — 배울 신호가 없다
(실험으로 확인: 다수클래스 대비 macro-F1 +0.07 수준). 수정된 설계:

  [A] 오류 발생 예측 (이진, 핵심 모델) — 실사용(user) 데이터 5-fold CV.
      문장 특징 → 이 문장에서 오류가 날 확률. /recommend가 사용.
  [B] 추천 품질 비교 — out-of-fold 확률로 문장 랭킹 vs 규칙 기반(취약 자모) 랭킹,
      정답 = 사용자가 실제로 틀린 문장. precision@5.
  [C] 오류 성분 다중분류 (실험 기록용) — synth 학습→user 평가. 부정적 결과와 원인을
      리포트에 남긴다.
  [D] 합성 데이터의 감지율 분석 — 주입한 혼동 쌍별로 시스템(Whisper+엔진)이
      얼마나 잡아내는가. 합성 데이터의 올바른 사용처.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe -m ml.train
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.db import get_conn
from ml.features import dominant_error_component, feature_names, sentence_features

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "data" / "models"
RESULTS_DIR = ROOT / "experiments" / "results"
SYNTH_LABELS = RESULTS_DIR / "synth_labels.csv"
SEED = 42


def load_attempts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT a.id, a.sentence_id, a.errors_json, a.source, s.pron, s.type"
        " FROM attempts a JOIN sentences s ON s.id = a.sentence_id ORDER BY a.id"
    ).fetchall()
    conn.close()
    data = []
    for r in rows:
        errors = json.loads(r["errors_json"])
        data.append({
            "attempt_id": r["id"], "sentence_id": r["sentence_id"],
            "source": r["source"], "pron": r["pron"], "type": r["type"],
            "features": sentence_features(r["pron"], r["type"]),
            "component": dominant_error_component(errors),
            "errors": errors,
        })
    return data


# ---------- [A] 오류 발생 예측 (이진, user 데이터 CV) ----------

def task_a_binary(user_rows: list[dict], results: dict):
    X = np.array([d["features"] for d in user_rows])
    y = np.array([0 if d["component"] == "none" else 1 for d in user_rows])
    print(f"\n[A] 오류 발생 예측 — user {len(y)}건 (오류 {int(y.sum())}건)")

    models = {
        "베이스라인(다수클래스)": DummyClassifier(strategy="most_frequent"),
        "로지스틱 회귀": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED)),
        "랜덤 포레스트": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=SEED),
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    results["task_a"] = {}
    for name, model in models.items():
        auc = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
        f1 = cross_val_score(model, X, y, cv=cv, scoring="f1")
        results["task_a"][name] = {
            "cv_roc_auc": round(float(auc.mean()), 3),
            "cv_roc_auc_std": round(float(auc.std()), 3),
            "cv_f1": round(float(f1.mean()), 3),
        }
        print(f"  {name:<14} CV AUC {auc.mean():.3f}±{auc.std():.3f}  F1 {f1.mean():.3f}")

    best_name = max((n for n in models if "베이스라인" not in n),
                    key=lambda n: results["task_a"][n]["cv_roc_auc"])
    best = models[best_name]
    # 추천 비교용 out-of-fold 확률 (in-sample 낙관 방지)
    oof_proba = cross_val_predict(best, X, y, cv=cv, method="predict_proba")[:, 1]
    best.fit(X, y)
    joblib.dump({"model": best, "feature_names": feature_names(), "task": "binary",
                 "name": best_name, "trained_on": "user"},
                MODELS_DIR / "error_clf.joblib")
    results["task_a"]["best_model"] = best_name
    print(f"  → 베스트 {best_name} 저장 (data/models/error_clf.joblib)")
    return oof_proba


# ---------- [B] 추천 품질 비교 (모델 vs 규칙 기반) ----------

def task_b_recommend(user_rows: list[dict], oof_proba, results: dict, k: int = 5):
    # 정답: 사용자가 한 번이라도 틀린 문장
    sent_error: dict[int, bool] = defaultdict(bool)
    sent_proba: dict[int, list] = defaultdict(list)
    for d, p in zip(user_rows, oof_proba):
        sent_error[d["sentence_id"]] |= d["component"] != "none"
        sent_proba[d["sentence_id"]].append(p)

    # 모델 랭킹: 문장별 평균 out-of-fold P(오류)
    model_rank = sorted(sent_proba, key=lambda s: -float(np.mean(sent_proba[s])))

    # 규칙 기반 랭킹: 취약 자모 TOP5(6주차 통계)를 포함한 문장 우선
    weak = Counter()
    for d in user_rows:
        for e in d["errors"]:
            if e["component"] in ("choseong", "jungseong", "jongseong"):
                weak[(e["component"], e["expected"] or "")] += 1
    top_weak = {key for key, _ in weak.most_common(5)}

    conn = get_conn()
    prons = dict(conn.execute("SELECT id, pron FROM sentences"))
    conn.close()
    from engine.hangul import decompose_text

    def rule_score(sid: int) -> int:
        return sum(1 for t in decompose_text(prons[sid])
                   if (t.component, t.jamo) in top_weak)

    rule_rank = sorted(sent_proba, key=lambda s: -rule_score(s))

    def precision_at_k(rank):
        top = rank[:k]
        return sum(1 for s in top if sent_error[s]) / len(top)

    base_rate = sum(sent_error.values()) / len(sent_error)
    results["task_b"] = {
        "n_sentences_attempted": len(sent_proba),
        "sentence_error_base_rate": round(base_rate, 3),
        f"precision_at_{k}_model": round(precision_at_k(model_rank), 3),
        f"precision_at_{k}_rule": round(precision_at_k(rule_rank), 3),
        "weak_top5": [f"{c}:{j or '(없음)'}" for (c, j) in
                      [key for key, _ in weak.most_common(5)]],
    }
    print(f"\n[B] 추천 품질 (precision@{k}, 기저율 {base_rate:.2f}): "
          f"모델 {results['task_b'][f'precision_at_{k}_model']} vs "
          f"규칙 {results['task_b'][f'precision_at_{k}_rule']}")


# ---------- [C] 성분 다중분류 (부정적 결과 기록) ----------

def task_c_multiclass(rows: list[dict], results: dict):
    Xtr = np.array([d["features"] for d in rows if d["source"] == "synth"])
    ytr = np.array([d["component"] for d in rows if d["source"] == "synth"])
    Xev = np.array([d["features"] for d in rows if d["source"] == "user"])
    yev = np.array([d["component"] for d in rows if d["source"] == "user"])
    dummy = DummyClassifier(strategy="most_frequent").fit(Xtr, ytr)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                random_state=SEED).fit(Xtr, ytr)
    results["task_c"] = {
        "baseline_f1_macro": round(float(f1_score(
            yev, dummy.predict(Xev), average="macro", zero_division=0)), 3),
        "rf_f1_macro": round(float(f1_score(
            yev, rf.predict(Xev), average="macro", zero_division=0)), 3),
        "note": "합성 라벨은 무작위 주입이라 문장 특징과 독립 — 학습 신호 없음(설계 교훈)",
    }
    print(f"\n[C] 성분 다중분류(synth→user, 실험 기록): "
          f"베이스라인 {results['task_c']['baseline_f1_macro']} vs "
          f"RF {results['task_c']['rf_f1_macro']}")


# ---------- [D] 합성 감지율 분석 ----------

def task_d_detection(rows: list[dict], results: dict):
    if not SYNTH_LABELS.exists():
        print("[D] synth_labels.csv 없음 — 건너뜀")
        return
    by_id = {d["attempt_id"]: d for d in rows}
    with open(SYNTH_LABELS, encoding="utf-8-sig") as f:
        labels = [r for r in csv.DictReader(f) if r["kind"] == "perturbed"]

    comp_stat: dict[str, list] = defaultdict(lambda: [0, 0])  # [감지, 전체]
    pair_stat: dict[tuple, list] = defaultdict(lambda: [0, 0])
    for lb in labels:
        att = by_id.get(int(lb["attempt_id"]))
        if att is None:
            continue
        detected = any(e["component"] == lb["component"] for e in att["errors"])
        comp_stat[lb["component"]][1] += 1
        pair_stat[(lb["component"], lb["from"], lb["to"])][1] += 1
        if detected:
            comp_stat[lb["component"]][0] += 1
            pair_stat[(lb["component"], lb["from"], lb["to"])][0] += 1

    results["task_d"] = {
        "per_component": {
            c: {"detected": d, "total": t, "rate": round(d / t, 2)}
            for c, (d, t) in sorted(comp_stat.items())
        },
        "hardest_pairs": [
            {"component": c, "from": fr, "to": to, "detected": d, "total": t}
            for (c, fr, to), (d, t) in sorted(pair_stat.items(), key=lambda x: x[1][0] / x[1][1])
            if t >= 2
        ][:8],
    }
    print("\n[D] 주입 오류 감지율 (성분별):")
    for c, s in results["task_d"]["per_component"].items():
        print(f"  {c:<10} {s['detected']}/{s['total']} ({s['rate'] * 100:.0f}%)")


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = load_attempts()
    user_rows = [d for d in rows if d["source"] == "user"]
    results: dict = {"n_user": len(user_rows),
                     "n_synth": len(rows) - len(user_rows)}

    oof = task_a_binary(user_rows, results)
    task_b_recommend(user_rows, oof, results)
    task_c_multiclass(rows, results)
    task_d_detection(rows, results)

    with open(RESULTS_DIR / "ml_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] {RESULTS_DIR / 'ml_metrics.json'}")


if __name__ == "__main__":
    main()
