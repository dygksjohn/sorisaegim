# 소리새김 — 배포 7단계 컨테이너 이미지 (초안 v1)
#
# 빌드 (프로젝트 루트에서):
#   docker build -t sorisaegim:dev .
# 실행:
#   docker run --rm -p 8000:8000 -v sorisaegim-data:/app/data sorisaegim:dev
#   → http://localhost:8000
#
# 설계 메모
# - 2스테이지. python-mecab-ko(g2pk 의존)가 소스 빌드라 g++가 필요한데,
#   그 빌드툴을 런타임 이미지에 남기지 않는다.
# - torch는 CPU 휠을 index-url로 못박아 먼저 깐다. requirements.txt의
#   --extra-index-url만으로는 PyPI의 GPU 빌드가 선택될 수 있고, 그러면
#   nvidia 런타임 패키지까지 딸려와 이미지가 수 GB 붇는다.
# - Whisper small(약 460MB)과 nltk cmudict를 빌드 시점에 받아 굽는다.
#   기동 후 첫 요청에서 네트워크를 타지 않게 하려는 것 — 오프라인 데모와
#   콜드스타트 측정(기준선 4.61s)의 재현성을 위해서다.
# - 미세조정 wav2vec2(w2v2-jamo)는 굽지 않는다. 볼륨으로 넣거나
#   PHONE_MODEL_DIR로 경로를 덮어쓴다. 배치 방식은 docs/handoff_배포운영_v1.md 3-1.

# ---------- 1) builder ----------
FROM python:3.13-slim AS builder

# build-essential: python-mecab-ko의 pybind11 확장 컴파일
# mecab, libmecab-dev: 그 확장이 링크할 mecab 본체와 mecab-config.
#   g++만 있으면 "RuntimeError: mecab-config not found"로 죽는다 —
#   Windows에서 C:\mecab 를 따로 깔아야 했던 것과 같은 이유다.
#   한국어 사전(mecab-ko-dic)은 pip의 python-mecab-ko-dic이 들고 온다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        mecab \
        libmecab-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip

# torch를 CPU 휠로 먼저 고정 (아래 requirements 설치 때 이미 충족된 것으로 처리됨)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.12.1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 런타임에 네트워크를 타지 않도록 미리 받아 둔다
ENV NLTK_DATA=/opt/nltk_data \
    XDG_CACHE_HOME=/opt/cache
RUN python -m nltk.downloader -d /opt/nltk_data cmudict \
    && python -c "import whisper; whisper.load_model('small')"

# 스모크 체크 — g2pk가 mecab 사전을 실제로 물었는지 빌드 시점에 확인한다.
# 런타임 첫 요청에서 터지면 원인 추적이 훨씬 비싸다.
RUN python -c "from g2pk import G2p; assert G2p()('밥을') == '바블', G2p()('밥을')"

# ---------- 2) runtime ----------
FROM python:3.13-slim

# ffmpeg: 업로드 오디오 디코딩(whisper.audio.load_audio)
# libgomp1: torch 런타임 의존
# libmecab2: builder에서 컴파일한 mecab 확장이 링크한 공유 라이브러리.
#   빌드툴(build-essential·libmecab-dev)은 남기지 않고 런타임 .so만 가져온다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
        libmecab2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/nltk_data /opt/nltk_data
COPY --from=builder /opt/cache /opt/cache

ENV PATH="/opt/venv/bin:$PATH" \
    NLTK_DATA=/opt/nltk_data \
    XDG_CACHE_HOME=/opt/cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PHONE_MODEL_DIR=/app/data/models/w2v2-jamo

WORKDIR /app

# 코드만 넣는다. data/ 는 .dockerignore로 제외 — AI Hub 데이터 재배포 금지
# 규칙 때문이기도 하고, DB·녹음은 볼륨에 있어야 재시작에도 남기 때문이다.
COPY app/ ./app/
COPY engine/ ./engine/
COPY ml/ ./ml/
COPY stt/ ./stt/
COPY tts/ ./tts/
COPY static/ ./static/

# 비루트 실행. data/는 볼륨 마운트 지점이라 미리 만들고 소유권을 넘긴다.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/sentences', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
