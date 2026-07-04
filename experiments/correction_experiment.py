r"""핵심 실험 — Whisper 교정 문제 검증 (1주차 최대 리스크 확인).

질문: 의도적으로 틀리게 발음한 녹음을 Whisper가 '틀린 대로' 인식하는가,
      아니면 똑똑하게 '맞는 텍스트로 교정'해버리는가?

준비:
  1. experiments\recordings\ 에 녹음 파일(wav/mp3/m4a 등)을 넣는다.
  2. experiments\recordings\manifest.csv 에 한 줄씩 기록한다:
       file,target_text,intended_text,note
     - target_text  : 화면에 제시된 정답 문장 (표기)
     - intended_text: 실제로 발음한 내용. 정상 발음 녹음이면 target_text와 동일하게 적는다.
       (예: target "밥"을 [받]으로 발음했으면 intended_text에 "받")
     - note         : 자유 메모 (어떤 오류를 의도했는지)

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\correction_experiment.py
    .venv\Scripts\python.exe experiments\correction_experiment.py --models small,medium --temperatures 0.0,0.6

결과:
    experiments\results\correction_results.md   (설정별 표 + 요약)
    experiments\results\correction_results.csv  (원자료)
"""

import argparse
import csv
import re
import time
from pathlib import Path

from stt_check import transcribe

BASE = Path(__file__).parent
RECORDINGS_DIR = BASE / "recordings"
MANIFEST = RECORDINGS_DIR / "manifest.csv"
RESULTS_DIR = BASE / "results"

_PUNCT_RE = re.compile(r"[\s.,!?~'\"“”‘’·…\-]+")


def normalize(text: str) -> str:
    """공백·문장부호를 제거해 발음 텍스트만 비교."""
    return _PUNCT_RE.sub("", text)


def judge(recognized: str, target: str, intended: str) -> str:
    """인식 결과 자동 판정.

    - 정상 발음 녹음(intended == target):
        '정확 인식' / '오인식'
    - 의도적 오발음 녹음(intended != target):
        '틀린 대로 인식' (우리가 원하는 결과 — 평가 가능)
        '교정됨'        (Whisper가 정답으로 고쳐버림 — 리스크 현실화)
        '기타'          (둘 다 아님 — 표를 보고 사람이 판단)
    """
    r, t, i = normalize(recognized), normalize(target), normalize(intended)
    if i == t:  # 정상 발음 케이스
        return "정확 인식" if r == t else "오인식"
    if r == i:
        return "틀린 대로 인식"
    if r == t:
        return "교정됨"
    return "기타"


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        raise SystemExit(
            f"[오류] {MANIFEST} 가 없습니다.\n"
            "recordings 폴더에 녹음을 넣고 manifest.csv를 작성하세요 (파일 상단 주석 참고)."
        )
    with open(MANIFEST, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("file", "").strip()]
    if not rows:
        raise SystemExit("[오류] manifest.csv에 데이터 행이 없습니다.")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper 교정 문제 실험")
    parser.add_argument("--models", default="small,medium")
    parser.add_argument("--temperatures", default="0.0,0.6")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    temps = [float(t) for t in args.temperatures.split(",") if t.strip()]
    configs = [(m, t) for m in models for t in temps]

    rows = load_manifest()
    RESULTS_DIR.mkdir(exist_ok=True)

    records = []
    for row in rows:
        audio = RECORDINGS_DIR / row["file"].strip()
        if not audio.exists():
            print(f"[건너뜀] 파일 없음: {audio}")
            continue
        target = row["target_text"].strip()
        intended = (row.get("intended_text") or "").strip() or target
        print(f"\n=== {audio.name}  (정답: {target} / 발음: {intended}) ===")
        for model_name, temp in configs:
            r = transcribe(str(audio), model_name=model_name, temperature=temp)
            verdict = judge(r["text"], target, intended)
            print(f"[{model_name:>7} t={temp}] ({r['elapsed_sec']:5.1f}s) "
                  f"{r['text']}  →  {verdict}")
            records.append({
                "file": audio.name,
                "target_text": target,
                "intended_text": intended,
                "model": model_name,
                "temperature": temp,
                "recognized": r["text"],
                "elapsed_sec": round(r["elapsed_sec"], 1),
                "verdict": verdict,
                "note": (row.get("note") or "").strip(),
            })

    if not records:
        raise SystemExit("[오류] 처리된 녹음이 없습니다.")

    # CSV 저장
    csv_path = RESULTS_DIR / "correction_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    # 마크다운 저장
    md_path = RESULTS_DIR / "correction_results.md"
    lines = [
        "# Whisper 교정 실험 결과 (자동 생성)",
        "",
        f"- 생성 시각: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- 설정: models={models}, temperatures={temps}",
        "",
        "| 파일 | 정답(표기) | 의도 발음 | 모델 | temp | 인식 결과 | 판정 | 시간(s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['file']} | {r['target_text']} | {r['intended_text']} "
            f"| {r['model']} | {r['temperature']} | {r['recognized']} "
            f"| **{r['verdict']}** | {r['elapsed_sec']} |"
        )

    # 설정별 요약 — 의도적 오발음 케이스만 대상으로 '틀린 대로 인식' 비율 계산
    lines += ["", "## 설정별 요약 (의도적 오발음 케이스만)", "",
              "| 모델 | temp | 틀린 대로 인식 | 교정됨 | 기타 | 평가 가능 비율 |",
              "|---|---|---|---|---|---|"]
    for model_name, temp in configs:
        subset = [r for r in records
                  if r["model"] == model_name and r["temperature"] == temp
                  and normalize(r["intended_text"]) != normalize(r["target_text"])]
        if not subset:
            continue
        kept = sum(1 for r in subset if r["verdict"] == "틀린 대로 인식")
        fixed = sum(1 for r in subset if r["verdict"] == "교정됨")
        other = len(subset) - kept - fixed
        lines.append(f"| {model_name} | {temp} | {kept} | {fixed} | {other} "
                     f"| {kept}/{len(subset)} ({kept / len(subset) * 100:.0f}%) |")

    lines += ["", "> 판정 기준: '틀린 대로 인식' 비율이 대략 50% 이상이면 Whisper small로 진행,",
              "> 대부분 '교정됨'이면 2주차에 wav2vec2 계열 음소 인식 검증을 추가한다 (세부계획 1주차 결정 포인트).", ""]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[저장] {md_path}")
    print(f"[저장] {csv_path}")
    print("결과 표를 experiments\\whisper_교정실험.md 의 해당 섹션에 옮겨 붙이고 결정을 기록할 것.")


if __name__ == "__main__":
    main()
