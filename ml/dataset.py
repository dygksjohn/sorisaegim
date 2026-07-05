r"""학습 데이터셋 분할 — +2주차 작업 4.

표적(재정의): wav2vec2가 발음형 자모(phones)를 출력하도록 미세조정해 Whisper 프론트엔드
교체. 학습쌍 = (wav, phones 자모 시퀀스). AI Hub가 이런 쌍 2만 건을 직접 제공.

분할 원칙:
  - **화자(UserID) 단위 분리** — 같은 화자가 train/test에 동시에 들지 않게 (누출 방지).
    UserID의 안정 해시(md5)로 결정적 배정 (Math.random/hash() 비의존, 재현 가능).
  - train 80% / val 10% / test 10% (화자 기준).
  - test는 두 평가 프로토콜을 품는다:
      · FP eval  = test의 정발음(오류 태그 없는) 레코드 → 오탐률 측정(before 52%)
      · det eval = test의 오류 태그 레코드 → 성분/규칙별 감지 측정
  - **골드셋 격리**: 1주차 인간 녹음 20건(=attempts 1~20)은 별도 테스트 전용, 학습 절대 금지.
    (AI Hub와 화자 무관하므로 자동 분리되지만 명시적으로 문서화.)

라벨: phones_to_flat_jamo(정본). 학습 타깃은 사람 전사 발음형.

산출(재배포 금지 — data/ 아래, gitignore):
  data/aihub/splits/{train,val,test}.jsonl  (wav_path, label, user_id, region, ...)
  data/aihub/splits/eval_fp.jsonl / eval_det.jsonl  (test 부분집합)
집계 요약은 콘솔 + 반환.

실행: .venv\Scripts\python.exe -m ml.dataset
"""

import hashlib
import json
from pathlib import Path

from ml.aihub import iter_records, phones_to_flat_jamo

SPLITS_DIR = Path(__file__).parent.parent / "data" / "aihub" / "splits"
VAL_END = 0.10   # [0,0.10) val
TEST_END = 0.20  # [0.10,0.20) test, [0.20,1) train


def speaker_bucket(user_id: str) -> float:
    """UserID → [0,1) 안정 해시. 프로세스 무관 재현 가능."""
    h = hashlib.md5(user_id.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def split_of(user_id: str) -> str:
    b = speaker_bucket(user_id)
    if b < VAL_END:
        return "val"
    if b < TEST_END:
        return "test"
    return "train"


def build() -> dict:
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    writers = {name: open(SPLITS_DIR / f"{name}.jsonl", "w", encoding="utf-8")
               for name in ("train", "val", "test")}
    eval_fp = open(SPLITS_DIR / "eval_fp.jsonl", "w", encoding="utf-8")
    eval_det = open(SPLITS_DIR / "eval_det.jsonl", "w", encoding="utf-8")

    counts = {k: 0 for k in ("train", "val", "test")}
    speakers = {k: set() for k in ("train", "val", "test")}
    n_fp = n_det = n_skip = 0
    try:
        for r in iter_records():
            if r.wav_path is None:
                n_skip += 1
                continue
            label = phones_to_flat_jamo(r.phones)
            if not label:
                n_skip += 1
                continue
            split = split_of(r.user_id)
            rec = {
                "wav_path": r.wav_path.relative_to(
                    Path(__file__).parent.parent).as_posix(),
                "label": " ".join(label),          # 공백 구분 자모 (CTC 타깃)
                "prompt": r.prompt,
                "user_id": r.user_id, "region": r.region,
                "proficiency": r.proficiency,
                "n_errors": len(r.error_tags),
                "error_components": sorted(r.error_components),
                "error_tags": [t["tag"] for t in r.error_tags],
            }
            writers[split].write(json.dumps(rec, ensure_ascii=False) + "\n")
            counts[split] += 1
            speakers[split].add(r.user_id)
            if split == "test":
                if r.error_tags:
                    eval_det.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_det += 1
                else:
                    eval_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_fp += 1
    finally:
        for w in writers.values():
            w.close()
        eval_fp.close()
        eval_det.close()

    # 화자 누출 검증
    overlap = (speakers["train"] & speakers["test"]) | (speakers["val"] & speakers["test"])
    summary = {
        "counts": counts,
        "speakers": {k: len(v) for k, v in speakers.items()},
        "eval_fp": n_fp, "eval_det": n_det,
        "skipped": n_skip,
        "speaker_overlap": len(overlap),
    }
    return summary


def build_vocab() -> dict:
    """train.jsonl 라벨에서 자모 vocab 생성 (CTC용). blank/unk/pad 포함.

    wav2vec2 CTC 관례: 인덱스 0을 [PAD](=blank), 별도 [UNK].
    반환 {jamo: id}. data/aihub/splits/vocab.json 에 저장.
    """
    jamos = set()
    with open(SPLITS_DIR / "train.jsonl", encoding="utf-8") as f:
        for line in f:
            jamos.update(json.loads(line)["label"].split())
    vocab = {"[PAD]": 0, "[UNK]": 1}
    for j in sorted(jamos):
        vocab[j] = len(vocab)
    (SPLITS_DIR / "vocab.json").write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    return vocab


def main() -> None:
    s = build()
    vocab = build_vocab()
    print("분할 완료 (화자 단위):")
    for k in ("train", "val", "test"):
        print(f"  {k:<5} 레코드 {s['counts'][k]:>6} · 화자 {s['speakers'][k]:>5}")
    print(f"  test 내 평가셋: FP(정발음) {s['eval_fp']} · det(오류) {s['eval_det']}")
    print(f"  스킵(wav/label 없음) {s['skipped']}")
    print(f"  ✅ 화자 누출: {s['speaker_overlap']}건 (0이어야 정상)")
    print(f"  vocab {len(vocab)}종 (자모 {len(vocab) - 2} + PAD/UNK)")
    print(f"→ {SPLITS_DIR}")


if __name__ == "__main__":
    main()
