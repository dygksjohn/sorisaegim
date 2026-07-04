/* 소리새김 프론트 (4주차 MVP) — 프레임워크 없이 화면 2개.
 * 연습: 문장 표시 → TTS 듣기 → MediaRecorder 녹음 → 정지 시 자동 업로드
 * 결과: 점수 + reference_pron 음절 하이라이트(errors[].position) + 재도전/다음
 * API: docs/api_spec.md
 */

const $ = (id) => document.getElementById(id);

const state = {
  sentences: [],
  index: 0,
  recorder: null,
  chunks: [],
  timerId: null,
  startedAt: 0,
  lastBlob: null, // 업로드 실패 시 재시도용
};

const MIN_BLOB_BYTES = 2000; // 이보다 작으면 사실상 빈 녹음 (실측: 빈 webm ≈ 1KB)

const COMPONENT_KO = {
  choseong: "초성",
  jungseong: "중성",
  jongseong: "받침",
  char: "문자",
};

const MAX_RECORD_SEC = 15;

// ---------- 문장 ----------

function currentSentence() {
  return state.sentences[state.index];
}

function showPractice() {
  const s = currentSentence();
  $("sentence-type").textContent = s.type;
  $("sentence-difficulty").textContent = "난이도 " + "★".repeat(s.difficulty);
  $("sentence-counter").textContent = `${state.index + 1} / ${state.sentences.length}`;
  $("sentence-text").textContent = s.text;
  $("sentence-pron").textContent = s.pron;
  $("status").textContent = "";
  $("btn-retry-upload").hidden = true;
  $("result-view").hidden = true;
  $("practice-view").hidden = false;
}

async function loadSentences() {
  const res = await fetch("/sentences");
  if (!res.ok) throw new Error("문장 목록을 불러오지 못했습니다");
  state.sentences = (await res.json()).sentences;
  if (!state.sentences.length) throw new Error("등록된 문장이 없습니다");
  showPractice();
}

// ---------- TTS 듣기 ----------

$("btn-listen").addEventListener("click", () => {
  const audio = $("tts-audio");
  audio.src = `/sentences/${currentSentence().id}/audio`;
  audio.play().catch(() => {
    $("status").textContent = "음원을 재생할 수 없습니다.";
  });
});

// ---------- 녹음 ----------

function pickMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

function extFor(mime) {
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "m4a";
  return "bin";
}

$("btn-record").addEventListener("click", async () => {
  let stream;
  try {
    // 원시 캡처: 브라우저 음성 처리(에코 제거 등)를 끈다.
    // 발음 평가엔 가공 없는 소리가 낫고, 화면 녹화 도구와의
    // 마이크 동시 캡처 충돌(무음 스트림)도 피할 수 있다.
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
  } catch (e) {
    $("status").textContent =
      "마이크 권한이 필요합니다. 브라우저 주소창의 권한 설정을 확인해 주세요.";
    return;
  }

  const mime = pickMimeType();
  state.chunks = [];
  state.recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  state.recorder.ondataavailable = (e) => e.data.size && state.chunks.push(e.data);
  state.recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(state.chunks, { type: state.recorder.mimeType });
    if (blob.size < MIN_BLOB_BYTES) {
      $("status").textContent = "녹음이 되지 않았습니다. 마이크를 확인하고 다시 시도해 주세요.";
      return;
    }
    upload(blob);
  };
  state.recorder.start();

  state.startedAt = Date.now();
  $("rec-time").textContent = "0:00";
  $("rec-indicator").hidden = false;
  $("btn-record").hidden = true;
  $("btn-stop").hidden = false;
  $("btn-listen").disabled = true;
  $("status").textContent = "";

  state.timerId = setInterval(() => {
    const sec = Math.floor((Date.now() - state.startedAt) / 1000);
    $("rec-time").textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
    if (sec >= MAX_RECORD_SEC) stopRecording(); // 과도한 녹음 방지
  }, 250);
});

function stopRecording() {
  if (state.recorder && state.recorder.state === "recording") state.recorder.stop();
  clearInterval(state.timerId);
  $("rec-indicator").hidden = true;
  $("btn-stop").hidden = true;
  $("btn-record").hidden = false;
  $("btn-listen").disabled = false;
}

$("btn-stop").addEventListener("click", stopRecording);

// ---------- 업로드 & 채점 ----------

async function upload(blob) {
  state.lastBlob = blob;
  $("loading").hidden = false;
  $("btn-record").disabled = true;
  $("btn-retry-upload").hidden = true;

  const form = new FormData();
  form.append("sentence_id", currentSentence().id);
  form.append("audio", blob, `rec.${extFor(blob.type)}`);

  try {
    const res = await fetch("/attempts", { method: "POST", body: form });
    const body = await res.json();
    if (!res.ok) {
      // 서버 판정 오류(무음·짧음 등)는 재녹음이 답 — 재시도 버튼은 안 띄운다
      $("status").textContent = body.message || body.error || "요청이 실패했습니다.";
      return;
    }
    state.lastBlob = null;
    showResult(body);
  } catch (e) {
    // 네트워크 실패는 같은 녹음으로 재시도 가능
    $("status").textContent = "업로드에 실패했습니다. 네트워크를 확인해 주세요.";
    $("btn-retry-upload").hidden = false;
  } finally {
    $("loading").hidden = true;
    $("btn-record").disabled = false;
  }
}

$("btn-retry-upload").addEventListener("click", () => {
  if (state.lastBlob) upload(state.lastBlob);
});

// ---------- 결과 화면 ----------

function scoreClass(score) {
  if (score >= 90) return "good";
  if (score >= 70) return "mid";
  return "bad";
}

/* reference_pron을 음절 span으로 렌더링.
 * errors[].position은 공백·문장부호 제외 음절 인덱스 (api_spec.md). */
function renderHighlight(pron, errors) {
  const byPos = new Map();
  for (const e of errors) {
    if (!byPos.has(e.position)) byPos.set(e.position, []);
    byPos.get(e.position).push(e);
  }

  const wrap = $("highlight");
  wrap.textContent = "";
  const skip = /[\s.,!?~'"“”‘’·…\-]/;
  let pos = 0;
  for (const ch of pron) {
    if (skip.test(ch)) {
      wrap.appendChild(document.createTextNode(ch));
      continue;
    }
    const span = document.createElement("span");
    span.className = "syl";
    span.textContent = ch;
    const errs = byPos.get(pos);
    if (errs) {
      span.classList.add("syl-error");
      span.title = errs
        .map((e) => `${COMPONENT_KO[e.component]} — 기대: ${e.expected || "없음"} / 발음됨: ${e.actual || "없음"}`)
        .join("\n");
    }
    wrap.appendChild(span);
    pos += 1;
  }
}

function renderErrorList(errors) {
  const ul = $("error-list");
  ul.textContent = "";
  for (const e of errors) {
    const li = document.createElement("li");
    const where = e.syllable ? `'${e.syllable}'` : `${e.position + 1}번째 음절 근처`;
    li.innerHTML =
      `${where} ${COMPONENT_KO[e.component]}: ` +
      `기대 <b>${e.expected || "없음"}</b> → 발음됨 <b>${e.actual || "없음"}</b>`;
    ul.appendChild(li);
  }
}

function showResult(body) {
  const a = body.analysis;
  const scoreEl = $("score");
  scoreEl.textContent = a.score;
  scoreEl.className = `score ${scoreClass(a.score)}`;
  $("ref-text").textContent = a.reference;
  renderHighlight(a.reference_pron, a.errors);
  $("recognized").textContent = body.stt.text;
  renderErrorList(a.errors);
  $("practice-view").hidden = true;
  $("result-view").hidden = false;
}

$("btn-retry").addEventListener("click", showPractice);
$("btn-next").addEventListener("click", () => {
  state.index = (state.index + 1) % state.sentences.length;
  showPractice();
});

// ---------- 시작 ----------

loadSentences().catch((e) => {
  $("sentence-text").textContent = "서버에 연결할 수 없습니다.";
  $("status").textContent = e.message;
});
