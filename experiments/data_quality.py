r"""+1주차 — 오디오 데이터 품질 전수 검사 (ML 고도화 후속계획).

대상:
  1. data\uploads (attempts 참조 녹음: user webm + synth mp3)
  2. attempts가 참조하지만 파일이 없는 경우 (missing)
  3. uploads에 있지만 attempts가 참조하지 않는 고아 파일 (orphan)
  4. experiments\recordings\*.wav (1주차 골드셋 20건, manifest.csv 기준)

검사 항목 (플래그):
  decode_fail     ffmpeg 디코딩 실패
  mostly_silent   활성(발화) 구간 비율 < 10%
  low_volume      전체 RMS < -40 dBFS
  clipping        |샘플| ≥ 32600 비율 > 0.5%
  too_short       음절당 길이 < 0.08s (문장 대비 비정상적으로 짧음)
  too_long        음절당 길이 > 1.20s (앞뒤 무음 과다 포함)
  duplicate_exact 디코딩된 PCM MD5 중복 (첫 파일만 원본으로 남김)
  orphan          DB가 참조하지 않는 파일
  missing         DB가 참조하지만 파일 없음

판정: fail(decode_fail·mostly_silent·duplicate_exact·missing)
      review(low_volume·clipping·too_short·too_long·orphan) / pass

실행 (CMD, 프로젝트 루트에서 — 서버 불필요):
    .venv\Scripts\python.exe experiments\data_quality.py
산출: experiments\results\data_quality_report.csv + 콘솔 요약
"""

import csv
import hashlib
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.db import UPLOADS_DIR, get_conn  # noqa: E402
from engine.hangul import is_hangul_syllable  # noqa: E402

RECORDINGS_DIR = Path(__file__).parent / "recordings"
RESULTS_DIR = Path(__file__).parent / "results"
REPORT_CSV = RESULTS_DIR / "data_quality_report.csv"

SAMPLE_RATE = 16000
RMS_FLOOR_DBFS = -40.0      # 이하면 low_volume
ACTIVE_WIN_S = 0.2          # 활성 구간 판정 창
ACTIVE_THRESH_DBFS = -45.0  # 창 RMS가 이보다 크면 '발화 중'
MIN_ACTIVE_RATIO = 0.10     # 미만이면 mostly_silent
CLIP_LEVEL = 32600
MAX_CLIP_RATIO = 0.005
MIN_SEC_PER_SYL = 0.08
MAX_SEC_PER_SYL = 1.20

FAIL_FLAGS = {"decode_fail", "mostly_silent", "duplicate_exact", "missing"}


def decode_pcm(path: Path) -> np.ndarray | None:
    """ffmpeg로 16k mono s16le 디코딩. 실패 시 None."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or len(proc.stdout) < 2:
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16)


def dbfs(x: np.ndarray) -> float:
    if len(x) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    return -120.0 if rms < 1 else 20 * np.log10(rms / 32768.0)


def audio_metrics(pcm: np.ndarray) -> dict:
    dur = len(pcm) / SAMPLE_RATE
    win = int(ACTIVE_WIN_S * SAMPLE_RATE)
    n_win = max(len(pcm) // win, 1)
    active = sum(
        1 for k in range(n_win) if dbfs(pcm[k * win:(k + 1) * win]) > ACTIVE_THRESH_DBFS
    )
    return {
        "duration_s": round(dur, 2),
        "rms_dbfs": round(dbfs(pcm), 1),
        "clip_ratio": round(float(np.mean(np.abs(pcm.astype(np.int32)) >= CLIP_LEVEL)), 4),
        "active_ratio": round(active / n_win, 2),
        "md5": hashlib.md5(pcm.tobytes()).hexdigest(),
    }


def count_syllables(text: str) -> int:
    return sum(1 for ch in text if is_hangul_syllable(ch))


def check(m: dict, syllables: int) -> list[str]:
    flags = []
    if m["active_ratio"] < MIN_ACTIVE_RATIO:
        flags.append("mostly_silent")
    if m["rms_dbfs"] < RMS_FLOOR_DBFS:
        flags.append("low_volume")
    if m["clip_ratio"] > MAX_CLIP_RATIO:
        flags.append("clipping")
    if syllables:
        sps = m["duration_s"] / syllables
        if sps < MIN_SEC_PER_SYL:
            flags.append("too_short")
        elif sps > MAX_SEC_PER_SYL:
            flags.append("too_long")
    return flags


def collect_targets() -> list[dict]:
    """검사 대상 목록: (경로, 출처, 메타)."""
    targets, referenced = [], set()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT a.id, a.sentence_id, a.audio_path, a.source, s.text"
            " FROM attempts a JOIN sentences s ON s.id = a.sentence_id"
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        p = Path(r["audio_path"])
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        referenced.add(p.name)
        targets.append({
            "path": p, "origin": r["source"], "attempt_id": r["id"],
            "sentence_id": r["sentence_id"], "text": r["text"],
        })
    for f in sorted(UPLOADS_DIR.iterdir()):
        if f.is_file() and f.name not in referenced:
            targets.append({"path": f, "origin": "orphan", "attempt_id": "",
                            "sentence_id": "", "text": ""})
    manifest = RECORDINGS_DIR / "manifest.csv"
    if manifest.exists():
        with open(manifest, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                targets.append({
                    "path": RECORDINGS_DIR / row["file"], "origin": "week1",
                    "attempt_id": "", "sentence_id": "",
                    "text": row.get("intended_text") or row["target_text"],
                })
    return targets


def main() -> None:
    targets = collect_targets()
    seen_md5: dict[str, str] = {}
    report = []
    for t in targets:
        row = {
            "file": t["path"].name, "origin": t["origin"],
            "attempt_id": t["attempt_id"], "sentence_id": t["sentence_id"],
            "duration_s": "", "rms_dbfs": "", "clip_ratio": "", "active_ratio": "",
            "sec_per_syl": "", "flags": "", "verdict": "",
        }
        if not t["path"].exists():
            flags = ["missing"]
        else:
            pcm = decode_pcm(t["path"])
            if pcm is None:
                flags = ["decode_fail"]
            else:
                m = audio_metrics(pcm)
                syl = count_syllables(t["text"])
                flags = check(m, syl)
                if m["md5"] in seen_md5:
                    flags.append("duplicate_exact")
                    row["flags_dup_of"] = seen_md5[m["md5"]]
                else:
                    seen_md5[m["md5"]] = t["path"].name
                row.update({k: m[k] for k in
                            ("duration_s", "rms_dbfs", "clip_ratio", "active_ratio")})
                if syl:
                    row["sec_per_syl"] = round(m["duration_s"] / syl, 3)
        if t["origin"] == "orphan":
            flags.append("orphan")
        row["flags"] = ";".join(flags)
        row["verdict"] = ("fail" if set(flags) & FAIL_FLAGS
                          else "review" if flags else "pass")
        report.append(row)

    RESULTS_DIR.mkdir(exist_ok=True)
    fields = ["file", "origin", "attempt_id", "sentence_id", "duration_s", "rms_dbfs",
              "clip_ratio", "active_ratio", "sec_per_syl", "flags", "flags_dup_of",
              "verdict"]
    with open(REPORT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(report)

    print(f"검사 {len(report)}건 → {REPORT_CSV}\n")
    print(f"{'origin':<8} {'pass':>5} {'review':>7} {'fail':>5}")
    for origin in ("user", "synth", "week1", "orphan"):
        c = Counter(r["verdict"] for r in report if r["origin"] == origin)
        print(f"{origin:<8} {c['pass']:>5} {c['review']:>7} {c['fail']:>5}")
    flag_counts = Counter(fl for r in report for fl in r["flags"].split(";") if fl)
    print("\n플래그별 건수:")
    for fl, n in flag_counts.most_common():
        print(f"  {fl:<16} {n}")


if __name__ == "__main__":
    main()
