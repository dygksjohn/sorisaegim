# Colab 실행 가이드 — wav2vec2 미세조정 (+3주차)

> [ml/finetune_wav2vec2_colab.ipynb](../ml/finetune_wav2vec2_colab.ipynb)를 Colab GPU에서
> 돌려 발음형 인식기를 미세조정하고, 학습 로그를 회수하는 절차. 목표 지표 = **정발음
> 오탐률(before 52%)** 을 낮추는 것 (이론 바닥 ~12%).

## 준비물

- 구글 계정 + 드라이브 여유 공간 **10GB 이상** (데이터 zip ~7.2GB + 모델 체크포인트)
- Colab: 무료 티어(T4)로 충분. 끊김이 잦으면 Colab Pro 권장(선택).

---

## Step 1 — 로컬에서 업로드 패키지 만들기

드라이브는 작은 파일 수천 개를 직접 읽으면 극도로 느리다. 참조 wav만 단일 zip으로 묶는다.

```cmd
cd /d s:\sorisaegim
.venv\Scripts\python.exe experiments\pack_for_colab.py --dry-run   :: 크기 확인 (약 7.2GB)
.venv\Scripts\python.exe experiments\pack_for_colab.py             :: sorisaegim_colab.zip 생성
```

산출: `s:\sorisaegim\sorisaegim_colab.zip` (splits·vocab + wav 20,906개).

## Step 2 — 드라이브에 올리기 (2개만)

1. `sorisaegim_colab.zip` → 내 드라이브 최상위(`MyDrive/`)에 업로드. (7.2GB — 유선/안정 회선 권장, 재개 가능)
2. `ml/finetune_wav2vec2_colab.ipynb` → 드라이브 아무 곳에 업로드하거나, Colab에서 직접 열기.

> zip 하나만 올리면 된다. 압축 해제는 Colab이 로컬 디스크에서 빠르게 처리한다.

## Step 3 — Colab에서 노트북 열기 + GPU 켜기

1. [colab.research.google.com](https://colab.research.google.com) → 파일 → 노트북 업로드(또는 드라이브에서 열기).
2. 상단 메뉴 **런타임 → 런타임 유형 변경 → 하드웨어 가속기: GPU (T4)** → 저장.
3. 셀 0(`nvidia-smi`)을 실행해 GPU가 잡히는지 확인.

## Step 4 — 경로 설정 (셀 "2. 설정")

셀 안의 3줄만 본인 환경에 맞추면 된다. 기본값대로 드라이브 최상위에 zip을 올렸다면 그대로 실행 가능:

```python
ZIP_ON_DRIVE = '/content/drive/MyDrive/sorisaegim_colab.zip'   # 올린 zip 위치
OUTPUT_DIR   = '/content/drive/MyDrive/sorisaegim/models/w2v2-jamo'  # 체크포인트(영구 보관)
DRIVE_ROOT   = '/content/sorisaegim'   # zip 푸는 로컬 경로 — 수정 불필요
```

- 드라이브 마운트 팝업이 뜨면 계정 인증.
- 다음 셀(압축 해제)이 zip을 `/content`에 **Python zipfile로** 푼다(~1–2분). "splits OK + wav 경로 일치"가
  나오면 성공. (리눅스 `unzip`은 한글 폴더명 `원천데이터`를 다른 유니코드 형태로 풀어 경로가 어긋난다 —
  노트북은 Python으로 풀어 이를 피한다. 옛 노트북을 쓰다 이 에러가 나면 아래 "자주 나는 문제" 참고.)

## Step 5 — 위에서부터 순서대로 실행

셀 1~10을 차례로. 주요 지점:
- **셀 5(전처리)**: train 16,813건 특징 추출 — 몇 분 걸린다(`num_proc=2`).
- **셀 8(모델)**: "Some weights were newly initialized" 경고는 **정상**(CTC 헤드를 새로 교체하니까).
- **셀 10(학습)**: 여기가 본체. T4에서 8 epoch 대략 1.5~3시간 예상(데이터·배치에 따라).

## Step 6 — 학습 중 볼 것

- **train loss**가 내려가는가 (셀 로그 50스텝마다).
- **epoch마다 eval `cer`**(자모 오류율)가 내려가는가 — 핵심 학습 지표.
- OOM(메모리 부족) 나면: 셀 9에서 `per_device_train_batch_size=8`→`4`, `gradient_accumulation_steps=2`→`4`로.

## Step 7 — 세션이 끊기면 (무료 티어 흔함)

체크포인트가 드라이브(`OUTPUT_DIR`)에 저장되므로 처음부터 다시 안 해도 된다:
1. 런타임 재접속 → 셀 0~9 다시 실행(데이터 압축 해제 셀 포함 — `/content`는 초기화됨).
2. 셀 10을 이렇게 바꿔 재개:
   ```python
   trainer.train(resume_from_checkpoint=True)
   ```

## Step 8 — 학습 끝나면: 회수할 로그 (이걸 나한테 주면 됨)

아래 4가지를 캡처/복사해서 다음 세션에 붙여주세요. 그러면 2차 학습 방향을 잡습니다.

1. **셀 10 학습 로그 표** — epoch별 `Training Loss` / `Validation Loss` / `Cer` 행 전체.
2. **셀 11 최종 출력** — 3줄 그대로:
   ```
   오탐률(eval_fp NNNN건): NN%   (Whisper before 52%)
   감지율(eval_det NNNN건): NN%
   순개선: 오탐 +NN%p
   ```
3. **막힌 것** — OOM·에러·중간에 바꾼 하이퍼파라미터가 있으면 그 내용.
4. (선택) `OUTPUT_DIR`에 저장된 최종 모델 폴더가 있는지 확인(있으면 이후 API 통합에 씀).

---

## 자주 나는 문제

| 증상 | 대처 |
|---|---|
| `assert zip/경로 확인` 실패 | `ZIP_ON_DRIVE` 경로 오타, 또는 업로드 미완료 |
| **`No such file or directory` (wav) — 추출은 20906개 다 됐는데 특정 경로만 없음** | 리눅스 `unzip`이 한글 폴더명을 다른 유니코드로 풀어 경로 불일치. **Python으로 재추출**: `import shutil,zipfile,os; shutil.rmtree(os.path.join(DRIVE_ROOT,'data'),ignore_errors=True); zipfile.ZipFile('/content/pkg.zip').extractall(DRIVE_ROOT)` 후 셀 5부터 재실행 |
| wav 경로 불일치 assert | 위와 동일 — Python zipfile로 재추출 |
| CUDA out of memory | batch size↓ + grad accum↑ (Step 6) |
| CER이 안 내려가고 발산 | 셀 9 `learning_rate` 3e-4→1e-4, 재학습 (2차 학습 힌트, 셀 12) |
| 세션 자꾸 끊김 | 체크포인트 재개(Step 7). 빈번하면 Colab Pro 검토 |
| datasets/transformers 버전 오류 | 셀 1 재실행 후 런타임 재시작(런타임→세션 다시 시작) |

## 기대 결과 해석

- **성공 기준**: 오탐률이 52%보다 **뚜렷이 낮아짐**(예 52%→20%대)이면서 감지율 유지.
- **오탐률 ~12% 근처면 이론 상한 근접** — 그 이상은 플래그 임계 완화(편집거리≥2, 셀 12)나
  Zeroth-Korean 정발음 보강이 다음 카드.
- CER은 좋은데 오탐이 안 줄면 → 플래그 규칙 문제(엔진 측), 셀 12 힌트 참고.

---

## Step 9 — 로컬 통합·데모 (모델 내보내기)

학습한 모델을 로컬 서비스(FastAPI)에 붙여 데모까지. 엔진은 이미 `engine=phone` 경로로
통합돼 있다 — 모델 파일만 로컬에 두면 된다.

### 9-1. Colab에서 모델 온전히 저장

체크포인트 폴더에는 모델 가중치만 있고 **프로세서(vocab·토크나이저)가 없다.** 최선 체크포인트를
로드한 뒤 모델+프로세서를 한 폴더로 저장한다 (Colab 새 셀):

```python
import glob, os
from transformers import Wav2Vec2ForCTC
ckpt = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'checkpoint-*')))[-1]
model = Wav2Vec2ForCTC.from_pretrained(ckpt)
EXPORT = '/content/drive/MyDrive/w2v2-jamo-export'
model.save_pretrained(EXPORT)
processor.save_pretrained(EXPORT)   # vocab.json·토크나이저·전처리기까지
print('내보내기 완료:', os.listdir(EXPORT))   # config.json, model.safetensors, vocab.json ...
```

### 9-2. 드라이브 → 로컬 PC

`MyDrive/w2v2-jamo-export/` 폴더(~1.2GB)를 통째로 내려받아 프로젝트의
**`data\models\w2v2-jamo\`** 에 넣는다. (구글 드라이브 웹에서 폴더 다운로드 → 압축 해제,
또는 Google Drive 데스크톱 동기화). 최종 형태:

```
data\models\w2v2-jamo\
  config.json  model.safetensors  vocab.json
  tokenizer_config.json  preprocessor_config.json  special_tokens_map.json
```

### 9-3. 데모 실행 (Whisper vs wav2vec2 오탐 비교)

```cmd
.venv\Scripts\python.exe experiments\phone_demo.py
```
1주차 녹음 20건에 두 엔진을 나란히 돌려 **정발음에서의 오탐 건수**를 비교한다
(AI Hub 실측 52%→6%의 로컬 재현). 산출: `experiments\results\phone_demo.md`.

### 9-4. 서버에서 사용

서버 실행 후 `/attempts` 요청에 `engine=phone`을 넣으면 발음형 인식기로 채점한다
(기본은 `whisper`). 모델이 없으면 503 `phone_model_missing`. CPU 추론이라 문장당 수 초.
프론트에 엔진 토글을 붙이는 건 선택(백로그).

> 데모 영상: 정발음을 읽었을 때 Whisper 경로는 헛오류를 하이라이트하지만 wav2vec2 경로는
> 100점을 주는 장면이 핵심 컷 — 오탐 제거를 시각적으로 보여준다.
