r"""wav2vec2 CTC 음소/문자 인식 검증 (2주차 — 1주차 결정 포인트의 후속).

질문: 언어모델 없는 CTC 인식기는 Whisper가 못 보는 오류를 보는가?
  - 합격 기준: 발음규칙 미적용형(wrong_01/03/05)이 정상 발음과 다르게 인식되는가
  - 대조군: Whisper small t=0.0 — 자모 대체형 4/7, 규칙 미적용형 0/3

1주차 녹음 20개(recordings\manifest.csv)를 동일 벤치마크로 사용한다.

실행 (CMD, 프로젝트 루트에서):
    .venv\Scripts\python.exe experiments\wav2vec2_check.py
    .venv\Scripts\python.exe experiments\wav2vec2_check.py --model facebook/wav2vec2-lv-60-espeak-cv-ft

결과: experiments\results\wav2vec2_<모델명>.md / .csv
"""

import argparse
import csv
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import torch
from transformers import AutoModelForCTC, AutoProcessor
from whisper.audio import load_audio  # ffmpeg 기반 16kHz mono float32 로더 재사용

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import compare  # noqa: E402

BASE = Path(__file__).parent
RECORDINGS_DIR = BASE / "recordings"
MANIFEST = RECORDINGS_DIR / "manifest.csv"
RESULTS_DIR = BASE / "results"

DEFAULT_MODEL = "kresnik/wav2vec2-large-xlsr-korean"

_PUNCT_RE = re.compile(r"[\s.,!?~'\"“”‘’·…\-|]+")


def norm(text: str) -> str:
    return _PUNCT_RE.sub("", text)


def is_hangul_output(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def judge(recognized: str, target: str, intended: str) -> tuple[str, int]:
    """발음형 공간 판정 + 정답 대비 엔진 점수.

    CTC 출력은 발음형에 가깝다고 가정하고 recognized_is_phonetic=True로 비교한다.
    """
    if not is_hangul_output(recognized):
        return "-", -1  # IPA 등 비한글 출력은 표만 기록, 사람이 해석

    from engine.g2p import to_pronunciation
    r = norm(recognized)
    t = norm(to_pronunciation(target))
    i = norm(to_pronunciation(intended))
    score = compare(target, recognized, recognized_is_phonetic=True)["score"]

    if r == t:
        return ("정확 인식" if i == t else "교정됨"), score
    if i != t and r == i:
        return "틀린 대로 인식", score
    return "기타", score


def main() -> None:
    parser = argparse.ArgumentParser(description="wav2vec2 CTC 인식 검증")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    with open(MANIFEST, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("file", "").strip()]

    print(f"[모델 로드] {args.model} ...", flush=True)
    t0 = time.perf_counter()
    processor = AutoProcessor.from_pretrained(args.model)
    model = AutoModelForCTC.from_pretrained(args.model)
    model.eval()
    print(f"완료 ({time.perf_counter() - t0:.1f}s)", flush=True)

    records = []
    outputs: dict[str, str] = {}  # file → 인식 결과 (정상/오발음 쌍 비교용)
    for row in rows:
        audio_path = RECORDINGS_DIR / row["file"].strip()
        if not audio_path.exists():
            print(f"[건너뜀] 파일 없음: {audio_path}")
            continue
        target = row["target_text"].strip()
        intended = (row.get("intended_text") or "").strip() or target

        audio = load_audio(str(audio_path))
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            logits = model(**inputs).logits
        ids = torch.argmax(logits, dim=-1)
        text = processor.batch_decode(ids)[0].strip()
        elapsed = time.perf_counter() - t0

        verdict, score = judge(text, target, intended)
        outputs[row["file"].strip()] = text
        print(f"[{audio_path.name}] ({elapsed:4.1f}s) {text}  →  {verdict}"
              + (f" (점수 {score})" if score >= 0 else ""), flush=True)
        records.append({
            "file": audio_path.name,
            "target_text": target,
            "intended_text": intended,
            "recognized": text,
            "score_vs_target": score,
            "verdict": verdict,
            "elapsed_sec": round(elapsed, 1),
            "note": (row.get("note") or "").strip(),
        })

    if not records:
        raise SystemExit("[오류] 처리된 녹음이 없습니다.")

    # 정상/오발음 쌍 비교 — 규칙 미적용형 감지의 핵심 지표.
    # 같은 목표 문장의 normal_XX vs wrong_XX 출력이 '다르면' 모델이 차이를 들은 것.
    pair_lines = []
    for f, text in outputs.items():
        if not f.startswith("wrong_"):
            continue
        counterpart = f.replace("wrong_", "normal_")
        if counterpart not in outputs:
            continue
        a, b = norm(outputs[counterpart]), norm(text)
        ratio = SequenceMatcher(None, a, b).ratio()
        pair_lines.append(
            f"| {counterpart} vs {f} | {outputs[counterpart]} | {text} "
            f"| {'다름 ✅' if a != b else '동일 ⚠️'} | {ratio:.2f} |"
        )

    model_slug = args.model.replace("/", "_")
    RESULTS_DIR.mkdir(exist_ok=True)

    csv_path = RESULTS_DIR / f"wav2vec2_{model_slug}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    md_lines = [
        f"# wav2vec2 검증 결과 — `{args.model}` (자동 생성)",
        "",
        f"- 생성 시각: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| 파일 | 정답(표기) | 의도 발음 | 인식 결과 | 판정 | 점수 | 시간(s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        score = r["score_vs_target"] if r["score_vs_target"] >= 0 else "-"
        md_lines.append(
            f"| {r['file']} | {r['target_text']} | {r['intended_text']} "
            f"| {r['recognized']} | **{r['verdict']}** | {score} | {r['elapsed_sec']} |"
        )
    md_lines += [
        "",
        "## 정상/오발음 쌍 비교 (규칙 미적용형 감지 지표)",
        "",
        "같은 문장의 정상 발음과 오발음 출력이 **달라야** 모델이 그 차이를 들은 것이다.",
        "특히 wrong_01/03/05(비음화·유음화·경음화 무시)가 Whisper에서는 전부 '동일'이었다.",
        "",
        "| 쌍 | 정상 출력 | 오발음 출력 | 판정 | 유사도 |",
        "|---|---|---|---|---|",
        *pair_lines,
        "",
        "> 대조군(Whisper small t=0.0): 자모 대체형 4/7 보존, 규칙 미적용형 0/3.",
    ]
    md_path = RESULTS_DIR / f"wav2vec2_{model_slug}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n[저장] {md_path}\n[저장] {csv_path}")


if __name__ == "__main__":
    main()
