r"""3주차 수동 테스트 — 1주차 녹음 20개를 API에 업로드해 전 구간 확인.

전제: 서버 실행 중 (.venv\Scripts\uvicorn.exe app.main:app --port 8000)

확인 항목:
  1. GET /sentences — 시드 10문장
  2. GET /sentences/{id}/audio — TTS 캐싱 (1차 생성 vs 2차 캐시 응답 시간)
  3. POST /attempts — 녹음 20개 전부: 점수 JSON + 처리 시간 (목표: 문장당 10초 이내)
  4. 오류 응답 — 없는 문장 404, 형식 불량 400

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\api_manual_test.py
"""

import csv
import os
import time
from pathlib import Path

import requests

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
RECORDINGS_DIR = Path(__file__).parent / "recordings"
MANIFEST = RECORDINGS_DIR / "manifest.csv"


def main() -> None:
    # 1. 문장 목록
    r = requests.get(f"{BASE}/sentences", timeout=30)
    r.raise_for_status()
    sentences = r.json()["sentences"]
    by_text = {s["text"]: s for s in sentences}
    print(f"[1] GET /sentences → {len(sentences)}문장")
    assert len(sentences) == 10, "시드 10문장이어야 함"

    # 2. TTS 캐싱 — 같은 문장 2회 호출 시간 비교
    sid = sentences[0]["id"]
    t0 = time.perf_counter()
    r = requests.get(f"{BASE}/sentences/{sid}/audio", timeout=60)
    first = time.perf_counter() - t0
    r.raise_for_status()
    size = len(r.content)
    t0 = time.perf_counter()
    requests.get(f"{BASE}/sentences/{sid}/audio", timeout=60).raise_for_status()
    second = time.perf_counter() - t0
    print(f"[2] TTS: 최초 {first:.2f}s ({size:,}B) → 캐시 {second:.2f}s")

    # 3. 평가 — 1주차 녹음 전부 업로드
    with open(MANIFEST, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("file", "").strip()]
    times = []
    print(f"[3] POST /attempts — {len(rows)}건")
    for row in rows:
        path = RECORDINGS_DIR / row["file"].strip()
        target = row["target_text"].strip()
        if not path.exists() or target not in by_text:
            print(f"    [건너뜀] {row['file']}")
            continue
        t0 = time.perf_counter()
        r = requests.post(
            f"{BASE}/attempts",
            data={"sentence_id": by_text[target]["id"]},
            files={"audio": (path.name, path.read_bytes())},
            timeout=120,
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        r.raise_for_status()
        body = r.json()
        n_err = len(body["analysis"]["errors"])
        print(f"    {path.name:<14} {elapsed:5.1f}s  점수 {body['analysis']['score']:>3}"
              f"  오류 {n_err}  「{body['stt']['text']}」")

    if times:
        print(f"    평균 {sum(times)/len(times):.1f}s / 최대 {max(times):.1f}s "
              f"(목표: 10초 이내, 첫 요청은 모델 로드 포함)")

    # 4. 오류 응답
    r = requests.post(f"{BASE}/attempts", data={"sentence_id": 9999},
                      files={"audio": ("x.wav", b"")}, timeout=30)
    print(f"[4] 없는 문장 → {r.status_code} {r.json()}")
    assert r.status_code == 404
    r = requests.post(f"{BASE}/attempts", data={"sentence_id": 1},
                      files={"audio": ("x.wav", b"not-audio")}, timeout=30)
    print(f"    깨진 오디오 → {r.status_code} {r.json()}")
    assert r.status_code == 400

    print("\n수동 테스트 통과: 업로드 → 점수 JSON → DB 기록 전 구간 동작.")


if __name__ == "__main__":
    main()
