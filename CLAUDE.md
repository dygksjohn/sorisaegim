# CLAUDE.md — 소리새김 (한국어 발음 코치)

프로젝트 작업 시 지침. 글로벌 `~/.claude/CLAUDE.md`와 충돌하면 이 문서를 우선한다.

## 프로젝트 개요

문장을 읽으면 STT로 발음을 인식해 **자모(초/중/종성) 단위**로 점수화하고 어디가 틀렸는지
짚어주는 웹 서비스. 8주 1인 사이드 프로젝트로 완성됐고, 현재 **후속 ML 고도화**(이력서용
fine-tuning 경험) 진행 중.

- 스택: Python 3.13 / FastAPI / Whisper small / g2pk / scikit-learn
- **핵심 원칙: 비교는 항상 발음형(g2pk) 공간에서 한다.** 표기 "밥을"과 인식 "바블"은
  발음형이 같으므로 100점. 1주차 실험(Whisper가 틀린 발음을 표기로 교정)에서 나온 설계.

## 명령어 규약 (중요)

사용자는 **CMD·git bash 둘 다** 사용. 경로 구분자를 상황에 맞게 구분한다:

- **git에 넘기는 파일 경로는 `/`(슬래시)로 쓴다.** git이 셸과 무관하게 처리하므로 CMD·git bash
  양쪽에서 동작한다. 예: `git add ml/dataset.py docs/log.md`. (`\`는 git bash에서 이스케이프로 깨진다.)
- **venv 파이썬·실행 파일은 셸에 맞게.** CMD는 명령 경로 맨 앞의 `/`를 스위치로 오해하므로 `\` 필요:
  - CMD: `.venv\Scripts\python.exe experiments\xxx.py`
  - git bash: `.venv/Scripts/python.exe experiments/xxx.py`
  - 스크립트 docstring의 "실행:" 예시는 CMD 기준(`\`)으로 통일돼 있다.
- 환경변수는 CMD `%VAR%`, git bash `$VAR`. PowerShell 전용 cmdlet은 별도 요청 없으면 쓰지 않는다.
- 예외: `ml/finetune_wav2vec2_colab.ipynb`의 셸 명령(`!unzip` 등)은 Colab(리눅스)에서 도는
  것이라 bash가 맞다 — 로컬 명령과 혼동 금지.

## 환경 셋업 / 실행

```cmd
:: 폴더 이동·이름 변경 후 venv 재생성 (mecab DLL 복사 + 테스트까지)
setup_venv.cmd

:: 서버 실행 → http://localhost:8000
.venv\Scripts\uvicorn.exe app.main:app --port 8000

:: 테스트 (엔진 단위 32개)
.venv\Scripts\python.exe -m pytest tests -q
```

- **g2pk는 네이티브 의존성이 있다**: MSVC C++ 워크로드 + `C:\mecab`의 mecab-ko-msvc +
  `libmecab.dll`을 site-packages에 복사. 절차는 `experiments\README.md`. `setup_venv.cmd`가
  DLL 복사를 자동 처리한다.
- **의존성은 requirements.txt에 반드시 반영**한다. 과거 서버·ML 패키지가 누락돼 venv 재생성
  후 기능이 깨진 적 있음 (수동 설치분이 기록 안 됨).

## 구조

```
engine/   자모 비교 엔진 — 순수 Python, 외부 의존성 0 (해커톤 재사용 자산). compare()가 핵심.
app/      FastAPI + SQLite(sentences 33 · attempts). stt/·tts/ = Whisper·Edge-TTS 래퍼.
ml/       features·train·recommend(7주차) + aihub·dataset(후속). 발음형 인식기 학습 파이프라인.
static/   프론트 (프레임워크 없는 HTML+JS, 화면 2개 + 기록)
experiments/  주차별 기술 검증 스크립트. 결과는 results/ 에 md·csv.
docs/     기획·주차별 계획·API 스펙·ml_report·주간 로그(log.md)·후속계획·Colab 가이드.
```

## 핵심 설계 원칙 / 함정

- **발음형 공간 비교**: `compare(reference, recognized)`는 양쪽을 g2pk로 변환 후 자모 정렬.
  음소 인식기(wav2vec2) 출력처럼 이미 발음형이면 `recognized_is_phonetic=True` — 아니면
  g2p 재적용으로 음운 규칙이 되살아나 오류가 지워진다(테스트가 잡아준 설계 결정).
- **attempts.audio_path는 프로젝트 루트 기준 상대경로**로 저장(`data/uploads/...`). 폴더 이동/
  이름 변경에도 안 깨지게. 절대경로로 되돌리지 말 것.
- **한글 콘솔 출력**: 스크립트에서 한글을 print하면 cp949로 깨진다. 진단 스크립트는
  `PYTHONIOENCODING=utf-8` + `sys.stdout` UTF-8 래핑, 또는 결과를 파일로 써서 Read로 확인.
- **커밋 메시지의 특수문자**: `%`·따옴표가 셸에서 깨질 수 있음 — 메시지를 파일로 써서
  `git commit -F` 사용.

## 데이터 재배포 금지 (필수)

- `data/`는 통째로 .gitignore (DB·업로드 녹음·AI Hub 데이터·splits).
- **AI Hub "교육용 외국인 한국어 음성"**은 이용약관상 재배포 금지 → `data/aihub/` 아래에만
  두고, 원본 라벨을 재포장한 산출물(`aihub_manifest.csv`, `splits/*.jsonl`)도 gitignore.
  집계 리포트(숫자만, `results/aihub_*.md`)는 추적 가능.

## 현재 상태 (후속 ML 고도화)

계획: `docs/후속계획_ML고도화_v1.md`. 주간 로그: `docs/log.md`.

- **미세조정 표적(재정의됨)**: 원래 "받침 감지율 35%→개선"이었으나 +2주차 실측으로 반증 —
  실전 받침 감지율은 73%(합성 35%는 TTS 한계였음). **진짜 병목은 정발음 오탐률 52%**이고
  83%가 Whisper 오인식. → 표적 = **Whisper를 wav2vec2 발음형 인식기로 교체해 오탐 제거**.
  근거: `experiments/results/aihub_detection_findings.md`.
- **학습 라벨 = AI Hub phones**(사람 전사 발음형, 2만 건). g2pk는 제시어 기대발음 생성에만.
- **데이터 분할**: 화자(UserID) 단위, 누출 0 검증. **골드셋(1주차 녹음 20건 = attempts 1~20)은
  테스트 전용, 학습 절대 금지.** eval_fp(오탐)·eval_det(감지)가 평가 프로토콜.
- **다음**: `ml/finetune_wav2vec2_colab.ipynb`를 Colab GPU에서 실행(사람 몫). 절차는
  `docs/colab_실행가이드.md`. 학습 후 오탐률/감지율 로그로 2차 학습 방향 결정.

## 톤

- 이력서·면접용 프로젝트다. **정직한 반증**(가정을 실데이터로 뒤집고 방향 수정)이 이 프로젝트의
  핵심 서사 — 1주차 교정실험, 7주차 합성학습 실패, +2주차 오탐 발견이 그 계보. 지표는 부풀리지
  말고 한계와 함께 제시한다.
- 기본 응답 언어는 한국어.
