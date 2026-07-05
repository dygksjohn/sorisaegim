r"""CTC 학습 데이터 로컬 검증 — +2주차 작업 5.

Colab에서 wav2vec2 CTC 미세조정에 넣기 전에, 로컬에서 확인한다:
  1. vocab이 val/test 라벨을 전부 커버하는가 (미등록 자모 = [UNK] 유출)
  2. wav가 16kHz로 디코딩되는가 (whisper.audio.load_audio)
  3. CTC 길이 제약: wav2vec2 프레임 수(≈samples/320) ≥ 라벨 길이 (아니면 학습 불가 샘플)
  4. 라벨 인코딩/디코딩 왕복이 맞는가

무거운 스택(datasets/torch)은 Colab에서 돌리므로 여기선 whisper.audio만 사용.
산출: 콘솔 + results\ctc_data_verify.md. 실행:
    .venv\Scripts\python.exe experiments\verify_ctc_data.py [--n 300]
"""

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from whisper.audio import SAMPLE_RATE, load_audio  # noqa: E402

ROOT = Path(__file__).parent.parent
SPLITS = ROOT / "data" / "aihub" / "splits"
RESULTS = Path(__file__).parent / "results"
W2V_DOWNSAMPLE = 320  # wav2vec2 CNN stride 총곱 (16k → ~50fps)


def load_jsonl(name):
    with open(SPLITS / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300, help="오디오 검증 표본 수")
    args = ap.parse_args()

    vocab = json.loads((SPLITS / "vocab.json").read_text(encoding="utf-8"))
    inv = {v: k for k, v in vocab.items()}

    # 1. vocab 커버리지 (val/test 전수)
    unk = {}
    for split in ("val", "test"):
        for rec in load_jsonl(f"{split}.jsonl"):
            for j in rec["label"].split():
                if j not in vocab:
                    unk[j] = unk.get(j, 0) + 1

    # 2~4. 오디오/길이/왕복 (train 앞 n건)
    train = load_jsonl("train.jsonl")
    step = max(len(train) // args.n, 1)
    sample = train[::step][:args.n]
    n_ok = n_audio_fail = n_too_short = 0
    min_ratio = 1e9
    durs = []
    for rec in sample:
        wav = ROOT / rec["wav_path"]
        try:
            audio = load_audio(str(wav))
        except Exception:
            n_audio_fail += 1
            continue
        frames = len(audio) // W2V_DOWNSAMPLE
        label_ids = [vocab.get(j, 1) for j in rec["label"].split()]
        durs.append(len(audio) / SAMPLE_RATE)
        # CTC: 입력 프레임 ≥ 라벨 길이 (반복문자 없으면 등호 가능, 여유 필요)
        ratio = frames / max(len(label_ids), 1)
        min_ratio = min(min_ratio, ratio)
        if frames < len(label_ids):
            n_too_short += 1
        # 왕복
        decoded = " ".join(inv[i] for i in label_ids)
        if decoded == rec["label"]:
            n_ok += 1

    n = len(sample)
    lines = ["# CTC 학습 데이터 로컬 검증 (+2주차 작업 5)\n"]
    lines.append(f"> vocab {len(vocab)}종. 오디오 표본 {n}건(train). Colab 투입 전 사전점검.\n")
    lines.append("## 결과\n")
    lines.append(f"- vocab 커버리지(val+test): 미등록 자모 **{len(unk)}종** "
                 f"{'✅' if not unk else '⚠️ ' + str(unk)}")
    lines.append(f"- 오디오 디코딩 실패: {n_audio_fail}/{n} {'✅' if not n_audio_fail else '⚠️'}")
    lines.append(f"- CTC 길이 위반(프레임<라벨): {n_too_short}/{n} "
                 f"{'✅' if not n_too_short else '⚠️'} (최소 프레임/라벨 비율 {min_ratio:.1f})")
    lines.append(f"- 라벨 인코딩 왕복 일치: {n_ok}/{n} {'✅' if n_ok == n else '⚠️'}")
    if durs:
        durs.sort()
        lines.append(f"- 오디오 길이(초): 중앙값 {durs[len(durs)//2]:.1f}, "
                     f"최소 {durs[0]:.1f}, 최대 {durs[-1]:.1f}")
    lines.append("\n## Colab 학습 준비물\n")
    lines.append("- 베이스: `kresnik/wav2vec2-large-xlsr-korean` (2주차 검증 자산)")
    lines.append("- vocab: `data/aihub/splits/vocab.json` (PAD=0=CTC blank, UNK=1)")
    lines.append("- 데이터: train/val jsonl (wav_path + 공백구분 자모 label)")
    lines.append("- 평가: eval_fp(오탐률 before 52%) / eval_det(감지) — 화자 분리 확인됨")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "ctc_data_verify.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"vocab {len(vocab)}종, 미등록 {len(unk)}")
    print(f"오디오 {n}건: 실패 {n_audio_fail}, CTC길이위반 {n_too_short}, "
          f"왕복OK {n_ok} (최소비율 {min_ratio:.1f})")
    print(f"→ {RESULTS / 'ctc_data_verify.md'}")


if __name__ == "__main__":
    main()
