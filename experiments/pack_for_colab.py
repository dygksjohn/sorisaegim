r"""Colab 업로드 패키지 생성 — 분할이 참조하는 wav만 골라 zip.

구글 드라이브는 작은 파일 수천 개 I/O가 매우 느리다. 학습 전 단일 zip으로 묶어
드라이브에 올린 뒤 Colab 로컬 디스크(/content)에 풀면 I/O 병목이 사라진다.

패키지 내용 (zip 내부 경로 = 프로젝트 루트 기준 그대로):
  data/aihub/splits/*.jsonl, vocab.json
  data/aihub/<region>/.../sound/<referenced>.wav   (train/val/eval에서 참조된 것만)

실행:
  .venv\Scripts\python.exe experiments\pack_for_colab.py --dry-run   # 크기만 확인
  .venv\Scripts\python.exe experiments\pack_for_colab.py             # zip 생성
산출: sorisaegim_colab.zip (프로젝트 루트)
"""

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPLITS = ROOT / "data" / "aihub" / "splits"
OUT = ROOT / "sorisaegim_colab.zip"
SPLIT_FILES = ["train.jsonl", "val.jsonl", "test.jsonl",
               "eval_fp.jsonl", "eval_det.jsonl", "vocab.json"]


def referenced_wavs() -> set:
    wavs = set()
    for name in ("train.jsonl", "val.jsonl", "eval_fp.jsonl", "eval_det.jsonl"):
        with open(SPLITS / name, encoding="utf-8") as f:
            for line in f:
                wavs.add(json.loads(line)["wav_path"])
    return wavs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wavs = sorted(referenced_wavs())
    total = missing = 0
    size = 0
    for w in wavs:
        p = ROOT / w
        if p.exists():
            size += p.stat().st_size
            total += 1
        else:
            missing += 1
    print(f"참조 wav {len(wavs)}건: 존재 {total}, 누락 {missing}")
    print(f"wav 총 용량: {size / 1e9:.2f} GB")
    split_size = sum((SPLITS / s).stat().st_size for s in SPLIT_FILES) / 1e6
    print(f"분할·vocab: {split_size:.1f} MB")
    if args.dry_run:
        print("(dry-run — zip 생성 안 함)")
        return

    print(f"\nzip 생성 중 → {OUT.name} ...")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_STORED) as z:  # wav는 이미 압축 무의미
        for s in SPLIT_FILES:
            z.write(SPLITS / s, f"data/aihub/splits/{s}")
        for i, w in enumerate(wavs, 1):
            p = ROOT / w
            if p.exists():
                z.write(p, w)
            if i % 2000 == 0:
                print(f"  {i}/{len(wavs)}")
    print(f"완료: {OUT} ({OUT.stat().st_size / 1e9:.2f} GB)")


if __name__ == "__main__":
    main()
