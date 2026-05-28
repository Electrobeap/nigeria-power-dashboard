const REFRESH_MS = 60000;
const chartLabels = [];
const generationReadings = [];
const movingAverageReadings = [];
const distributionLabels = [];
const distributionUtilization = [];
const distributionWarning = [];
const distributionOverload = [];
let chart;
let distributionChart;
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
    "trend-7d", "trend-7d-note", "theme-toggle", "distribution-classification",
    "transformer-utilization", "transformer-note", "distribution-regions-risk",
    "distribution-risk-note", "settlement-growth", "settlement-note",
    "distribution-chart", "distribution-chart-empty", "distribution-table",
    "distribution-method", "transformer-risk", "transformer-risk-note",
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
    if (distributionChart) distributionChart.update();
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

function labelize(value) {
    return String(value || "unknown").replaceAll("_", " ");
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

function badgeClassForRisk(value) {
    if (["critical", "overload_risk", "elevated", "warning"].includes(value)) return "red";
    if (["watch", "stressed"].includes(value)) return "amber";
    if (["normal", "stable", "strong"].includes(value)) return "green";
    return "blue";
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

function renderDistribution(payload, errorMessage = "") {
    const summary = payload?.summary;
    const utilization = payload?.transformer_utilization;
    const impact = payload?.settlement_expansion_impact;
    const riskRows = payload?.regional_risk || [];
    const classification = summary?.overload_warning_classification || "unknown";

    if (!payload) {
        el["distribution-classification"].textContent = "Pending";
        el["distribution-classification"].className = "badge blue";
        el["transformer-utilization"].textContent = "...";
        el["transformer-note"].textContent = errorMessage || "Awaiting stored DisCo allocation data.";
        el["distribution-regions-risk"].textContent = "...";
        el["distribution-risk-note"].textContent = "No transformer risk model available yet.";
        el["settlement-growth"].textContent = "...";
        el["settlement-note"].textContent = "Projected settlement impact pending.";
        el["transformer-risk"].textContent = "...";
        el["transformer-risk-note"].textContent = "Awaiting distribution intelligence.";
        el["distribution-method"].textContent = "Distribution model will appear after the first stored allocation reading.";
        el["distribution-table"].innerHTML = `<tr><td colspan="4">No distribution intelligence available.</td></tr>`;
        el["distribution-chart-empty"].classList.add("visible");
        return;
    }

    const utilizationValue = utilization?.weighted_utilization_percent;
    const warningCount = summary?.regions_at_warning_or_higher ?? 0;
    const highestRisk = summary?.highest_risk_region;

    el["distribution-classification"].textContent = labelize(classification);
    el["distribution-classification"].className = `badge ${badgeClassForRisk(classification)}`;
    el["transformer-utilization"].textContent = utilizationValue === null || utilizationValue === undefined
        ? "..."
        : `${formatNumber(utilizationValue)}%`;
    el["transformer-note"].textContent =
        `Warning at ${formatNumber(utilization?.warning_threshold_percent, 0)}%, overload at ${formatNumber(utilization?.overload_threshold_percent, 0)}%.`;
    el["distribution-regions-risk"].textContent = warningCount;
    el["distribution-risk-note"].textContent = highestRisk
        ? `${highestRisk.company}: ${labelize(highestRisk.overload_warning)}`
        : "No high-risk regions detected.";
    el["settlement-growth"].textContent = formatMW(impact?.projected_load_growth_12m_mw);
    el["settlement-note"].textContent =
        `${impact?.regions_projected_overload_12m ?? 0} region(s) projected above overload threshold in 12 months.`;
    el["transformer-risk"].textContent = labelize(classification);
    el["transformer-risk-note"].textContent = highestRisk
        ? `${highestRisk.company} stress index ${formatNumber(highestRisk.settlement_growth_vs_stress, 1)}.`
        : "Portfolio risk is normal.";
    el["distribution-method"].textContent = payload.methodology?.model_type
        ? `${payload.methodology.model_type}. ${payload.methodology.basis}`
        : "Planning-grade distribution estimate.";

    renderDistributionTable(riskRows);
    renderDistributionChart(payload);
}

function renderDistributionTable(rows) {
    if (!rows || rows.length === 0) {
        el["distribution-table"].innerHTML = `<tr><td colspan="4">No regions available.</td></tr>`;
        return;
    }
    el["distribution-table"].innerHTML = rows.slice(0, 8).map((row) => {
        const riskClass = badgeClassForRisk(row.overload_warning);
        return `<tr>
            <td>
                <strong>${escapeHTML(row.company)}</strong>
                <small>${escapeHTML(row.planning_region)}</small>
            </td>
            <td>${formatNumber(row.estimated_utilization_percent)}%</td>
            <td>${formatNumber(row.projected_utilization_12m_percent)}%</td>
            <td><span class="badge ${riskClass}">${escapeHTML(labelize(row.overload_warning))}</span></td>
        </tr>`;
    }).join("");
}

function renderDistributionChart(payload) {
    const points = payload?.transformer_loading_trend || [];
    const hasPoints = points.length > 0;
    el["distribution-chart-empty"].classList.toggle("visible", !hasPoints);
    if (!window.Chart || !hasPoints) return;

    distributionLabels.splice(0, distributionLabels.length, ...points.map((point) => formatTimestamp(point.timestamp)));
    distributionUtilization.splice(0, distributionUtilization.length, ...points.map((point) => point.weighted_utilization_percent));
    distributionWarning.splice(0, distributionWarning.length, ...points.map((point) => point.warning_threshold_percent));
    distributionOverload.splice(0, distributionOverload.length, ...points.map((point) => point.overload_threshold_percent));

    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    if (!distributionChart) {
        distributionChart = new Chart(el["distribution-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels: distributionLabels,
                datasets: [
                    {
                        label: "Utilization",
                        data: distributionUtilization,
                        borderColor: "#16a66a",
                        backgroundColor: "rgba(22, 166, 106, 0.12)",
                        borderWidth: 3,
                        tension: 0.3,
                        pointRadius: 0,
                        fill: true,
                    },
                    {
                        label: "Warning",
                        data: distributionWarning,
                        borderColor: "#f2b84b",
                        borderDash: [6, 4],
                        borderWidth: 2,
                        pointRadius: 0,
                    },
                    {
                        label: "Overload",
                        data: distributionOverload,
                        borderColor: "#c83532",
                        borderDash: [3, 4],
                        borderWidth: 2,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
                    tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${formatNumber(context.parsed.y)}%` } },
                },
                scales: {
                    x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 }, grid: { display: false } },
                    y: { suggestedMin: 40, suggestedMax: 110, ticks: { callback: (value) => `${value}%` }, grid: { color: gridColor } },
                },
            },
        });
    } else {
        distributionChart.options.scales.y.grid.color = gridColor;
        distributionChart.update();
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
        fetchJSON("/api/distribution?hours=168&limit=336"),
    ]);
    const results = { latest: settled[0], history: settled[1], health: settled[2], distribution: settled[3] };
    const latest = resultValue(results, "latest");
    const history = resultValue(results, "history");
    const health = resultValue(results, "health");
    const distribution = resultValue(results, "distribution");
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
    renderDistribution(distribution, resultError(results, "distribution"));

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
