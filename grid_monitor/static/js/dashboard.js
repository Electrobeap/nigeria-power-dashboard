const REFRESH_MS = 60000;
const chartLabels = [];
const generationReadings = [];
const movingAverageReadings = [];
let chart;
let previousMW = null;

const ids = [
    "source", "refresh-state", "error-banner", "time", "mw", "status", "trend",
    "insight", "reporting", "as-at", "moving-average", "sample-count", "chart",
    "chart-empty", "chart-note", "chart-window", "daily-date", "peak", "off-peak",
    "daily-high", "daily-low", "energy-generated", "energy-sent", "disco-time",
    "genco-time", "discos", "gencos", "grid-health", "grid-health-note",
    "stability-score", "stability-note", "volatility", "volatility-note",
    "load-concentration", "load-note", "top-genco", "top-genco-note",
];
const el = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

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

function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.error || `Request failed: ${url}`);
        }
        return payload;
    });
}

function gridStatus(mw, stale, health) {
    if (stale) {
        return ["Stored fallback", "amber", "Live source is unavailable, so the latest stored reading is shown."];
    }
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
        .map((row) => (
            `<tr><td>${escapeHTML(row[nameKey])}</td><td>${formatNumber(row[valueKey])}</td></tr>`
        ))
        .join("");
}

function renderTrend(analytics) {
    const trend = analytics?.last_24h_generation_trend;
    if (!trend) {
        el.trend.textContent = "Collecting trend";
        el.trend.className = "pill blue";
        return;
    }

    const sign = trend.change_mw > 0 ? "+" : "";
    const arrow = trend.direction === "up" ? "&uarr;" : trend.direction === "down" ? "&darr;" : "&rarr;";
    const percent = trend.change_percent === null ? "" : ` (${sign}${formatNumber(trend.change_percent)}%)`;
    el.trend.innerHTML = `${arrow} ${sign}${formatMW(trend.change_mw)}${percent}`;
    el.trend.className = `pill ${trend.direction === "up" ? "green" : trend.direction === "down" ? "red" : "blue"}`;
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
    el.status.className = `pill ${statusClass}`;
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

    renderTrend(analytics);
}

function renderAnalytics(analytics) {
    if (!analytics || analytics.sample_count === 0) {
        el["moving-average"].textContent = "...";
        el["sample-count"].textContent = "0";
        el["daily-high"].textContent = "...";
        el["daily-low"].textContent = "...";
        renderAdvancedAnalytics(null);
        renderTrend(null);
        return;
    }

    el["moving-average"].textContent = formatMW(analytics.rolling_average_mw);
    el["sample-count"].textContent = analytics.sample_count;
    el["daily-high"].textContent = formatMW(analytics.highest_daily_generation?.total_generation_mw);
    el["daily-low"].textContent = formatMW(analytics.lowest_daily_generation?.total_generation_mw);
    el["chart-window"].textContent = `${analytics.window_hours} hours`;
    renderTrend(analytics);
    renderAdvancedAnalytics(analytics);
}

function renderAdvancedAnalytics(analytics) {
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
        return;
    }

    const health = analytics.grid_health || {};
    const stability = analytics.supply_stability_score || {};
    const volatility = analytics.generation_volatility || {};
    const load = analytics.disco_load_concentration || {};
    const top = analytics.top_performing_gencos?.[0];

    el["grid-health"].textContent = health.classification || "...";
    el["grid-health-note"].textContent = health.message || "No classification available.";
    el["stability-score"].textContent = stability.score === null ? "..." : `${formatNumber(stability.score, 1)}/100`;
    el["stability-note"].textContent = stability.classification || "No stability score available.";
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
}

function renderChart(history) {
    const points = history?.history || [];
    const hasPoints = points.length > 0;
    el["chart-empty"].classList.toggle("visible", !hasPoints);

    chartLabels.splice(0, chartLabels.length, ...points.map((point) => formatTimestamp(point.timestamp)));
    generationReadings.splice(0, generationReadings.length, ...points.map((point) => point.total_generation_mw));
    movingAverageReadings.splice(0, movingAverageReadings.length, ...points.map((point) => point.moving_average_mw));

    if (!window.Chart) {
        el["chart-empty"].textContent = "Chart library unavailable. Data tables and metrics are still live.";
        el["chart-empty"].classList.add("visible");
        return;
    }

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
                        borderColor: "#11845b",
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
                interaction: {
                    intersect: false,
                    mode: "index",
                },
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            boxWidth: 12,
                            usePointStyle: true,
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => `${context.dataset.label}: ${formatMW(context.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 8,
                        },
                        grid: {
                            display: false,
                        },
                    },
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: (value) => formatNumber(value, 0),
                        },
                    },
                },
            },
        });
    } else {
        chart.update();
    }
}

function renderDiscos(payload) {
    el["disco-time"].textContent = payload?.as_at ? `As at ${payload.as_at}` : formatTimestamp(payload?.fetched_at);
    renderRows(el.discos, payload?.discos || [], "company", "load_allocation_mw");
}

function renderGencos(payload) {
    el["genco-time"].textContent = formatTimestamp(payload?.fetched_at || payload?.reading_timestamp);
    renderRows(el.gencos, payload?.gencos || [], "plant", "generation_mw");
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
        fetchJSON("/api/grid/live"),
        fetchJSON("/api/history?hours=24&limit=288"),
        fetchJSON("/api/discos"),
        fetchJSON("/api/gencos"),
    ]);
    const results = {
        live: settled[0],
        history: settled[1],
        discos: settled[2],
        gencos: settled[3],
    };

    const history = resultValue(results, "history");
    const analytics = history?.analytics;
    if (history) {
        renderAnalytics(analytics);
        renderChart(history);
    }

    const live = resultValue(results, "live");
    if (live) {
        renderLive(live, analytics);
    }

    const discos = resultValue(results, "discos") || live?.disco_profile;
    if (discos) renderDiscos(discos);

    const gencos = resultValue(results, "gencos") || (live ? {
        gencos: live.gencos,
        fetched_at: live.fetched_at,
    } : null);
    if (gencos) renderGencos(gencos);

    const errors = ["live", "history", "discos", "gencos"]
        .map((key) => resultError(results, key))
        .filter(Boolean);
    if (errors.length) {
        setBanner(errors[0]);
    }

    if (!live && !history && !discos && !gencos) {
        el.status.textContent = "Source unavailable";
        el.status.className = "pill red";
        el.insight.textContent = "No live or stored grid data is currently available.";
    }

    el["refresh-state"].textContent = `Last refresh ${new Date().toLocaleTimeString()}`;
    document.body.classList.remove("loading");
}

refresh().catch((error) => {
    setBanner(error.message);
    el.status.textContent = "Source unavailable";
    el.status.className = "pill red";
    el.insight.textContent = "No live or stored grid data is currently available.";
    document.body.classList.remove("loading");
});

setInterval(() => {
    refresh().catch((error) => setBanner(error.message));
}, REFRESH_MS);
