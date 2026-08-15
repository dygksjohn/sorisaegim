# 주간 로그

> 운영 원칙: 주당 3줄 — 한 것 / 막힌 것 / 다음. 회고 글 재료.
> 8주차로 본 프로젝트 완료. 이하 **후속 +N주차**는 ML 고도화(이력서용 fine-tuning 경험) 확장 — 계획 `docs/후속계획_ML고도화_v1.md`.

## 배포 8단계 준비 (2026-08-09) — 방식 결정 + 준비물 작성

- 한 것: ① 배포 방식을 EC2 단일 인스턴스로 결정. App Runner는 볼륨을 못 붙여 SQLite·녹음이 재배포마다 유실되고, Fargate는 EFS(NFS) 위 SQLite의 파일 락 위험 + 로드밸런서 고정비가 붙는다. EC2는 로컬에서 검증한 볼륨 구성을 그대로 옮길 수 있다. ② 준비물 작성: `deploy/compose.prod.yaml`(앱 + Caddy 2컨테이너, 앱 포트 비공개) · `deploy/Caddyfile`(HTTP-01 자동 인증서) · `deploy/user-data.sh`(도커·컴포즈·AWS CLI 설치 자동화) · `deploy/.env.example`. ③ 절차·근거 문서 `docs/배포_AWS_v1.md` — 결정마다 버린 선택지와 되돌릴 조건을 함께 기록.
- 결정 요지: t3.medium(2GiB는 OOM 위험 → 측정값 오염), 서울 리전(국제 구간 지연이 측정에 섞이지 않게), Ubuntu 24.04(컨테이너 베이스와 같은 Debian 계열), Caddy 리버스 프록시(앱 코드 무수정 + 인증서 자동), `restart: unless-stopped`(systemd 유닛 불필요), IAM 인스턴스 역할(서버에 액세스 키를 두지 않음), 탄력적 IP(IP 변경 시 DNS·인증서 동시 파손 방지).
- 다음: 08-15 실행 — ECR 푸시(5GB, 30분+이므로 당일 맨 앞) → IAM·인스턴스·DNS → 기동·검증. 도메인은 `SITE_ADDRESS` 한 줄로 분리해 당일 결정 가능. 모델 웨이트 미배치라 `engine=phone`은 배포 후에도 503.

## 배포 7단계 (2026-08-08) — 컨테이너화 완료

- 한 것: 이미지 빌드부터 마이크 실사용까지 통과. ① `Dockerfile` 2스테이지(builder에서 컴파일, 런타임엔 빌드툴 없음) + `.dockerignore`(`data/` 제외 — AI Hub 재배포 금지·DB는 볼륨) + `compose.yaml`(볼륨 `sorisaegim-data:/app/data`). ② 재현 결과: 이미지 5.04GB, 기동→API 응답 12.3초, `/sentences` 33문장 한글 정상, 정적 화면·통계 API 200, 브라우저 마이크 녹음→채점 정상. ③ 빌드 시점에 Whisper small·nltk cmudict를 굽고 g2pk 스모크 체크(`밥을`→`바블`)를 넣어, 첫 요청이 네트워크를 타거나 사전 미적재로 터지는 것을 막았다.
- 막힌 것: ① 첫 빌드가 `RuntimeError: mecab-config not found`로 실패 — `python-mecab-ko`는 pybind11 확장을 시스템 mecab에 링크하므로 g++만으로 부족하다. builder에 `mecab`·`libmecab-dev`, 런타임에 `libmecab2`를 넣어 해결(한국어 사전은 pip의 `python-mecab-ko-dic`). Windows에서 `C:\mecab`이 필요했던 것과 같은 이유다. ② torch CPU 휠은 `requirements.txt`의 `--extra-index-url`만으로는 보장되지 않아, Dockerfile에서 `--index-url`로 먼저 설치해 확정했다. ③ Docker Desktop이 사용자 폴더(`%LOCALAPPDATA%\Programs\DockerDesktop`) 설치라 서비스가 없다 — 빌드 전에 앱을 먼저 띄워야 한다.
- 다음: 8단계 AWS 배포. 그 전에 모델 웨이트 배치(handoff 3-1)가 남아 `engine=phone`은 여전히 503이다. 이미지 5.04GB의 절반이 venv(2.56GB)라 푸시 비용이 크므로, 배포 방식 결정 시 이미지 크기를 함께 본다. 감량 후보: `konlpy`+`JPype1`+`lxml` 제거(실사용 경로가 아님), numba/llvmlite 필요 여부, ffmpeg 최소 구성.

## 배포 7단계 시작 (2026-08-03 ~) — 저장소 최신화·의존성 고정·로컬 재현

- **한 것**: 컨테이너화 전 재현 가능한 기준선 확보. ① **기준 상태 확정**: HEAD `b2be82a`(정합성 수정: setup_venv.cmd 복구·torch 명시·handoff 문서 추적), Python 3.13.7(→ 베이스 `python:3.13-slim`), 테스트 43개 통과. ② **의존성 2단 고정**: `requirements.txt` 직접 의존을 `==`로 핀(실측 버전) + torch는 CPU 휠 인덱스 지정(GPU 휠로 이미지 붇는 것 방지), `requirements.lock.txt` 전체 스냅샷 95개. dry-run resolve 충돌 0. ③ **응답시간 기준선**(`experiments/bench_local.py` → `results/bench_local.md`): Whisper 경로 **콜드 로딩+첫 추론 4.61s / 웜 추론 평균 1.74s·p50 1.74s·최대 1.81s**(CPU, 1주차 정발음 5건, 서버 미경유). 자모 비교 엔진은 무시할 수준.
- **막힌 것**: ① **프레시 `pip install -r requirements.txt`가 `python-mecab-ko==1.3.7` 휠 빌드에서 실패**(g2pk 네이티브 의존). handoff 3-3 확증 — 재현엔 네이티브 mecab + 빌드툴 필요(Windows: MSVC + C:\mecab, 리눅스: mecab 시스템 패키지). **이 목록이 7단계 Dockerfile `apt-get` 줄의 근거.** 핀 자체는 정확(dry-run 통과). ② **phone 경로 측정 보류** — 미세조정 모델이 로컬에 없어(handoff 3-1) `engine=phone` 503. 모델 배치 후 콜드/웜 측정 완결 예정.
- **다음**: 모델 export·배치(`data/models/w2v2-jamo/`) → phone 콜드/웜 측정으로 기준선 완결 → Dockerfile 초안(단일 스테이지, mecab 시스템 패키지 포함). 완료 기준: 컨테이너에서 whisper·phone 양쪽 재현.

## 후속 +5주차 (2026-07-08 ~) — 발음형 인식기 서비스 통합 + 데모

- **한 것**: 미세조정 모델을 로컬 FastAPI에 통합(재정의 표적대로 "받침 조준 하이브리드"가 아니라 **Whisper 대체 경로**). `engine/phonetic.py`(모델 평면 자모 vs 제시어 기대발음형 정렬 → 점수·성분별 오류, `compare()`와 동일 응답 형태) + 단위 테스트 11건, `stt/phone.py`(미세조정 wav2vec2 지연로더·`available()`), `app/main.py` `/attempts`에 `engine=whisper|phone` 플래그(모델 없으면 503, 기본 whisper 하위호환), `experiments/phone_demo.py`(1주차 20건 Whisper vs wav2vec2 오탐 비교). **전체 테스트 43개 통과.** 배치·데모 절차는 `docs/colab_실행가이드.md` Step 9.
- **막힌 것**: 없음. 모델 자체는 로컬에 없어 데모는 사람 몫(Colab export→`data/models/w2v2-jamo/` 배치). 발음형 비교는 모델 없이 자모 문자열로 전수 단위테스트 완료.
- **다음(사람 몫)**: 모델 export·배치 → `phone_demo.py` 실행(오탐 비교 재현) → 데모 영상(정발음을 Whisper는 헛오류·wav2vec2는 100점 주는 컷).

## 후속 +3주차 (2026-07-08 ~) — wav2vec2 미세조정 + 최종 지표

- **한 것**: Colab T4에서 발음형 자모 CTC 인식기 미세조정(`ml/finetune_wav2vec2_colab.ipynb`) — kresnik 베이스 + 헤드 자모 39종 교체, AI Hub phones 정본 학습. **val CER 14.4%→3.9%(5 epoch)**. **핵심 성과: 정발음 오탐률 실질 52%→6%** — 거리≥1 오탐 20%를 phones 정본으로 분해하니 순수 모델오탐 6% + 화자 실제차이 14%(연음 등 실발화를 정확히 전사한 것). 자모-검출 가능한 분절음 오류 **99% 회수**. 결과: `experiments/results/finetune_results.md`. 재정의 표적(오탐 제거) 달성.
- **막힌 것**: Colab 실전 이슈 연속 — ① 한글 폴더명(`원천데이터`) zip을 `unzip`이 다른 유니코드로 풀어 경로 불일치(→ Python zipfile 추출로 해결). ② transformers 5.x API 변화(`tokenizer=`→`processing_class=`, `group_by_length` 제거). ③ T4 OOM(→ 배치 2·누적 8·긴 클립 12s 컷). ④ 무료 GPU 한도로 중단(→ 다른 계정 드라이브 공유 + 체크포인트 재개). ⑤ 평가 시 학습 체크포인트 대신 랜덤 헤드 로드로 잡음 출력(→ checkpoint에서 로드). 노트북·`docs/colab_실행가이드.md`에 전부 반영.
- **다음**: 자모-사전형 비교의 감지 상한(27%)이 다음 병목 — 음향 세밀 채점 검토(백로그). ml_report v2로 전체 서사 정리 + README 갱신.

## 후속 +2주차 (2026-07-05 ~) — 학습 데이터셋 구축 + 표적 재정의

- **한 것**: AI Hub "교육용 외국인 한국어 음성" 4종(경량)을 실발화 학습 데이터로 편입. ① 파서·인벤토리(`ml/aihub.py`·`experiments/aihub_inventory.py`): pronunciation 라벨 **20,906건/화자 9,402**, 오류 3버킷 분류, 받침 오류 실발화 1,790건(합성 20건의 90배). ② 라벨 정합성 검증: phones↔g2pk **완전일치 87.8%·자모오류율 2.63%** → 학습 타깃은 phones 정본 확정. ③ 화자(UserID) 단위 분할(`ml/dataset.py`): train 16,813/val 2,054/test 2,039, **누출 0건**, test에 평가셋 2종(eval_fp 1,517·eval_det 522) + CTC vocab 39종·데이터 검증(미등록 0·길이위반 0). ④ Colab 미세조정 노트북(`ml/finetune_wav2vec2_colab.ipynb`).
- **막힌 것 / 반전**: **원래 가정("받침 감지율 35%가 최약점")이 실데이터로 반증됨.** 실전 받침 감지율은 **73%**(합성 35%는 시스템이 아니라 TTS 한계였음). 진짜 병목은 **정발음 오탐률 52%**(정확히 발음한 발화 절반에 가짜 오류)이고, 그 **83%가 Whisper 오인식**이 원인('고저'→'고정' 등, phones 정본으로 확인). → **미세조정 표적 재정의**: "받침 recall 개선"이 아니라 **"Whisper→wav2vec2 발음형 인식기 교체로 오탐 제거"**. before 지표=오탐 52%, 라벨=phones 2만건. 근거: `experiments/results/aihub_detection_findings.md`. (1주차 교정실험·7주차 합성학습실패에 이은 '정직한 반증' 3편.)
- **다음(사람 몫)**: 프로젝트를 드라이브 업로드 → Colab GPU에서 노트북 실행(wav2vec2 CTC 미세조정) → val CER·오탐률/감지율 로그 회수 → 2차 학습 방향 결정. (오탐률 이론 바닥 ~12%: 정발음 phones vs 기대발음 87.8% 일치.)

## 후속 +1주차 (2026-07-05 ~) — 데이터 정제 파이프라인

- **한 것**: ① 오디오 품질 전수 검사(`experiments/data_quality.py`): 613건 판정(무음·클리핑·길이·PCM 해시 중복·고아/누락) → 고아 24건 격리, 중복 29건 검출. ② L2 오류 분포 문헌 조사(`docs/l2_error_distribution.md`): ICPhS 2023(5개 모어권 1,500h+) 근거 통합 혼동쌍 가중치 표. ③ 합성 v2(`synth_data.py` 개편): L2 가중 주입(받침 45%)·무효변형 2단 기각(g2pk 텍스트+PCM 해시)·3보이스·속도/피치 지터 → **297건 생성, 품질 294 pass, 청취 스팟체크 20/20**.
- **막힌 것**: ① 폴더명 변경(pronunciation-coach→sorisaegim) 후유증 — 클로드 세션 이력 소실(경로 기준 저장), venv 절대경로 파손, `attempts.audio_path` 절대경로 296건 → venv 재생성 + 상대경로 마이그레이션 + requirements에 누락 의존성(fastapi·uvicorn·scikit-learn 등) 명시로 해결. ② v1 합성에 무효변형 라벨오류 5건(치환해도 표준발음 동일: 활짝→활작) → v2 2단 필터로 차단. ③ 골드셋(1주차 녹음 20건)=attempts 1~20 동일 파일 확인 → +2주차 분할에서 학습 제외 규칙화.
- **다음**: +2주차 — AI Hub 실발화로 학습 데이터셋 구축, 실전 감지율 기준선 측정.

## 8주차 (2026-07-05 ~)

- **한 것**: ① README 전면 작성 — 문제 정의·아키텍처·기술 하이라이트 3종(1주차 교정 실험 서사, 자모 엔진, 규칙→ML 정량 비교+부정적 결과)·실행법·한계. ② 회고 글 초안(`docs/회고_초안.md`) — Whisper 교정 문제 발견→검증→대응이 중심 서사, 4막 구성(교정 실험/g2p 재적용 함정/게임바 무음/합성 학습 실패의 교훈). ③ 데모 영상 2분 촬영 대본(`docs/demo/데모대본.md`). ④ **배포 결정: 데모 영상으로 대체** — CPU Whisper 추론은 무료 티어에서 콜드스타트+지연으로 체험을 해침(세부계획의 예정된 분기). 최종 상태: pytest 32/32, 데이터 296건.
- **막힌 것**: 없음.
- **다음(사람 몫)**: 데모 영상 촬영(대본대로) → 회고 초안의 [TODO] 채워 게시 → GitHub 푸시 → 최종 커밋.

## 7주차 (2026-07-05 ~)

- **한 것**: `ml/` 패키지(특징 추출·학습·추천) + `docs/ml_report.md`. ① 오류 발생 예측(이진, user 98건 5-fold CV): 로지스틱 회귀 AUC 0.652 (베이스라인 0.5). ② **추천 품질: ML precision@5 0.6 vs 규칙 기반 0.4 (기저율 0.394)** — 포트폴리오 핵심 수치. ③ `GET /recommend` + 연습 화면 [🎯 추천 문장] 버튼으로 모델을 서비스에 연결(완료 기준 충족). ④ 합성 감지율 분석: 받침 오류 감지율 35%(초성 67%·중성 63%) — 1주차 표기 수렴 문제의 정량화, wav2vec2 조준 적용의 근거.
- **막힌 것**: 최초 설계(합성 학습→실사용 평가)는 무의미한 결과(macro-F1 0.28 vs 0.21) — **합성 오류는 무작위 주입이라 문장 특징과 독립, 학습 신호가 없다**. 실사용 데이터 CV로 재설계하고, 합성은 감지율 분석으로 역할 변경. 부정적 결과와 원인을 리포트 4장에 기록 (좋은 회고 재료).
- **다음**: 8주차 — README(아키텍처·기술 검증 서사·ML 결과), 데모 영상 2분 컷, 회고 글, 배포 여부 결정.

## 6주차 (2026-07-04 ~)

- **한 것**: ① 통계 API 3종(`/stats/summary`·`/stats/weak-jamo`·`/stats/attempts`) + 기록 화면(`stats.html`) — 요약 타일·점수 추이(라인)·유형별 평균(가로 막대)·**자주 틀리는 자모 TOP 5**(7주차 ML의 규칙 기반 대조군)·최근 시도 테이블. Chart.js는 로컬 번들(`static/vendor/`)로 오프라인 데모 가능. ② 데이터 점검 스크립트(`experiments/data_check.py`) — 현재 98건/목표 150건(65%), 33/33 문장 커버.
- **막힌 것**: 없음. (취약 자모 막대가 inline span이라 안 그려지던 것, 빈 종성 표기 '(없음)' 처리 — 스크린샷 검수로 잡음)
- **추가 (1인 진행 조정)**: 지인 테스트의 '데이터 축적' 역할을 **TTS 오발음 주입 합성**으로 대체 — 자모를 의도적으로 치환한 텍스트를 TTS로 합성하면 오류 라벨이 정확한 오발음 음성이 나온다(`experiments/synth_data.py`, 혼동 쌍 기반 + 고정 시드). 보이스 2종 × 33문장 × (정상1+변형2) = **198건 생성, 라벨 `results/synth_labels.csv`**. `attempts.source`(user/synth) 컬럼으로 구분, 통계 화면은 user만 집계. **최종 296건/목표 150건(197%)** — user 98(평가용) + synth 198(학습용), 오류 라벨 231건(substitution 206·deletion 19·insertion 6). '사용성 피드백' 역할은 본인 셀프 점검으로 축소. AI Hub 신청은 불필요 판단.
- **다음**: 7주차 ML — 합성으로 학습, 실사용으로 평가. 오류 패턴 분류 + 취약 발음 추천 + 규칙 기반(TOP 5) 대비 정량 비교.

## 5주차 (2026-07-04 ~)

- **한 것**: ① 문장 세트 33개(기존 10 + 신규 23) — 연음6·경음화5·비음화5·격음화4·받침대표음5·종합5·특수3, 유형 태그·난이도 포함. 시드를 INSERT OR IGNORE로 바꿔 기존 id 불변 재실행 가능. 검수용 `experiments/seed_review.py` 추가. ② 에러 처리 — 서버 무음 감지(400 audio_silent, 실측 -84dB 무음으로 캘리브레이션·테스트), 프론트 빈 녹음(<2KB) 가드, 네트워크 실패 시 같은 녹음 재업로드 버튼. ③ 결과 화면에 원문 표기 추가.
- **막힌 것**: g2pk 변환 의심 4건 발견(축하할 일이→'추카하 리리' 등) — 문장 교체로 해결 예정, 최종 검수는 사람 몫.
- **다음**: 발음형 전수 검수 확정 → 6주차(기록 화면·취약 발음 통계·지인 테스트).

## 4주차 (2026-07-04 ~)

- **한 것**: 프론트 완성(프레임워크 없이 HTML+JS) — 연습 화면(문장·발음형·[듣기]·MediaRecorder 녹음, 15초 자동 정지, 정지 시 자동 업로드) + 결과 화면(점수 색상 표시, `reference_pron` 음절 하이라이트 + 툴팁, 오류 목록, 재도전/다음). FastAPI에 정적 서빙 mount. 검증: webm(opus) 업로드 전 구간 통과, 헤드리스 브라우저 스크린샷 확인(`docs/img/`). **실사용 검증: 브라우저 마이크로 10문장 35회 시도 전부 정상 채점** (오독 시 89/73점 등 하이라이트 정확). **데모 영상 확보(`docs/demo/mvp_demo_2026-07-04.mp4`, 2분16초) → MVP 체크포인트 달성.**
- **막힌 것**: ① hidden 속성이 CSS display에 덮여 인디케이터 상시 노출 → `[hidden]{display:none!important}`. ② **게임바(Win+G) 녹화 중 브라우저 마이크가 완전 무음**(-84dB) — 독점 모드 해제로 안 풀림. getUserMedia에서 echoCancellation/noiseSuppression/autoGainControl을 꺼 원시 캡처로 바꾸니 해결. 발음 평가엔 무가공 오디오가 오히려 적합.
- **다음**: 5주차 — 유형별 30문장 + 하이라이트 개선 + 에러 처리(무음·짧은 녹음 거부). 1주차 결정에 따라 축소 1순위 주간.

## 3주차 (2026-07-04 ~)

- **한 것**: FastAPI 백엔드 완성 — `app/`(API·SQLite) · `stt/`(Whisper small 래퍼) · `tts/`(Edge-TTS 캐싱) 분리, 시드 10문장(=1주차 실험 문장, 발음형 자동 계산). `GET /sentences` · `GET /sentences/{id}/audio`(캐시 0.42s→0.02s) · `POST /attempts`(업로드→ffmpeg→Whisper→엔진→DB, 원본 보관) 모두 `docs/api_spec.md` 스펙대로. 수동 테스트: 1주차 녹음 20건 전부 통과, **평균 2.1s/최대 5.0s (목표 10초 이내 여유)**, 점수는 2주차 엔진 검증과 동일. 오류 응답(404/400/422)도 스펙대로.
- **막힌 것**: 8000 포트 선점(다른 프로세스) → 8765로 우회. 그 외 없음 — 스펙을 미리 확정한 덕에 API 계층은 엔진 dict를 그대로 싣기만 하면 됐다.
- **다음**: 4주차 — 프론트(HTML+JS, MediaRecorder) + MVP. 연습 화면(듣기/녹음) → 결과 화면(점수·하이라이트). 서버에 정적 파일 서빙 추가.

## 2주차 (2026-07-04 ~)

- **한 것**: ① 발음 비교 엔진 v1 완성(`engine/` 순수 패키지: 자모 분해·편집거리 정렬·점수/오류 리포트, g2pk 지연 임포트로 무의존 동작 가능) + pytest 32케이스 통과. ② 1주차 녹음 20개 엔진 통과 — 정상 10개 전원 100점, Whisper 보존 오류 5건 자모 단위 정확 검출. ③ wav2vec2 검증: kresnik 모델이 **비음화 미적용을 감지**(국물이 vs 국무리 — Whisper 0/3이던 영역), 단 유음화·경음화 미감지 + 정상 발음 오인식 5/10. ④ API 스펙 확정(`docs/api_spec.md`).
- **막힌 것**: ① 인식 텍스트에 g2p를 재적용하면 음운 규칙이 되살아나 오류가 지워짐 → `recognized_is_phonetic` 파라미터로 Whisper/음소 경로 분리 (테스트가 잡아준 설계 결정). ② kresnik도 표기 학습이라 표기 수렴 오류는 부분 감지 — MVP는 Whisper 단독, wav2vec2는 7주차에 규칙 위치 조준 검사로 재검토. ③ espeak IPA 모델은 네이티브 espeak-ng 의존성으로 보류.
- **다음**: 3주차 — FastAPI 파이프라인 (`app/`·SQLite 스키마·문장/TTS/평가 API). 스펙은 `docs/api_spec.md` 그대로.

## 1주차 (2026-07-04 ~)

- **한 것**: 환경 세팅(.venv, openai-whisper, edge-tts, ffmpeg) + 검증 스크립트 3종 작성. **핵심 실험 완료**: 육성 녹음 20개(정상 10 + 오발음 10)로 교정 실험 실행, 발음형 기준 재판정까지 마침. 결정 확정 — Whisper `small`(t=0.0) 유지 + 비교는 발음형 공간 + 2주차에 wav2vec2 음소 인식 검증 추가(하이브리드). 상세는 `experiments\whisper_교정실험.md`.
- **막힌 것**: ① g2pk 설치 실패(python-mecab-ko가 MSVC Build Tools 요구) — 발음형 비교의 전제라 필수로 격상. → **해결(2026-07-04)**: C++ 워크로드 추가 + mecab-ko-msvc를 C:\mecab에 배치 + libmecab.dll을 site-packages에 복사. 재현 절차는 `experiments\README.md`. `g2p_check.py`로 8/8 규칙 변환 일치 검증 완료. ② 발음규칙 미적용형 오류(비음화 등)는 표기 수렴 때문에 텍스트 STT로 원리적 감지 불가 — 실험 전엔 몰랐던 구조적 한계, wav2vec2 추가의 직접 근거.
- **다음**: 2주차 — wav2vec2 후보 검증(1주차 녹음 20개 재사용, wrong_01/03/05 감지가 합격 기준) → 발음 비교 엔진 v1.
