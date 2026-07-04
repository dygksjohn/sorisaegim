# experiments — 1주차 기술 검증

[주차별_세부계획_v1.md](../docs/주차별_세부계획_v1.md) 1주차 작업의 실행 폴더.

## 사전 준비 (완료됨)

- Python 가상환경: 프로젝트 루트 `.venv\` (Python 3.13)
- 설치 패키지: `openai-whisper`, `edge-tts` (`requirements.txt` 참고)
- `ffmpeg`: winget(Gyan.FFmpeg)으로 설치, PATH 등록됨

## 파일 구성

| 파일 | 용도 |
|---|---|
| `stt_check.py` | 오디오 → Whisper 인식 텍스트. 모델별(`small`/`medium`) 결과·처리시간 비교 |
| `tts_check.py` | 문장 → Edge-TTS mp3 생성 (`tts_out\`에 저장) |
| `correction_experiment.py` | **1주차 핵심 실험**: 녹음 일괄 처리 → 교정 여부 자동 판정 → 결과 표 생성 |
| `whisper_교정실험.md` | 실험 설계·체크리스트·결과·**결정** 기록 문서 |
| `g2p_check.py` | g2pk 표기→발음형 변환 품질 검증 (8규칙) |
| `wav2vec2_check.py` | **2주차 검증**: CTC 인식기가 규칙 미적용형 오류를 듣는지 — 정상/오발음 쌍 비교 |
| `engine_on_week1.py` | 1주차 인식 결과를 비교 엔진(`engine/`)에 통과시켜 점수 직관 검증 |
| `recordings\manifest.csv` | 녹음 파일 목록 (정답 문장 / 의도 발음 / 메모) |
| `results\` | 실험 결과 자동 생성 (md + csv) |
| `tts_out\` | TTS 생성 음원 |

## 사용법 (CMD, 프로젝트 루트에서)

```cmd
:: TTS 음질 확인 (기본 5문장 생성)
.venv\Scripts\python.exe experiments\tts_check.py
.venv\Scripts\python.exe experiments\tts_check.py --voice ko-KR-InJoonNeural

:: STT 단건 확인
.venv\Scripts\python.exe experiments\stt_check.py 녹음.wav --models small,medium

:: 교정 실험 (recordings\ 에 녹음 + manifest.csv 작성 후)
.venv\Scripts\python.exe experiments\correction_experiment.py
```

## 남은 수동 작업 (사람이 해야 함)

1. `whisper_교정실험.md`의 오발음 설계표 7~10번 채우기
2. 정상 발음 10개 + 의도적 오발음 10개 **직접 녹음** → `recordings\`에 저장
3. `manifest.csv` 작성 → `correction_experiment.py` 실행
4. 결과를 보고 `whisper_교정실험.md` 4번 섹션에 **결정** 기록
5. `tts_out\`의 mp3를 직접 들어보고 Edge-TTS 음질 판단

## 알려진 이슈

- **g2pk 변환 버그 패턴** (5주차 검수에서 발견): ① 'ㄴ첨가+ㅍ 연음' 조합에서 ㅍ이 ㅂ으로 나옴
  (꽃잎이→꼰니**비**, 나뭇잎이→나문니**비** — 규범은 [꼰니피], [나문니피]). ② 'ㄹ 관형형+일' 유음화 누락
  (축하할 일이→추카**하 리**리). ③ 일부 어미 연음 오류(늦었다→느**섣**따). → 대응: 시드 문장은
  `experiments\seed_review.py`로 전수 검수하고, 걸리는 문장은 교체한다 (라이브러리 수정보다 빠름).

- 스모크 테스트 결과 (2026-07-04): Edge-TTS 음원 → Whisper `small` 인식 정확, CPU 기준 문장당 4.5~6.1초.
- **espeak IPA 음소 모델 보류** (`facebook/wav2vec2-lv-60-espeak-cv-ft`): 토크나이저가 `phonemizer`(설치됨) +
  네이티브 espeak-ng을 요구. MSI 설치가 미완료 상태 — 7주차에 재검토 시:
  ```cmd
  :: 관리자 권한 CMD에서
  msiexec /i espeak-ng.msi /qn /norestart
  :: (MSI: https://github.com/espeak-ng/espeak-ng/releases 의 espeak-ng.msi)
  :: 설치 후 환경변수: set PHONEMIZER_ESPEAK_LIBRARY=C:\Program Files\eSpeak NG\libespeak-ng.dll
  ```

### g2pk Windows 설치 (2026-07-04 해결 — 재현 절차)

g2pk의 의존성 `python-mecab-ko`는 ① MSVC 컴파일러와 ② `C:\mecab`의 네이티브 mecab-ko 라이브러리를 요구한다.
크로스플랫폼 대안 `g2pkk`도 Windows에선 컴파일이 필요한 `eunjeon`을 요구해 우회 불가 — 아래가 정공법.

1. **VS Build Tools + C++ 워크로드**: `winget install Microsoft.VisualStudio.2022.BuildTools`는 워크로드 없는
   빈 껍데기만 설치한다. C++ 워크로드는 별도로 추가해야 하며, `--quiet` 모드는 87 오류로 실패하니 `--passive` 사용
   (관리자 권한 필요):
   ```cmd
   "C:\Program Files (x86)\Microsoft Visual Studio\Installer\setup.exe" modify --installPath "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools" --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --norestart
   ```
2. **mecab-ko 네이티브 라이브러리**: [Pusnow/mecab-ko-msvc](https://github.com/Pusnow/mecab-ko-msvc/releases)에서
   `mecab-ko-windows-x64.zip`을 받아 `C:\mecab`에 풀고, 빌드가 루트에서 헤더를 찾으므로
   `include\mecab.h`와 `lib\libmecab.lib`를 `C:\mecab` 루트에도 복사한다.
3. `pip install g2pk` (이제 컴파일 성공)
4. **DLL 로드 오류 대응**: `import` 시 `DLL load failed while importing _mecab`가 나면
   `C:\mecab\bin\libmecab.dll`을 `.venv\Lib\site-packages\`에 복사한다 (확장 모듈 `_mecab.pyd` 옆).
   **venv를 다시 만들면 이 복사도 다시 해야 한다.**

검증: `g2p_check.py` 실행 → 8/8 규칙(비음화·유음화·경음화·격음화·구개음화·연음·겹받침) 변환 일치 확인됨.
