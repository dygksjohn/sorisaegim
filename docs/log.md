# 주간 로그

> 운영 원칙: 주당 3줄 — 한 것 / 막힌 것 / 다음. 회고 글 재료.

## 2주차 (2026-07-04 ~)

- **한 것**: ① 발음 비교 엔진 v1 완성(`engine/` 순수 패키지: 자모 분해·편집거리 정렬·점수/오류 리포트, g2pk 지연 임포트로 무의존 동작 가능) + pytest 32케이스 통과. ② 1주차 녹음 20개 엔진 통과 — 정상 10개 전원 100점, Whisper 보존 오류 5건 자모 단위 정확 검출. ③ wav2vec2 검증: kresnik 모델이 **비음화 미적용을 감지**(국물이 vs 국무리 — Whisper 0/3이던 영역), 단 유음화·경음화 미감지 + 정상 발음 오인식 5/10. ④ API 스펙 확정(`docs/api_spec.md`).
- **막힌 것**: ① 인식 텍스트에 g2p를 재적용하면 음운 규칙이 되살아나 오류가 지워짐 → `recognized_is_phonetic` 파라미터로 Whisper/음소 경로 분리 (테스트가 잡아준 설계 결정). ② kresnik도 표기 학습이라 표기 수렴 오류는 부분 감지 — MVP는 Whisper 단독, wav2vec2는 7주차에 규칙 위치 조준 검사로 재검토. ③ espeak IPA 모델은 네이티브 espeak-ng 의존성으로 보류.
- **다음**: 3주차 — FastAPI 파이프라인 (`app/`·SQLite 스키마·문장/TTS/평가 API). 스펙은 `docs/api_spec.md` 그대로.

## 1주차 (2026-07-04 ~)

- **한 것**: 환경 세팅(.venv, openai-whisper, edge-tts, ffmpeg) + 검증 스크립트 3종 작성. **핵심 실험 완료**: 육성 녹음 20개(정상 10 + 오발음 10)로 교정 실험 실행, 발음형 기준 재판정까지 마침. 결정 확정 — Whisper `small`(t=0.0) 유지 + 비교는 발음형 공간 + 2주차에 wav2vec2 음소 인식 검증 추가(하이브리드). 상세는 `experiments\whisper_교정실험.md`.
- **막힌 것**: ① g2pk 설치 실패(python-mecab-ko가 MSVC Build Tools 요구) — 발음형 비교의 전제라 필수로 격상. → **해결(2026-07-04)**: C++ 워크로드 추가 + mecab-ko-msvc를 C:\mecab에 배치 + libmecab.dll을 site-packages에 복사. 재현 절차는 `experiments\README.md`. `g2p_check.py`로 8/8 규칙 변환 일치 검증 완료. ② 발음규칙 미적용형 오류(비음화 등)는 표기 수렴 때문에 텍스트 STT로 원리적 감지 불가 — 실험 전엔 몰랐던 구조적 한계, wav2vec2 추가의 직접 근거.
- **다음**: 2주차 — wav2vec2 후보 검증(1주차 녹음 20개 재사용, wrong_01/03/05 감지가 합격 기준) → 발음 비교 엔진 v1.
