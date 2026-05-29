const ENTITY_REFRESH_MS = 120000;
let entityChart;

const entityIds = [
    "theme-toggle", "entity-refresh-state", "entity-error-banner", "entity-title",
    "entity-lede", "entity-rank-pill", "entity-risk-pill", "entity-forecast-pill",
    "entity-unit", "entity-generated", "entity-latest", "entity-trend",
    "entity-risk", "entity-latest-note", "entity-score", "entity-score-note",
    "entity-forecast-24h", "entity-forecast-note", "entity-utilization",
    "entity-utilization-note", "entity-window", "entity-chart", "entity-chart-empty",
    "entity-rank", "entity-rank-note", "entity-average-rank",
    "entity-average-rank-note", "entity-volatility", "entity-volatility-note",
    "entity-summary", "entity-method", "entity-forecast-7d", "entity-risk-driver",
    "entity-high", "entity-low", "entity-related", "entity-chart-copy",
];
const entityEl = Object.fromEntries(entityIds.map((id) => [id, document.getElementById(id)]));

function initEntityTheme() {
    const stored = localStorage.getItem("grid-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored || (prefersDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    entityEl["theme-toggle"].textContent = theme === "dark" ? "Light" : "Dark";
}

function toggleEntityTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("grid-theme", next);
    entityEl["theme-toggle"].textContent = next === "dark" ? "Light" : "Dark";
    if (entityChart) entityChart.update();
}

function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "...";
    return Number(value).toLocaleString(undefined, {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
    });
}

function formatMW(value, digits = 2) {
    return `${formatNumber(value, digits)} MW`;
}

function formatTimestamp(value) {
    if (!value) return "...";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function labelize(value) {
    return String(value || "unknown").replaceAll("_", " ");
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#039;",
    }[char]));
}

function badgeClassForRisk(value) {
    if (["critical", "overload_risk", "elevated", "warning", "weak"].includes(value)) return "red";
    if (["watch", "stressed"].includes(value)) return "amber";
    if (["normal", "stable", "strong"].includes(value)) return "green";
    return "blue";
}

function setEntityBanner(message) {
    entityEl["entity-error-banner"].textContent = message || "";
    entityEl["entity-error-banner"].classList.toggle("visible", Boolean(message));
}

async function fetchEntityJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed: ${url}`);
    return payload;
}

function renderEntityChart(payload) {
    const history = payload.history || [];
    const hasPoints = history.length > 0;
    entityEl["entity-chart-empty"].classList.toggle("visible", !hasPoints);
    if (!window.Chart || !hasPoints) return;

    const labels = history.map((point) => formatTimestamp(point.timestamp));
    const values = history.map((point) => point.value_mw);
    const movingAverage = history.map((point) => point.moving_average_mw);
    const share = history.map((point) => point.share_percent);
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    const title = payload.entity.type === "disco" ? "Allocation MW" : "Generation MW";

    if (!entityChart) {
        entityChart = new Chart(entityEl["entity-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: title,
                        data: values,
                        borderColor: "#206bc4",
                        backgroundColor: "rgba(32, 107, 196, 0.13)",
                        borderWidth: 3,
                        tension: 0.32,
                        pointRadius: 2,
                        fill: true,
                        yAxisID: "y",
                    },
                    {
                        label: "Moving average",
                        data: movingAverage,
                        borderColor: "#18a66a",
                        borderDash: [6, 4],
                        borderWidth: 2,
                        tension: 0.28,
                        pointRadius: 0,
                        yAxisID: "y",
                    },
                    {
                        label: "System share",
                        data: share,
                        borderColor: "#f2b84b",
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius: 0,
                        yAxisID: "share",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
                    tooltip: {
                        callbacks: {
                            label: (context) => context.dataset.yAxisID === "share"
                                ? `${context.dataset.label}: ${formatNumber(context.parsed.y)}%`
                                : `${context.dataset.label}: ${formatMW(context.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } },
                    y: {
                        beginAtZero: false,
                        ticks: { callback: (value) => formatNumber(value, 0) },
                        grid: { color: gridColor },
                    },
                    share: {
                        position: "right",
                        beginAtZero: true,
                        ticks: { callback: (value) => `${value}%` },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    } else {
        entityChart.data.labels = labels;
        entityChart.data.datasets[0].label = title;
        entityChart.data.datasets[0].data = values;
        entityChart.data.datasets[1].data = movingAverage;
        entityChart.data.datasets[2].data = share;
        entityChart.options.scales.y.grid.color = gridColor;
        entityChart.update();
    }
}

function renderRelated(payload) {
    const related = payload.related || [];
    entityEl["entity-related"].innerHTML = related
        .map((item) => `<a href="${escapeHTML(item.url)}">${escapeHTML(item.name)}</a>`)
        .join("");
}

function renderEntity(payload) {
    const entity = payload.entity || {};
    const stats = payload.statistics || {};
    const trend = payload.trend || {};
    const forecast = payload.forecast || {};
    const risk = payload.risk || {};
    const performance = payload.performance || {};
    const latestRank = payload.rankings?.latest || {};
    const averageRank = payload.rankings?.average || {};
    const distribution = payload.utilization?.distribution;

    document.title = `${entity.name} ${entity.label} Intelligence | Nigeria Power Data`;
    entityEl["entity-title"].textContent = entity.name;
    entityEl["entity-lede"].textContent =
        `${entity.label} historical trend, forecast, ranking, risk, utilization, and automated analysis.`;
    entityEl["entity-unit"].textContent = entity.unit || "MW";
    entityEl["entity-generated"].textContent = `Generated ${formatTimestamp(payload.generated_at)}`;
    entityEl["entity-window"].textContent = `${payload.window_hours} hours`;

    entityEl["entity-latest"].innerHTML = `<span>${formatNumber(stats.latest_mw)}</span><span class="mw-unit">MW</span>`;
    entityEl["entity-latest"].className = "mw";
    entityEl["entity-latest-note"].textContent = `${payload.sample_count} stored readings for this entity.`;

    const trendClass = trend.direction === "up" ? "green" : trend.direction === "down" ? "red" : "blue";
    const trendArrow = trend.direction === "up" ? "&uarr;" : trend.direction === "down" ? "&darr;" : "&rarr;";
    entityEl["entity-trend"].innerHTML = `${trendArrow} ${trend.change_mw > 0 ? "+" : ""}${formatMW(trend.change_mw)}`;
    entityEl["entity-trend"].className = `badge ${trendClass}`;

    entityEl["entity-risk"].textContent = labelize(risk.classification);
    entityEl["entity-risk"].className = `badge ${badgeClassForRisk(risk.classification)}`;
    entityEl["entity-risk-pill"].textContent = `Risk: ${labelize(risk.classification)}`;
    entityEl["entity-risk-pill"].className = `badge ${badgeClassForRisk(risk.classification)}`;

    entityEl["entity-score"].textContent = `${formatNumber(performance.score, 1)}/100`;
    entityEl["entity-score-note"].textContent = `${labelize(performance.classification)} performance score.`;
    entityEl["entity-forecast-24h"].textContent = formatMW(forecast.next_24h_mw);
    entityEl["entity-forecast-7d"].textContent = formatMW(forecast.next_7d_mw);
    entityEl["entity-forecast-note"].textContent =
        `${labelize(forecast.method)} with ${forecast.confidence} confidence.`;
    entityEl["entity-forecast-pill"].textContent = `24h forecast: ${formatMW(forecast.next_24h_mw, 0)}`;
    entityEl["entity-method"].textContent = labelize(forecast.method);

    entityEl["entity-utilization"].textContent = `${formatNumber(payload.utilization?.latest_share_percent)}%`;
    entityEl["entity-utilization-note"].textContent = entity.type === "disco" && distribution
        ? `${formatNumber(distribution.estimated_utilization_percent)}% transformer utilization estimate.`
        : "Share of latest total system reading.";

    entityEl["entity-rank"].textContent = latestRank.rank ? `#${latestRank.rank}` : "...";
    entityEl["entity-rank-note"].textContent = latestRank.rank
        ? `${latestRank.rank} of ${latestRank.total_entities} by latest value.`
        : "No latest rank available.";
    entityEl["entity-rank-pill"].textContent = latestRank.rank
        ? `Rank #${latestRank.rank} of ${latestRank.total_entities}`
        : "Ranking pending";
    entityEl["entity-average-rank"].textContent = averageRank.rank ? `#${averageRank.rank}` : "...";
    entityEl["entity-average-rank-note"].textContent = averageRank.rank
        ? `${formatMW(averageRank.average_mw)} average across stored history.`
        : "No average rank available.";

    entityEl["entity-volatility"].textContent = `${formatNumber(stats.volatility_percent)}%`;
    entityEl["entity-volatility-note"].textContent = `${formatMW(stats.volatility_mw)} standard deviation.`;
    entityEl["entity-summary"].textContent = payload.analysis_summary;
    entityEl["entity-risk-driver"].textContent = labelize(risk.primary_driver);
    entityEl["entity-high"].textContent = formatMW(stats.highest_mw);
    entityEl["entity-low"].textContent = formatMW(stats.lowest_mw);
    entityEl["entity-chart-copy"].textContent = entity.type === "disco"
        ? "DisCo load allocation, moving average, and share of total distribution allocation."
        : "GenCo output, moving average, and share of total generation.";

    renderEntityChart(payload);
    renderRelated(payload);
}

async function refreshEntity() {
    document.body.classList.add("loading");
    entityEl["entity-refresh-state"].textContent = "Refreshing...";
    setEntityBanner("");

    try {
        const page = window.ENTITY_PAGE || {};
        const payload = await fetchEntityJSON(`/api/${page.plural}/${page.slug}?hours=168&limit=1000`);
        renderEntity(payload);
        entityEl["entity-refresh-state"].textContent = `Last refresh ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        setEntityBanner(error.message);
        entityEl["entity-refresh-state"].textContent = "Refresh failed";
    } finally {
        document.body.classList.remove("loading");
    }
}

initEntityTheme();
entityEl["theme-toggle"].addEventListener("click", toggleEntityTheme);
refreshEntity();
setInterval(refreshEntity, ENTITY_REFRESH_MS);
