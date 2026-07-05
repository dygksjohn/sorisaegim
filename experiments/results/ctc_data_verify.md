# CTC 학습 데이터 로컬 검증 (+2주차 작업 5)

> vocab 39종. 오디오 표본 300건(train). Colab 투입 전 사전점검.

## 결과

- vocab 커버리지(val+test): 미등록 자모 **0종** ✅
- 오디오 디코딩 실패: 0/300 ✅
- CTC 길이 위반(프레임<라벨): 0/300 ✅ (최소 프레임/라벨 비율 3.1)
- 라벨 인코딩 왕복 일치: 300/300 ✅
- 오디오 길이(초): 중앙값 2.8, 최소 0.5, 최대 69.9

## Colab 학습 준비물

- 베이스: `kresnik/wav2vec2-large-xlsr-korean` (2주차 검증 자산)
- vocab: `data/aihub/splits/vocab.json` (PAD=0=CTC blank, UNK=1)
- 데이터: train/val jsonl (wav_path + 공백구분 자모 label)
- 평가: eval_fp(오탐률 before 52%) / eval_det(감지) — 화자 분리 확인됨