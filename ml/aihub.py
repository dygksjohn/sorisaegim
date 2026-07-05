"""AI Hub "교육용 외국인 한국어 음성" 4종 파서 — +2주차.

데이터 구조 (권역별: asia / china_japan / english / europe):
  Sample/01.원천데이터/pronunciation/sound/*.wav   ← 단어·구 단위 발화 음원
  Sample/02.라벨링데이터/pronunciation/lab/*.json  ← 라벨 (phones + error_tags + 화자메타)
  (Speech/ 하위는 문장 자유발화 — error_tags 없음. 이 파서는 pronunciation만 다룬다.)

라벨 핵심 필드:
  prompt      제시어 (화자가 읽어야 할 표기)
  phones      사람이 전사한 '실제 발화' 자모 시퀀스 (+ 타임스탬프)
  error_tags  오류 구간 (분류 + 시간). 분류를 3버킷으로 매핑한다:
    segmental  초성·종성·모음오류         → 우리 자모 비교 엔진이 직접 판정 가능
    phon_rule  비음화·경음화·유음화·구개음화·격음화·연음규칙·ㄴ-첨가·음운탈락·모음삽입
                                           → 1주차 '표기 수렴 문제'. wav2vec2 조준 대상
    prosodic   반복·간투사·강세·경계억양·기타 → 우리 범위 밖

파일명: UserID-성별-출생년-언어약어-레벨-문제ID-음원ID(.wav/.json)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

AIHUB_ROOT = Path(__file__).parent.parent / "data" / "aihub"
REGIONS = ["asia", "china_japan", "english", "europe"]

# error_tag 분류 → 버킷
SEGMENTAL = {"초성", "종성", "모음오류"}
PHON_RULE = {"비음화", "경음화", "유음화", "구개음화", "격음화",
             "연음규칙", "ㄴ-첨가", "음운탈락", "모음삽입"}
PROSODIC = {"반복", "간투사", "강세 오류", "경계억양 오류", "기타"}

# error_tag '초성/종성/모음오류' → 엔진 component 이름
COMPONENT_MAP = {"초성": "choseong", "종성": "jongseong", "모음오류": "jungseong"}


def bucket(tag: str) -> str:
    if tag in SEGMENTAL:
        return "segmental"
    if tag in PHON_RULE:
        return "phon_rule"
    return "prosodic"


@dataclass
class AihubRecord:
    region: str
    wav_path: Path            # 존재 확인된 절대 경로 (없으면 None)
    user_id: str
    proficiency: str          # Beginner / Intermediate / Advance / Fluent
    nationality: str
    language: str
    prompt: str               # 제시어(표기)
    phones: str               # 실발화 자모 시퀀스 (공백 없이 이어붙임)
    pronun_eval: int          # PronunProfEval (0~3, 발음 숙련도 평가)
    error_tags: list = field(default_factory=list)  # [{tag, bucket, component, start, end}]

    @property
    def error_buckets(self) -> set:
        return {t["bucket"] for t in self.error_tags}

    @property
    def error_components(self) -> set:
        """segmental 오류의 엔진 component 집합 (초성/중성/종성)."""
        return {t["component"] for t in self.error_tags if t["component"]}


def _label_dir(region: str) -> Path:
    return AIHUB_ROOT / region / "Sample" / "02.라벨링데이터" / "pronunciation" / "lab"


def _sound_dir(region: str) -> Path:
    return AIHUB_ROOT / region / "Sample" / "01.원천데이터" / "pronunciation" / "sound"


def parse_label(region: str, fp: Path) -> AihubRecord:
    d = json.loads(fp.read_text(encoding="utf-8"))
    meta = d["SpeakerMetadata"]
    rec = d["RecordingMetadata"]
    ph = rec.get("phonemic", {})
    tags = []
    for t in ph.get("error_tags", []):
        cat = t["error_tag"]
        tags.append({
            "tag": cat, "bucket": bucket(cat),
            "component": COMPONENT_MAP.get(cat, ""),
            "start": t["start"], "end": t["end"],
        })
    wav = _sound_dir(region) / (fp.stem + ".wav")
    return AihubRecord(
        region=region,
        wav_path=wav if wav.exists() else None,
        user_id=d.get("UserID", ""),
        proficiency=meta.get("proficiency", ""),
        nationality=meta.get("nationality", ""),
        language=meta.get("language", ""),
        prompt=rec.get("prompt", ""),
        phones="".join(p["phone"] for p in ph.get("phones", [])),
        pronun_eval=d.get("EvaluationMetadata", {}).get("PronunProfEval", -1),
        error_tags=tags,
    )


def iter_records(regions=None):
    """4개(또는 지정) 권역의 pronunciation 라벨을 순회하며 AihubRecord yield."""
    for region in (regions or REGIONS):
        lab = _label_dir(region)
        if not lab.exists():
            continue
        for fp in sorted(lab.glob("*.json")):
            yield parse_label(region, fp)
