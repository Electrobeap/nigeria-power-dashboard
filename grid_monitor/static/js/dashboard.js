const REFRESH_MS = 60000;
const CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js";
const GRID_REFERENCE_DEMAND_MW = 6500;
const GRID_NOMINAL_FREQUENCY_HZ = 50;
window.requestAnimationFrame(() => document.body.classList.add("brand-loaded"));
const chartLabels = [];
const generationReadings = [];
const movingAverageReadings = [];
const distributionLabels = [];
const distributionUtilization = [];
const distributionWarning = [];
const distributionOverload = [];
const settlementLabels = [];
const settlementGrowth = [];
const settlementStress = [];
let chart;
let distributionChart;
let settlementChart;
let previousMW = null;
let latestDistributionPayload = null;
let selectedDiscoSlug = null;
let chartLibraryPromise = null;

const ids = [
    "source", "refresh-state", "error-banner", "time", "mw", "status", "trend",
    "insight", "grid-frequency", "grid-frequency-note", "available-capacity",
    "available-capacity-note", "energy-deficit", "energy-deficit-note",
    "gencos-online", "gencos-online-note", "discos-count", "discos-count-note",
    "last-updated", "last-updated-note", "reporting", "as-at", "moving-average", "sample-count", "chart",
    "chart-empty", "chart-window", "daily-date", "peak", "off-peak",
    "daily-high", "daily-low", "energy-generated", "energy-sent", "disco-time",
    "genco-time", "discos", "gencos", "grid-health", "grid-health-note",
    "stability-score", "stability-note", "volatility", "volatility-note",
    "load-concentration", "load-note", "top-genco", "top-genco-note",
    "outage-status", "outage-note", "api-health", "api-health-note",
    "trend-7d", "trend-7d-note", "theme-toggle", "distribution-classification",
    "distribution-back", "transformer-utilization", "transformer-note",
    "transformer-forecast", "transformer-forecast-note", "distribution-risk-level",
    "distribution-risk-level-note", "capacity-margin", "capacity-margin-note",
    "settlement-growth", "settlement-note",
    "distribution-chart", "distribution-chart-empty", "distribution-table",
    "settlement-chart", "settlement-chart-empty", "distribution-chart-title",
    "settlement-chart-title",
    "distribution-method", "transformer-risk", "transformer-risk-note",
];
const el = Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));

function loadChartLibrary() {
    if (window.Chart) return Promise.resolve(window.Chart);
    if (chartLibraryPromise) return chartLibraryPromise;
    chartLibraryPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = CHART_JS_URL;
        script.async = true;
        script.onload = () => resolve(window.Chart);
        script.onerror = () => reject(new Error("Chart library failed to load."));
        document.head.appendChild(script);
    });
    return chartLibraryPromise;
}

function scheduleNonCriticalWork(callback) {
    const run = () => {
        if ("requestIdleCallback" in window) {
            window.requestIdleCallback(callback, { timeout: 1800 });
        } else {
            window.setTimeout(callback, 0);
        }
    };
    window.requestAnimationFrame(run);
}

function scheduleChartWork(target, callback) {
    const run = () => scheduleNonCriticalWork(() => {
        loadChartLibrary()
            .then(callback)
            .catch((error) => setBanner(error.message));
    });
    if (window.Chart) {
        run();
        return;
    }
    if (target && "IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                observer.disconnect();
                run();
            }
        }, { rootMargin: "180px 0px" });
        observer.observe(target);
        return;
    }
    window.setTimeout(run, 3500);
}

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
    if (chart) chart.update("none");
    if (distributionChart) distributionChart.update("none");
    if (settlementChart) settlementChart.update("none");
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

function numericOrNull(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
    return Number(value);
}

function pointLabel(point) {
    return point?.label && !String(point.label).includes("T")
        ? point.label
        : formatTimestamp(point?.timestamp || point?.label);
}

function labelize(value) {
    return String(value || "unknown").replaceAll("_", " ");
}

function slugifyEntity(value) {
    return String(value || "unknown")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "unknown";
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

function renderRows(target, rows, nameKey, valueKey, entityPlural) {
    if (!rows || rows.length === 0) {
        target.innerHTML = `<tr><td colspan="2">No records available.</td></tr>`;
        return;
    }
    target.innerHTML = rows
        .map((row) => {
            const name = row[nameKey];
            const href = `/${entityPlural}/${slugifyEntity(name)}`;
            return `<tr class="clickable-row">
                <td><a class="entity-link" href="${href}">${escapeHTML(name)}</a></td>
                <td><a class="entity-link value" href="${href}">${formatNumber(row[valueKey])}</a></td>
            </tr>`;
        })
        .join("");
}

function topRows(rows, valueKey, limit = 8) {
    return [...(rows || [])]
        .sort((left, right) => Number(right[valueKey] || 0) - Number(left[valueKey] || 0))
        .slice(0, limit);
}

function badgeClassForRisk(value) {
    if (["critical", "overload_risk", "elevated", "warning"].includes(value)) return "red";
    if (["watch", "stressed"].includes(value)) return "amber";
    if (["normal", "stable", "strong"].includes(value)) return "green";
    return "blue";
}

function formatPercent(value, digits = 2) {
    return value === null || value === undefined ? "..." : `${formatNumber(value, digits)}%`;
}

function discoDrilldownUrl(slug) {
    return `/discos/${encodeURIComponent(slug)}`;
}

function selectedDisco(payload) {
    if (!selectedDiscoSlug) return null;
    return payload?.disco_drilldowns?.[selectedDiscoSlug] || null;
}

function selectDisco(slug) {
    selectedDiscoSlug = slug;
    if (latestDistributionPayload) renderDistribution(latestDistributionPayload);
}

function clearDiscoSelection() {
    selectedDiscoSlug = null;
    if (latestDistributionPayload) renderDistribution(latestDistributionPayload);
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
    const daily = data.daily || {};
    const frequency = numericOrNull(data.frequency_hz ?? data.grid_frequency_hz ?? data.frequency);
    const shownFrequency = frequency ?? GRID_NOMINAL_FREQUENCY_HZ;
    const availableCapacity = numericOrNull(
        data.available_capacity_mw
            ?? data.available_generation_capacity_mw
            ?? data.installed_available_capacity_mw
            ?? daily.peak_generation_mw,
    ) ?? mw;
    const referenceDemand = numericOrNull(
        data.estimated_peak_demand_mw
            ?? data.peak_demand_mw
            ?? data.reference_demand_mw,
    ) ?? GRID_REFERENCE_DEMAND_MW;
    const energyDeficit = Math.max(0, referenceDemand - mw);
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
    el["grid-frequency"].textContent = `${formatNumber(shownFrequency, 2)} Hz`;
    el["grid-frequency-note"].textContent = frequency === null
        ? "Nominal 50 Hz reference until live frequency is exposed."
        : "Latest reported grid frequency.";
    el["available-capacity"].textContent = formatMW(availableCapacity);
    el["available-capacity-note"].textContent = availableCapacity === mw
        ? "Using current generation until declared available capacity is reported."
        : "Latest available capacity signal from the source payload.";
    el["energy-deficit"].textContent = formatMW(energyDeficit);
    el["energy-deficit-note"].textContent = `Against ${formatMW(referenceDemand, 0)} reference demand.`;
    el["gencos-online"].textContent = data.reporting_gencos ?? "...";
    el["gencos-online-note"].textContent = "Reporting GenCos from the latest source snapshot.";
    el["last-updated"].textContent = formatTimestamp(data.fetched_at || data.reading_timestamp);
    el["last-updated-note"].textContent = data.stale
        ? "Stored fallback reading."
        : "Live or latest stored grid snapshot.";
    el.reporting.textContent = data.reporting_gencos ?? "...";
    el["as-at"].textContent = data.as_at_time ?? "...";

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
                        borderColor: "#2563EB",
                        backgroundColor: "rgba(37, 99, 235, 0.13)",
                        borderWidth: 3,
                        tension: 0.32,
                        pointRadius: 2,
                        fill: true,
                    },
                    {
                        label: "Moving average",
                        data: movingAverageReadings,
                        borderColor: "#008751",
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
                animation: false,
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
        chart.update("none");
    }
}

function renderDistribution(payload, errorMessage = "") {
    latestDistributionPayload = payload || null;
    const summary = payload?.summary;
    const utilization = payload?.transformer_utilization;
    const impact = payload?.settlement_expansion_impact;
    const riskRows = payload?.regional_risk || [];

    if (!payload) {
        selectedDiscoSlug = null;
        el["distribution-classification"].textContent = "Pending";
        el["distribution-classification"].className = "badge blue";
        el["distribution-back"].classList.add("hidden");
        el["distribution-chart-title"].textContent = "Transformer Loading Trend";
        el["settlement-chart-title"].textContent = "Settlement Expansion Risk";
        el["transformer-utilization"].textContent = "...";
        el["transformer-note"].textContent = errorMessage || "Awaiting stored DisCo allocation data.";
        el["transformer-forecast"].textContent = "...";
        el["transformer-forecast-note"].textContent = "Projected loading pending.";
        el["distribution-risk-level"].textContent = "...";
        el["distribution-risk-level-note"].textContent = "No transformer risk model available yet.";
        el["capacity-margin"].textContent = "...";
        el["capacity-margin-note"].textContent = "Margin to overload threshold.";
        el["settlement-growth"].textContent = "...";
        el["settlement-note"].textContent = "Projected settlement impact pending.";
        el["transformer-risk"].textContent = "...";
        el["transformer-risk-note"].textContent = "Awaiting distribution intelligence.";
        el["distribution-method"].textContent = "Distribution model will appear after the first stored allocation reading.";
        el["distribution-table"].innerHTML = `<tr><td colspan="4">No distribution intelligence available.</td></tr>`;
        el["distribution-chart-empty"].classList.add("visible");
        el["settlement-chart-empty"].classList.add("visible");
        return;
    }

    if (selectedDiscoSlug && !selectedDisco(payload)) selectedDiscoSlug = null;
    const activeDisco = selectedDisco(payload);
    const hasSelection = Boolean(activeDisco);
    const classification = hasSelection
        ? activeDisco.overload_warning || "unknown"
        : summary?.overload_warning_classification || "unknown";
    const utilizationValue = hasSelection
        ? activeDisco.current_utilization_percent ?? activeDisco.estimated_utilization_percent
        : utilization?.weighted_utilization_percent;
    const forecastValue = hasSelection
        ? activeDisco.projected_utilization_12m_percent
        : utilization?.projected_utilization_12m_percent ?? summary?.projected_utilization_12m_percent;
    const capacityMargin = hasSelection
        ? activeDisco.capacity_margin_percent
        : utilization?.capacity_margin_percent ?? summary?.capacity_margin_percent;
    const projectedMargin = hasSelection
        ? activeDisco.projected_capacity_margin_12m_percent
        : utilization?.projected_capacity_margin_12m_percent ?? summary?.projected_capacity_margin_12m_percent;
    const warningCount = summary?.regions_at_warning_or_higher ?? 0;
    const highestRisk = summary?.highest_risk_region;
    const selectedGrowthPoint = activeDisco?.settlement_expansion_trend?.find((point) => point.label === "12 months");

    el["distribution-back"].classList.toggle("hidden", !hasSelection);
    el["distribution-chart-title"].textContent = hasSelection
        ? `${activeDisco.company} Transformer Loading Trend`
        : "Transformer Loading Trend";
    el["settlement-chart-title"].textContent = hasSelection
        ? `${activeDisco.company} Settlement Expansion Risk`
        : "Settlement Expansion Risk";
    el["distribution-classification"].textContent = hasSelection
        ? `${activeDisco.company}: ${labelize(classification)}`
        : labelize(classification);
    el["distribution-classification"].className = `badge ${badgeClassForRisk(classification)}`;
    el["transformer-utilization"].textContent = utilizationValue === null || utilizationValue === undefined
        ? "..."
        : `${formatNumber(utilizationValue)}%`;
    el["transformer-note"].textContent = hasSelection
        ? `${formatMW(activeDisco.load_allocation_mw)} allocation, ${formatPercent(activeDisco.load_share_percent)} load share.`
        : `Warning at ${formatNumber(utilization?.warning_threshold_percent, 0)}%, overload at ${formatNumber(utilization?.overload_threshold_percent, 0)}%.`;
    el["transformer-forecast"].textContent = formatPercent(forecastValue);
    el["transformer-forecast-note"].textContent = hasSelection
        ? `36-month projection ${formatPercent(activeDisco.projected_utilization_36m_percent)}.`
        : `Portfolio 36-month projection ${formatPercent(summary?.projected_utilization_36m_percent)}.`;
    el["distribution-risk-level"].textContent = labelize(classification);
    el["distribution-risk-level-note"].textContent = hasSelection
        ? activeDisco.recommended_action || "Monitor allocation and regional loading trend."
        : highestRisk
            ? `${warningCount} region(s) at warning or higher; highest risk is ${highestRisk.company}.`
            : "No high-risk regions detected.";
    el["capacity-margin"].textContent = formatPercent(capacityMargin);
    el["capacity-margin-note"].textContent = `12-month margin ${formatPercent(projectedMargin)} to overload threshold.`;
    el["settlement-growth"].textContent = hasSelection
        ? formatPercent(activeDisco.settlement_growth_percent, 1)
        : formatMW(impact?.projected_load_growth_12m_mw);
    el["settlement-note"].textContent = hasSelection
        ? `${formatMW(selectedGrowthPoint?.projected_load_growth_mw)} projected load growth; stress ${formatNumber(activeDisco.settlement_growth_vs_stress, 1)}/100.`
        : `${impact?.regions_projected_overload_12m ?? 0} region(s) projected above overload threshold in 12 months.`;
    el["transformer-risk"].textContent = labelize(classification);
    el["transformer-risk-note"].textContent = hasSelection
        ? `${activeDisco.company} stress index ${formatNumber(activeDisco.settlement_growth_vs_stress, 1)}.`
        : highestRisk
            ? `${highestRisk.company} stress index ${formatNumber(highestRisk.settlement_growth_vs_stress, 1)}.`
            : "Portfolio risk is normal.";
    el["distribution-method"].textContent = payload.methodology?.model_type
        ? `${hasSelection ? `Selected DisCo: ${activeDisco.company}. ` : ""}${payload.methodology.model_type}. ${payload.methodology.basis}`
        : "Planning-grade distribution estimate.";

    renderDistributionTable(riskRows);
    renderDistributionChart(payload, activeDisco);
    renderSettlementChart(payload, activeDisco);
}

function renderDistributionTable(rows) {
    if (!rows || rows.length === 0) {
        el["distribution-table"].innerHTML = `<tr><td colspan="4">No regions available.</td></tr>`;
        return;
    }
    el["distribution-table"].innerHTML = rows.map((row) => {
        const slug = row.slug || slugifyEntity(row.company);
        const riskClass = badgeClassForRisk(row.overload_warning);
        const selectedClass = selectedDiscoSlug === slug ? " selected" : "";
        return `<tr class="clickable-row distribution-row${selectedClass}" data-disco-slug="${escapeHTML(slug)}" data-detail-url="${escapeHTML(discoDrilldownUrl(slug))}" tabindex="0" role="button" aria-pressed="${selectedDiscoSlug === slug ? "true" : "false"}">
            <td>
                <strong>${escapeHTML(row.company)}</strong>
                <small>${escapeHTML(row.planning_region)}</small>
            </td>
            <td>${formatNumber(row.estimated_utilization_percent)}%</td>
            <td>${formatNumber(row.projected_utilization_12m_percent)}%</td>
            <td><span class="badge ${riskClass}">${escapeHTML(labelize(row.overload_warning))}</span></td>
        </tr>`;
    }).join("");

    el["distribution-table"].querySelectorAll("[data-disco-slug]").forEach((row) => {
        row.addEventListener("click", () => selectDisco(row.dataset.discoSlug));
        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectDisco(row.dataset.discoSlug);
            }
        });
    });
}

function renderDistributionChart(payload, activeDisco = null) {
    const points = activeDisco?.transformer_loading_trend || payload?.transformer_loading_trend || [];
    const utilizationValue = (point) => numericOrNull(
        activeDisco
            ? point.estimated_utilization_percent ?? point.weighted_utilization_percent
            : point.weighted_utilization_percent,
    );
    const hasPoints = points.some((point) => utilizationValue(point) !== null);
    el["distribution-chart-empty"].classList.toggle("visible", !hasPoints);
    if (!window.Chart || !hasPoints) return;

    distributionLabels.splice(0, distributionLabels.length, ...points.map(pointLabel));
    distributionUtilization.splice(0, distributionUtilization.length, ...points.map(utilizationValue));
    distributionWarning.splice(0, distributionWarning.length, ...points.map((point) => numericOrNull(point.warning_threshold_percent)));
    distributionOverload.splice(0, distributionOverload.length, ...points.map((point) => numericOrNull(point.overload_threshold_percent)));

    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    const pointRadius = distributionUtilization.length <= 2 ? 5 : 3;
    const utilizationLabel = activeDisco ? `${activeDisco.company} utilization` : "Portfolio utilization";
    if (!distributionChart) {
        distributionChart = new Chart(el["distribution-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels: distributionLabels,
                datasets: [
                    {
                        label: utilizationLabel,
                        data: distributionUtilization,
                        borderColor: "#16a66a",
                        backgroundColor: "rgba(22, 166, 106, 0.12)",
                        borderWidth: 3,
                        tension: 0.3,
                        pointRadius,
                        pointHoverRadius: 6,
                        fill: true,
                    },
                    {
                        label: "Warning",
                        data: distributionWarning,
                        borderColor: "#F59E0B",
                        borderDash: [6, 4],
                        borderWidth: 2,
                        pointRadius: 2,
                    },
                    {
                        label: "Overload",
                        data: distributionOverload,
                        borderColor: "#DC2626",
                        borderDash: [3, 4],
                        borderWidth: 2,
                        pointRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
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
        distributionChart.data.labels = distributionLabels;
        distributionChart.data.datasets[0].label = utilizationLabel;
        distributionChart.data.datasets[0].data = distributionUtilization;
        distributionChart.data.datasets[1].data = distributionWarning;
        distributionChart.data.datasets[2].data = distributionOverload;
        distributionChart.data.datasets[0].pointRadius = pointRadius;
        distributionChart.options.scales.y.grid.color = gridColor;
        distributionChart.update("none");
    }
}

function renderSettlementChart(payload, activeDisco = null) {
    const impact = payload?.settlement_expansion_impact || {};
    const fallbackPoints = [
        {
            label: "Current",
            projected_load_growth_mw: 0,
            settlement_stress_index: activeDisco?.settlement_growth_vs_stress
                ?? payload?.summary?.highest_risk_region?.settlement_growth_vs_stress,
        },
        {
            label: "12 months",
            projected_load_growth_mw: activeDisco
                ? (activeDisco.load_allocation_mw || 0) * ((activeDisco.settlement_growth_percent || 0) / 100)
                : impact.projected_load_growth_12m_mw,
            settlement_stress_index: activeDisco?.settlement_growth_vs_stress
                ?? payload?.summary?.highest_risk_region?.settlement_growth_vs_stress,
        },
        {
            label: "36 months",
            projected_load_growth_mw: activeDisco
                ? (activeDisco.load_allocation_mw || 0) * (((1 + ((activeDisco.settlement_growth_percent || 0) / 100)) ** 3) - 1)
                : impact.projected_load_growth_36m_mw,
            settlement_stress_index: activeDisco?.settlement_growth_vs_stress
                ?? payload?.summary?.highest_risk_region?.settlement_growth_vs_stress,
        },
    ];
    const sourcePoints = activeDisco?.settlement_expansion_trend || payload?.settlement_expansion_trend || [];
    const points = sourcePoints.length
        ? sourcePoints
        : fallbackPoints;
    const hasPoints = points.some((point) => numericOrNull(point.projected_load_growth_mw) !== null);
    el["settlement-chart-empty"].classList.toggle("visible", !hasPoints);
    if (!window.Chart || !hasPoints) return;

    settlementLabels.splice(0, settlementLabels.length, ...points.map(pointLabel));
    settlementGrowth.splice(0, settlementGrowth.length, ...points.map((point) => numericOrNull(point.projected_load_growth_mw)));
    settlementStress.splice(0, settlementStress.length, ...points.map((point) => numericOrNull(point.settlement_stress_index)));

    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    if (!settlementChart) {
        settlementChart = new Chart(el["settlement-chart"].getContext("2d"), {
            data: {
                labels: settlementLabels,
                datasets: [
                    {
                        type: "bar",
                        label: activeDisco ? `${activeDisco.company} load growth` : "Projected load growth",
                        data: settlementGrowth,
                        backgroundColor: "rgba(37, 99, 235, 0.22)",
                        borderColor: "#2563EB",
                        borderWidth: 1,
                        borderRadius: 4,
                        yAxisID: "mw",
                    },
                    {
                        type: "line",
                        label: activeDisco ? `${activeDisco.company} stress` : "Settlement stress",
                        data: settlementStress,
                        borderColor: "#F59E0B",
                        backgroundColor: "rgba(245, 158, 11, 0.16)",
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.25,
                        yAxisID: "stress",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
                    tooltip: {
                        callbacks: {
                            label: (context) => context.dataset.yAxisID === "stress"
                                ? `${context.dataset.label}: ${formatNumber(context.parsed.y, 1)}/100`
                                : `${context.dataset.label}: ${formatMW(context.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false } },
                    mw: {
                        beginAtZero: true,
                        ticks: { callback: (value) => formatNumber(value, 0) },
                        grid: { color: gridColor },
                    },
                    stress: {
                        position: "right",
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: { callback: (value) => `${value}` },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    } else {
        settlementChart.data.labels = settlementLabels;
        settlementChart.data.datasets[0].label = activeDisco ? `${activeDisco.company} load growth` : "Projected load growth";
        settlementChart.data.datasets[1].label = activeDisco ? `${activeDisco.company} stress` : "Settlement stress";
        settlementChart.data.datasets[0].data = settlementGrowth;
        settlementChart.data.datasets[1].data = settlementStress;
        settlementChart.options.scales.mw.grid.color = gridColor;
        settlementChart.update("none");
    }
}

function renderTables(latest) {
    const profile = latest?.disco_profile || {};
    const discoRows = profile.discos || [];
    const gencoRows = latest?.gencos || [];
    const onlineGencos = gencoRows.filter((row) => (numericOrNull(row.generation_mw) || 0) > 0).length;

    el["disco-time"].textContent = profile.as_at ? `As at ${profile.as_at}` : formatTimestamp(profile.fetched_at);
    el["genco-time"].textContent = formatTimestamp(latest?.fetched_at || latest?.reading_timestamp);
    el["discos-count"].textContent = discoRows.length ? discoRows.length : "...";
    el["discos-count-note"].textContent = discoRows.length
        ? `${discoRows.length} distribution companies in the latest allocation profile.`
        : "Awaiting DisCo allocation profile.";
    if (onlineGencos > 0) {
        el["gencos-online"].textContent = onlineGencos;
        el["gencos-online-note"].textContent = `${onlineGencos} plants with positive output in the latest snapshot.`;
    }
    renderRows(el.discos, topRows(discoRows, "load_allocation_mw"), "company", "load_allocation_mw", "discos");
    renderRows(el.gencos, topRows(gencoRows, "generation_mw"), "plant", "generation_mw", "gencos");
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

    if (history) renderAnalytics(analytics, windows);
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

    if (history) scheduleChartWork(el.chart, () => renderChart(history));
    if (distribution) {
        scheduleChartWork(el["distribution-chart"], () => renderDistribution(distribution, resultError(results, "distribution")));
    }
}

initTheme();
el["theme-toggle"].addEventListener("click", toggleTheme);
el["distribution-back"].addEventListener("click", clearDiscoSelection);
refresh().catch((error) => {
    setBanner(error.message);
    el.status.textContent = "Source unavailable";
    el.status.className = "badge red";
    el.insight.textContent = "No live or stored grid data is currently available.";
    document.body.classList.remove("loading");
});
setInterval(() => refresh().catch((error) => setBanner(error.message)), REFRESH_MS);
