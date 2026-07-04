/* 학습 기록 화면 (6주차).
 * 단일 측정값(점수) 차트라 색은 앱 인디고 한 색조로 통일 — 범례 불필요.
 * 취약 자모 집계는 7주차 ML의 규칙 기반 대조군.
 */

const INDIGO = "#4f46e5";
const INDIGO_SOFT = "rgba(79, 70, 229, 0.12)";
const GRID = "#f0f1f5";
const INK_MUTED = "#6b7280";

const COMPONENT_KO = {
  choseong: "초성",
  jungseong: "중성",
  jongseong: "받침",
  char: "문자",
};

Chart.defaults.font.family =
  '"Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif';
Chart.defaults.color = INK_MUTED;

function scoreClass(score) {
  if (score >= 90) return "score-good";
  if (score >= 70) return "score-mid";
  return "score-bad";
}

function describeError(e) {
  const comp = COMPONENT_KO[e.component] || e.component;
  const jamo = (x) => (x ? x : "(없음)"); // 빈 종성 토큰은 '(없음)'으로 표기
  if (e.error_type === "substitution")
    return `${comp} <b>${jamo(e.expected)}</b> → <b>${jamo(e.actual)}</b>`;
  if (e.error_type === "deletion") return `${comp} <b>${jamo(e.expected)}</b> 누락`;
  return `${comp} <b>${jamo(e.actual)}</b> 잉여`;
}

async function main() {
  const [summary, weak, recent] = await Promise.all([
    fetch("/stats/summary").then((r) => r.json()),
    fetch("/stats/weak-jamo?top=5").then((r) => r.json()),
    fetch("/stats/attempts?limit=20").then((r) => r.json()),
  ]);

  // ---- 요약 타일 ----
  document.getElementById("tile-total").textContent = summary.total;
  document.getElementById("tile-avg").textContent = summary.avg_score ?? "–";
  document.getElementById("tile-errors").textContent = weak.total_errors;

  // ---- 점수 추이 (라인) ----
  new Chart(document.getElementById("chart-trend"), {
    type: "line",
    data: {
      labels: summary.trend.map((_, i) => i + 1),
      datasets: [{
        data: summary.trend.map((t) => t.score),
        borderColor: INDIGO,
        backgroundColor: INDIGO_SOFT,
        borderWidth: 2,
        pointRadius: summary.trend.length > 60 ? 0 : 2.5,
        pointHoverRadius: 5,
        fill: true,
        tension: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => {
              const t = summary.trend[items[0].dataIndex];
              return `${items[0].dataIndex + 1}번째 시도 · ${t.created_at.slice(0, 16).replace("T", " ")}`;
            },
            label: (item) => `${item.parsed.y}점`,
          },
        },
      },
      scales: {
        y: { min: 0, max: 100, grid: { color: GRID }, ticks: { stepSize: 25 } },
        x: { grid: { display: false }, title: { display: true, text: "시도 순서" },
             ticks: { maxTicksLimit: 10 } },
      },
    },
  });

  // ---- 유형별 평균 (가로 막대) ----
  new Chart(document.getElementById("chart-types"), {
    type: "bar",
    data: {
      labels: summary.by_type.map((t) => `${t.type} (${t.n})`),
      datasets: [{
        data: summary.by_type.map((t) => t.avg_score),
        backgroundColor: INDIGO,
        borderRadius: 4,
        barThickness: 16,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (item) => `평균 ${item.parsed.x}점` } },
      },
      scales: {
        x: { min: 0, max: 100, grid: { color: GRID } },
        y: { grid: { display: false } },
      },
    },
  });

  // ---- 취약 자모 TOP 5 ----
  const ul = document.getElementById("weak-list");
  if (!weak.weak_jamo.length) {
    document.getElementById("weak-empty").hidden = false;
  }
  const maxCount = weak.weak_jamo[0]?.count || 1;
  weak.weak_jamo.forEach((e, i) => {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="weak-rank">${i + 1}</span>` +
      `<span class="weak-desc">${describeError(e)}</span>` +
      `<span class="weak-bar-track"><span class="weak-bar" style="width:${(e.count / maxCount) * 100}%"></span></span>` +
      `<span class="weak-count">${e.count}회</span>`;
    ul.appendChild(li);
  });

  // ---- 최근 시도 테이블 ----
  const tbody = document.querySelector("#attempts-table tbody");
  for (const a of recent.attempts) {
    const tr = document.createElement("tr");
    const time = a.created_at.slice(5, 16).replace("T", " ");
    tr.innerHTML =
      `<td>${time}</td><td>${a.text}</td><td>${a.type}</td>` +
      `<td class="${scoreClass(a.score)}">${a.score}</td><td>${a.stt_text}</td>`;
    tbody.appendChild(tr);
  }
}

main().catch(() => {
  document.getElementById("tile-total").textContent = "!";
  document.querySelector(".stats-main").insertAdjacentHTML(
    "beforeend", '<p class="status">기록을 불러오지 못했습니다. 서버 상태를 확인해 주세요.</p>');
});
