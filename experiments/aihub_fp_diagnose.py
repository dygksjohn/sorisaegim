r"""정발음 대조군 오탐 원인 진단 — 작업 3b 부속.

정발음(오류 태그 없는) 레코드에서 엔진이 오류를 플래그한 경우, 그 원인이
g2pk 기대발음 오류인지 / Whisper 오인식인지 / 실제 미세 발음인지 판별한다.
phones 정본(사람 전사)과 대조하면 판별된다: phones가 정답발음과 같은데도
엔진이 오류를 냈다면 → Whisper 오인식이 원인(가짜 감지).

산출: 콘솔 + results\aihub_fp_diagnose.md. 서버 불필요.
실행: .venv\Scripts\python.exe experiments\aihub_fp_diagnose.py [--n 30]
"""

import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import stt  # noqa: E402
from engine import compare, to_pronunciation  # noqa: E402
from ml.aihub import iter_records, prompt_to_flat_jamo, phones_to_flat_jamo  # noqa: E402

RESULTS = Path(__file__).parent / "results"
REPORT = RESULTS / "aihub_fp_diagnose.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="진단할 오탐 건수")
    args = ap.parse_args()

    control = [r for r in iter_records() if r.wav_path and not r.error_tags]
    control = sorted(control, key=lambda r: (r.region, r.user_id))

    whisper_cause = phones_diverge = 0
    cases = []
    for r in control[::7]:  # 결정적 표집
        stt_text = stt.transcribe(str(r.wav_path))["text"]
        res = compare(r.prompt, stt_text)
        if not res["errors"]:
            continue
        # phones 정본이 g2pk 기대발음과 (거의) 같으면 화자는 정발음 → 오탐은 Whisper 탓
        exp_flat = prompt_to_flat_jamo(r.prompt)
        pho_flat = phones_to_flat_jamo(r.phones)
        speaker_ok = exp_flat == pho_flat
        if speaker_ok:
            whisper_cause += 1
        else:
            phones_diverge += 1
        cases.append((r.prompt, to_pronunciation(r.prompt), stt_text, r.phones,
                      len(res["errors"]), res["score"], speaker_ok))
        if len(cases) >= args.n:
            break

    n = len(cases)
    wc_pct = whisper_cause / n * 100 if n else 0
    lines = ["# 정발음 오탐 원인 진단 (작업 3b 부속)\n"]
    lines.append(f"> 정발음인데 엔진이 오류를 낸 {n}건 분석. "
                 f"phones 정본이 기대발음과 일치하면 화자는 정발음 → 오탐은 Whisper 오인식.\n")
    lines.append("## 결론\n")
    lines.append(f"- **Whisper 오인식이 원인: {whisper_cause}/{n} ({wc_pct:.0f}%)** "
                 "(phones 정본은 정답발음과 일치 = 화자는 맞게 발음)")
    lines.append(f"- phones가 기대발음과 다름(화자 실발음/전사차): {phones_diverge}/{n}")
    lines.append("- → **엔진 정밀도의 병목은 Whisper 프론트엔드다.** 짧은 L2 발화에서 "
                 "Whisper가 다른 단어로 오인식 → 엔진이 그대로 가짜 오류를 보고.\n")
    lines.append("## 사례\n")
    for prompt, exp, stt_text, phones, nerr, score, ok in cases:
        mark = "Whisper탓" if ok else "화자/전사차"
        lines.append(f"- **{prompt}** | 기대 `{exp}` | Whisper `{stt_text}` | "
                     f"정본 `{phones}` | 플래그 {nerr}개(점수 {score}) | **{mark}**")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"진단 {n}건: Whisper 오인식 원인 {whisper_cause} ({wc_pct:.0f}%), "
          f"화자/전사차 {phones_diverge}")
    print(f"→ {REPORT}")


if __name__ == "__main__":
    main()
