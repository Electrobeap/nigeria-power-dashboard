const REFRESH_MS = 60000;
const chartLabels = [];
const generationReadings = [];
const movingAverageReadings = [];
let chart;
let previousMW = null;

const ids = [
    "source", "refresh-state", "error-banner", "time", "mw", "status", "trend",
    "insight", "reporting", "as-at", "moving-average", "sample-count", "chart",
    "chart-empty", "chart-window", "daily-date", "peak", "off-peak",
    "daily-high", "daily-low", "energy-generated", "energy-sent", "disco-time",
    "genco-time", "discos", "gencos", "grid-health", "grid-health-note",
    "stability-score", "stability-note", "volatility", "volatility-note",
    "load-concentration", "load-note", "top-genco", "top-genco-note",
    "outage-status", "outage-note", "api-health", "api-health-note",
    "trend-7d", "trend-7d-note", "theme-toggle",
];
const el = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

function initTheme() {
    const stored = localStorage.getItem("grid-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored || (prefersDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    el["theme-toggle"].textContent = theme === "dark" ? "Light" : "Dark";
}

function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("grid-theme", next);
    el["theme-toggle"].textContent = next === "dark" ? "Light" : "Dark";
    if (chart) chart.update();
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

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#039;",
    }[char]));
}

function setBanner(message) {
    el["error-banner"].textContent = message || "";
    el["error-banner"].classList.toggle("visible", Boolean(message));
}

async function fetchJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed: ${url}`);
    return payload;
}

function gridStatus(mw, stale, health) {
    if (stale) return ["Stored fallback", "amber", "Live source is unavailable, so the latest stored reading is shown."];
    if (health?.classification) {
        return [
            health.classification.replaceAll("_", " "),
            health.severity || "blue",
            health.message || "Grid status calculated from latest generation.",
        ];
    }
    if (mw < 3000) return ["Critical", "red", "Generation is below the critical operating band."];
    if (mw < 4500) return ["Stressed", "amber", "Generation is below a stronger supply band."];
    return ["Stable", "green", "Generation is within a stable operating band."];
}

function renderRows(target, rows, nameKey, valueKey) {
    if (!rows || rows.length === 0) {
        target.innerHTML = `<tr><td colspan="2">No records available.</td></tr>`;
        return;
    }
    target.innerHTML = rows
        .map((row) => `<tr><td>${escapeHTML(row[nameKey])}</td><td>${formatNumber(row[valueKey])}</td></tr>`)
        .join("");
}

function renderTrendBadge(analytics) {
    const trend = analytics?.last_24h_generation_trend;
    if (!trend) {
        el.trend.textContent = "Collecting trend";
        el.trend.className = "badge blue";
        return;
    }
    const sign = trend.change_mw > 0 ? "+" : "";
    const arrow = trend.direction === "up" ? "&uarr;" : trend.direction === "down" ? "&darr;" : "&rarr;";
    const percent = trend.change_percent === null ? "" : ` (${sign}${formatNumber(trend.change_percent)}%)`;
    el.trend.innerHTML = `${arrow} ${sign}${formatMW(trend.change_mw)}${percent}`;
    el.trend.className = `badge ${trend.direction === "up" ? "green" : trend.direction === "down" ? "red" : "blue"}`;
}

function renderLive(data, analytics) {
    const mw = Number(data.total_generation_mw);
    const [statusText, statusClass, insight] = gridStatus(mw, data.stale, analytics?.grid_health);

    el.mw.innerHTML = `<span>${formatNumber(mw)}</span><span class="mw-unit">MW</span>`;
    el.mw.className = "mw";
    if (previousMW !== null && mw > previousMW) el.mw.classList.add("green");
    if (previousMW !== null && mw < previousMW) el.mw.classList.add("red");
    previousMW = mw;

    el.time.textContent = `Fetched ${formatTimestamp(data.fetched_at)}`;
    el.status.textContent = statusText;
    el.status.className = `badge ${statusClass}`;
    el.insight.textContent = insight;
    el.reporting.textContent = data.reporting_gencos ?? "...";
    el["as-at"].textContent = data.as_at_time ?? "...";

    const daily = data.daily || {};
    el["daily-date"].textContent = daily.performance_date ? `Performance date ${daily.performance_date}` : "...";
    el.peak.textContent = formatMW(daily.peak_generation_mw);
    el["off-peak"].textContent = formatMW(daily.off_peak_generation_mw);
    el["energy-generated"].textContent = `${formatNumber(daily.energy_generated_mwh)} MWh`;
    el["energy-sent"].textContent = `${formatNumber(daily.energy_sent_out_mwh)} MWh`;

    el.source.innerHTML =
        `Source: <a class="source-link" href="${escapeHTML(data.source_url)}" target="_blank" rel="noreferrer">${escapeHTML(data.source)}</a>`;
    renderTrendBadge(analytics);
}

function renderAnalytics(analytics, windows) {
    if (!analytics || analytics.sample_count === 0) {
        renderEmptyAnalytics();
        return;
    }

    el["moving-average"].textContent = formatMW(analytics.rolling_average_mw);
    el["sample-count"].textContent = `${analytics.sample_count} stored readings`;
    el["daily-high"].textContent = formatMW(analytics.highest_daily_generation?.total_generation_mw);
    el["daily-low"].textContent = formatMW(analytics.lowest_daily_generation?.total_generation_mw);
    el["chart-window"].textContent = `${analytics.window_hours} hours`;
    renderTrendBadge(analytics);
    renderAdvancedAnalytics(analytics, windows);
}

function renderEmptyAnalytics() {
    el["moving-average"].textContent = "...";
    el["sample-count"].textContent = "No stored readings yet";
    el["daily-high"].textContent = "...";
    el["daily-low"].textContent = "...";
    renderAdvancedAnalytics(null, null);
    renderTrendBadge(null);
}

function renderAdvancedAnalytics(analytics, windows) {
    if (!analytics) {
        el["grid-health"].textContent = "...";
        el["grid-health-note"].textContent = "Awaiting live generation.";
        el["stability-score"].textContent = "...";
        el["stability-note"].textContent = "Awaiting historical readings.";
        el.volatility.textContent = "...";
        el["volatility-note"].textContent = "Awaiting historical readings.";
        el["load-concentration"].textContent = "...";
        el["load-note"].textContent = "Awaiting DisCo profile.";
        el["top-genco"].textContent = "...";
        el["top-genco-note"].textContent = "Awaiting GenCo output.";
        el["outage-status"].textContent = "...";
        el["outage-note"].textContent = "Awaiting trend data.";
        return;
    }

    const health = analytics.grid_health || {};
    const stability = analytics.supply_stability_score || {};
    const rollingHealth = analytics.rolling_health_score || {};
    const volatility = analytics.generation_volatility || {};
    const load = analytics.disco_load_concentration || {};
    const outage = analytics.outage_detection || {};
    const top = analytics.top_performing_gencos?.[0];
    const sevenDay = windows?.trend_7d?.last_24h_generation_trend;

    el["grid-health"].textContent = health.classification || "...";
    el["grid-health-note"].textContent = health.message || "No classification available.";
    el["stability-score"].textContent = stability.score === null ? "..." : `${formatNumber(stability.score, 1)}/100`;
    el["stability-note"].textContent = `${stability.classification || "unknown"} supply, ${rollingHealth.classification || "unknown"} rolling health`;
    el.volatility.textContent = `${formatNumber(volatility.volatility_percent)}%`;
    el["volatility-note"].textContent = `${formatMW(volatility.volatility_mw)} spread, ${volatility.classification || "unknown"}`;
    el["load-concentration"].textContent = load.classification || "...";
    el["load-note"].textContent = load.top_company
        ? `${load.top_company}: ${formatNumber(load.top_share_percent)}% of latest allocation`
        : "No DisCo concentration data.";
    el["top-genco"].textContent = top?.plant || "...";
    el["top-genco-note"].textContent = top
        ? `${formatMW(top.generation_mw)}${top.share_percent ? `, ${formatNumber(top.share_percent)}% share` : ""}`
        : "No GenCo output data.";
    el["outage-status"].textContent = outage.classification || "unknown";
    el["outage-note"].textContent = outage.detected
        ? `${outage.event_count} event${outage.event_count === 1 ? "" : "s"} detected`
        : "No outage pattern detected in this window.";
    el["trend-7d"].textContent = sevenDay
        ? `${sevenDay.change_mw > 0 ? "+" : ""}${formatMW(sevenDay.change_mw)}`
        : "...";
    el["trend-7d-note"].textContent = sevenDay
        ? `${sevenDay.direction}, ${formatNumber(sevenDay.change_percent)}% over stored 7-day window`
        : "Awaiting 7-day storage depth.";
}

function renderChart(history) {
    const points = history?.history || [];
    const hasPoints = points.length > 0;
    el["chart-empty"].classList.toggle("visible", !hasPoints);

    chartLabels.splice(0, chartLabels.length, ...points.map((point) => formatTimestamp(point.timestamp)));
    generationReadings.splice(0, generationReadings.length, ...points.map((point) => point.total_generation_mw));
    movingAverageReadings.splice(0, movingAverageReadings.length, ...points.map((point) => point.moving_average_mw));

    if (!window.Chart || !hasPoints) return;

    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    if (!chart) {
        chart = new Chart(el.chart.getContext("2d"), {
            type: "line",
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: "Generation MW",
                        data: generationReadings,
                        borderColor: "#206bc4",
                        backgroundColor: "rgba(32, 107, 196, 0.13)",
                        borderWidth: 3,
                        tension: 0.32,
                        pointRadius: 2,
                        fill: true,
                    },
                    {
                        label: "Moving average",
                        data: movingAverageReadings,
                        borderColor: "#18a66a",
                        borderDash: [6, 4],
                        borderWidth: 2,
                        tension: 0.28,
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
                    tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${formatMW(context.parsed.y)}` } },
                },
                scales: {
                    x: {
                        ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 },
                        grid: { display: false },
                    },
                    y: {
                        beginAtZero: false,
                        ticks: { callback: (value) => formatNumber(value, 0) },
                        grid: { color: gridColor },
                    },
                },
            },
        });
    } else {
        chart.options.scales.y.grid.color = gridColor;
        chart.update();
    }
}

function renderTables(latest) {
    const profile = latest?.disco_profile || {};
    el["disco-time"].textContent = profile.as_at ? `As at ${profile.as_at}` : formatTimestamp(profile.fetched_at);
    el["genco-time"].textContent = formatTimestamp(latest?.fetched_at || latest?.reading_timestamp);
    renderRows(el.discos, profile.discos || [], "company", "load_allocation_mw");
    renderRows(el.gencos, latest?.gencos || [], "plant", "generation_mw");
}

function renderHealth(payload) {
    if (!payload) return;
    el["api-health"].textContent = payload.ok ? "Operational" : "Degraded";
    const next = payload.capture?.next_run_at ? `Next capture ${formatTimestamp(payload.capture.next_run_at)}` : "Scheduler idle";
    el["api-health-note"].textContent = `${payload.database?.snapshot_count ?? 0} snapshots. ${next}.`;
}

function resultValue(results, key) {
    const result = results[key];
    return result && result.status === "fulfilled" ? result.value : null;
}

function resultError(results, key) {
    const result = results[key];
    return result && result.status === "rejected" ? result.reason.message : null;
}

async function refresh() {
    document.body.classList.add("loading");
    el["refresh-state"].textContent = "Refreshing...";
    setBanner("");

    const settled = await Promise.allSettled([
        fetchJSON("/api/latest"),
        fetchJSON("/api/history?hours=24&limit=288"),
        fetchJSON("/api/health"),
    ]);
    const results = { latest: settled[0], history: settled[1], health: settled[2] };
    const latest = resultValue(results, "latest");
    const history = resultValue(results, "history");
    const health = resultValue(results, "health");
    const analytics = history?.analytics || latest?.analytics?.trend_24h;
    const windows = latest?.analytics || history?.windows;

    if (history) {
        renderAnalytics(analytics, windows);
        renderChart(history);
    }
    if (latest) {
        renderLive(latest, analytics);
        renderTables(latest);
    }
    renderHealth(health);

    const errors = ["latest", "history", "health"].map((key) => resultError(results, key)).filter(Boolean);
    if (errors.length) setBanner(errors[0]);

    if (!latest && !history) {
        el.status.textContent = "Source unavailable";
        el.status.className = "badge red";
        el.insight.textContent = "No live or stored grid data is currently available.";
    }

    el["refresh-state"].textContent = `Last refresh ${new Date().toLocaleTimeString()}`;
    document.body.classList.remove("loading");
}

initTheme();
el["theme-toggle"].addEventListener("click", toggleTheme);
refresh().catch((error) => {
    setBanner(error.message);
    el.status.textContent = "Source unavailable";
    el.status.className = "badge red";
    el.insight.textContent = "No live or stored grid data is currently available.";
    document.body.classList.remove("loading");
});
setInterval(() => refresh().catch((error) => setBanner(error.message)), REFRESH_MS);
