# API 스펙 v1 (2주차 확정 — 이후 프론트·백엔드는 이 문서만 본다)

> 원칙: `POST /attempts` 응답의 `analysis`는 **엔진 `compare()` 반환 dict를 그대로** 싣는다.
> 엔진이 바뀌어도 API 계층은 손대지 않는다 (결합도 0 — 기획서 3-1).
> 서버: FastAPI (3주차) · 인증 없음(MVP 범위 제외) · 모든 응답 UTF-8 JSON (오디오 제외).

## 1. GET /sentences — 연습 문장 목록

쿼리: `type`(선택, 예: `비음화`) · `difficulty`(선택, 1~3)

```json
{
  "sentences": [
    {
      "id": 1,
      "text": "국물이 정말 시원하다",
      "pron": "궁무리 정말 시원하다",
      "type": "비음화",
      "difficulty": 1
    }
  ]
}
```

- `pron`은 g2pk 변환 결과를 시드 시점에 저장한 것 (5주차에 30문장 눈 검수).

## 2. GET /sentences/{id}/audio — TTS 표준 발음 음원

- 응답: `audio/mpeg` (mp3 바이너리)
- 서버 동작: 최초 호출 시 Edge-TTS 생성 후 파일 캐싱, 이후 캐시 반환 (3주차)
- 404: 문장 없음

## 3. POST /attempts — 발음 평가 (핵심)

요청: `multipart/form-data`
| 필드 | 타입 | 설명 |
|---|---|---|
| `sentence_id` | int | 연습 문장 id |
| `audio` | file | 브라우저 녹음 (webm/ogg/wav — 서버가 ffmpeg으로 변환) |

응답 200:

```json
{
  "attempt_id": 42,
  "sentence_id": 1,
  "stt": {
    "engine": "whisper-small",
    "text": "궁무리 정말 시원하다",
    "elapsed_ms": 2100
  },
  "analysis": {
    "score": 93,
    "reference": "국물이 정말 시원하다",
    "reference_pron": "궁무리 정말 시원하다",
    "recognized": "국무리 정말 시원하다",
    "recognized_pron": "궁무리 정말 시원하다",
    "errors": [
      {
        "type": "substitution",
        "position": 0,
        "syllable": "궁",
        "component": "jongseong",
        "expected": "ㅇ",
        "actual": "ㄱ"
      }
    ]
  },
  "created_at": "2026-07-11T21:00:00+09:00"
}
```

### `analysis.errors[]` 필드 (= 엔진 오류 리포트)

| 필드 | 값 | 설명 |
|---|---|---|
| `type` | `substitution` \| `deletion` \| `insertion` | 대체 / 누락 / 잉여 |
| `position` | int | `reference_pron`에서 공백 제외 음절 인덱스 (하이라이트 위치) |
| `syllable` | str \| null | 해당 음절 문자. insertion이면 null |
| `component` | `choseong` \| `jungseong` \| `jongseong` \| `char` | 초/중/종성 구분 |
| `expected` | str \| null | 기대 자모 (빈 종성은 `""`, insertion이면 null) |
| `actual` | str \| null | 발음된 자모 (deletion이면 null) |

프론트 하이라이트 규칙: `reference_pron`을 음절 단위로 렌더링하고, `errors[].position` 음절에
마킹 + 툴팁 "기대: {expected} / 발음됨: {actual}" (5주차).

### 오류 응답

| 상태 | 조건 | 본문 |
|---|---|---|
| 400 | 무음, 1초 미만, 디코딩 불가 | `{"error": "audio_too_short", "message": "..."}` |
| 404 | sentence_id 없음 | `{"error": "sentence_not_found"}` |
| 422 | STT 결과가 빈 문자열 | `{"error": "stt_empty", "message": "다시 녹음해 주세요"}` |

## 4. 확장 예약 (v2 — 7주차 하이브리드)

- `stt.engine`에 `wav2vec2-*`가 추가될 수 있다. 음소 인식 경로의 분석은
  `analysis`와 같은 스키마로 `analysis_phonetic` 키에 별도 탑재한다 (기존 키 불변).
- `GET /stats/weak-jamo` (6주차): attempts의 `errors` 집계 — 자주 틀리는 자모 TOP 5.

---
*확정일: 2026-07-04 (2주차 결정 포인트) · 변경 시 이 문서를 먼저 고치고 코드가 따라간다.*
