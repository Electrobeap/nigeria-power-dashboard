const REFRESH_MS = 60000;
const CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js";
const HAMMER_JS_URL = "https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js";
const CHART_ZOOM_URL = "https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.2.0/dist/chartjs-plugin-zoom.min.js";
const GRID_REFERENCE_DEMAND_MW = 6500;
const GRID_NOMINAL_FREQUENCY_HZ = 50;
const GENERATION_CRITICAL_MW = 3000;
const GENERATION_WARNING_MW = 4500;
const HISTORY_LIMIT = 2000;
let historyHours = 24;
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
    "source", "refresh-state", "error-banner", "time", "mw", "status", "status-icon", "trend",
    "trend-arrow", "trend-percent",
    "insight", "grid-frequency", "grid-frequency-note", "available-capacity",
    "available-capacity-note", "energy-deficit", "energy-deficit-note",
    "gencos-online", "gencos-online-note", "discos-count", "discos-count-note",
    "last-updated", "last-updated-note", "reporting", "as-at", "moving-average", "sample-count", "chart",
    "chart-empty", "chart-window", "chart-reset", "chart-range", "daily-date", "peak", "off-peak",
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

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("Chart library failed to load."));
        document.head.appendChild(script);
    });
}

// Zoom and pan are progressive: if the plugin or Hammer fails to load the
// chart still renders, it simply is not interactive.
function loadZoomPlugin() {
    if (!window.Chart || window.Chart.registry.plugins.get("zoom")) return Promise.resolve();
    return loadScript(HAMMER_JS_URL)
        .catch(() => undefined)
        .then(() => loadScript(CHART_ZOOM_URL))
        .then(() => {
            const plugin = window.ChartZoom || window.chartjsPluginZoom;
            if (plugin) window.Chart.register(plugin);
        })
        .catch(() => undefined);
}

function loadChartLibrary() {
    if (chartLibraryPromise) return chartLibraryPromise;
    const base = window.Chart ? Promise.resolve() : loadScript(CHART_JS_URL);
    chartLibraryPromise = base.then(() => loadZoomPlugin()).then(() => window.Chart);
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

function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

function isDarkTheme() {
    return document.documentElement.dataset.theme === "dark";
}

// Shades the regime a reading sits in, so the series can be judged without
// tracing back to the axis. Drawn behind the datasets.
const operatingBandsPlugin = {
    id: "operatingBands",
    beforeDatasetsDraw(instance, _args, opts) {
        const bands = opts && opts.bands;
        if (!bands || !bands.length) return;
        const { ctx, chartArea, scales } = instance;
        const scale = scales[(opts && opts.axis) || "y"];
        if (!scale || !chartArea) return;
        const width = chartArea.right - chartArea.left;
        ctx.save();
        ctx.beginPath();
        ctx.rect(chartArea.left, chartArea.top, width, chartArea.bottom - chartArea.top);
        ctx.clip();
        bands.forEach((band) => {
            const from = band.from === null || band.from === undefined ? scale.min : band.from;
            const to = band.to === null || band.to === undefined ? scale.max : band.to;
            if (to <= scale.min || from >= scale.max) return;
            const yFrom = scale.getPixelForValue(Math.max(from, scale.min));
            const yTo = scale.getPixelForValue(Math.min(to, scale.max));
            const top = Math.min(yFrom, yTo);
            const height = Math.abs(yFrom - yTo);
            if (height <= 0.5) return;
            ctx.fillStyle = band.color;
            ctx.fillRect(chartArea.left, top, width, height);
            if (band.label && height >= 18) {
                ctx.fillStyle = band.labelColor;
                ctx.font = "700 10px Inter, system-ui, sans-serif";
                ctx.textAlign = "right";
                ctx.textBaseline = "top";
                ctx.fillText(band.label, chartArea.right - 8, top + 4);
            }
        });
        ctx.restore();
    },
};

// Flags stored outage events on the time axis. Drawn above the datasets.
const eventMarkersPlugin = {
    id: "eventMarkers",
    afterDatasetsDraw(instance, _args, opts) {
        const markers = opts && opts.markers;
        if (!markers || !markers.length) return;
        const { ctx, chartArea, scales } = instance;
        const xScale = scales.x;
        if (!xScale || !chartArea) return;
        ctx.save();
        markers.forEach((marker) => {
            const x = xScale.getPixelForValue(marker.index);
            if (!Number.isFinite(x) || x < chartArea.left || x > chartArea.right) return;
            ctx.beginPath();
            ctx.setLineDash([4, 3]);
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = marker.color;
            ctx.moveTo(x, chartArea.top);
            ctx.lineTo(x, chartArea.bottom);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.fillStyle = marker.color;
            ctx.arc(x, chartArea.top + 5, 3.5, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.restore();
    },
};

// Prints each bar's value just above it so the projection reads without hover.
const barValueLabelsPlugin = {
    id: "barValueLabels",
    afterDatasetsDraw(instance, _args, opts) {
        if (!opts || opts.enabled === false) return;
        const meta = instance.getDatasetMeta(opts.datasetIndex || 0);
        if (!meta || meta.hidden) return;
        const { ctx, chartArea } = instance;
        const format = opts.format || ((value) => String(value));
        ctx.save();
        ctx.font = "700 11px Inter, system-ui, sans-serif";
        ctx.fillStyle = opts.color;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        meta.data.forEach((element, index) => {
            const value = instance.data.datasets[meta.index].data[index];
            if (value === null || value === undefined || Number.isNaN(Number(value))) return;
            const y = element.y - 6;
            if (y < chartArea.top + 4) return;
            ctx.fillText(format(value), element.x, y);
        });
        ctx.restore();
    },
};

function analystTooltip(extra) {
    return Object.assign({
        backgroundColor: isDarkTheme() ? "rgba(11, 31, 58, 0.96)" : "rgba(255, 255, 255, 0.98)",
        titleColor: cssVar("--text", "#0B1F3A"),
        bodyColor: cssVar("--text", "#0B1F3A"),
        borderColor: cssVar("--line", "rgba(11, 31, 58, 0.14)"),
        borderWidth: 1,
        padding: 12,
        cornerRadius: 8,
        usePointStyle: true,
        boxPadding: 6,
        titleFont: { size: 12, weight: "700" },
        bodyFont: { size: 12, weight: "600" },
    }, extra || {});
}

function analystLegend() {
    return {
        position: "bottom",
        labels: {
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
            pointStyle: "circle",
            padding: 14,
            color: cssVar("--muted", "#5B6B82"),
            font: { size: 11, weight: "700" },
        },
    };
}

function analystTicks() {
    return { color: cssVar("--muted", "#5B6B82"), font: { size: 11 } };
}

// Background regimes only: the band a reading falls in is named in the
// tooltip, so nothing is painted over the plot area itself.
function generationBands() {
    return [
        { from: null, to: GENERATION_CRITICAL_MW, color: "rgba(220, 38, 38, 0.07)" },
        { from: GENERATION_CRITICAL_MW, to: GENERATION_WARNING_MW, color: "rgba(245, 158, 11, 0.07)" },
        { from: GENERATION_WARNING_MW, to: null, color: "rgba(0, 135, 81, 0.055)" },
    ];
}

function describeWindow(hours) {
    const value = numericOrNull(hours);
    if (value === null) return "24 hours";
    return value >= 48 ? `${Math.round(value / 24)} days` : `${Math.round(value)} hours`;
}

// Figures grow with the grid: 4,532.18 and -12,845.22 must both sit inside
// their card, so the type scale steps down with the rendered length.
// 4,532.18 (6 digits) is the everyday case and keeps the full size; the steps
// start at 12,543.67 and above.
function figureScaleClass(text) {
    const digits = String(text).replace(/[^0-9]/g, "").length;
    if (digits >= 8) return " is-xlong";
    if (digits >= 7) return " is-long";
    return "";
}

function fullTimestamp(value) {
    if (!value) return "...";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

// The reset control only appears once the view is actually zoomed or panned.
function syncZoomState() {
    if (!el["chart-reset"]) return;
    let active = false;
    if (chart && typeof chart.isZoomedOrPanned === "function") {
        active = chart.isZoomedOrPanned();
    } else if (chart && typeof chart.getZoomLevel === "function") {
        active = chart.getZoomLevel() !== 1;
    }
    el["chart-reset"].hidden = !active;
}

function resetChartZoom() {
    if (chart && typeof chart.resetZoom === "function") chart.resetZoom();
    syncZoomState();
}

function generationBandName(mw) {
    const value = numericOrNull(mw);
    if (value === null) return "unknown";
    if (value < GENERATION_CRITICAL_MW) return "Critical";
    if (value < GENERATION_WARNING_MW) return "Warning";
    return "Healthy";
}

function lastNumeric(values) {
    for (let index = values.length - 1; index >= 0; index -= 1) {
        const value = numericOrNull(values[index]);
        if (value !== null) return value;
    }
    return null;
}

// Transformer loading bands are data-driven: the API supplies the warning and
// overload thresholds per reading, so fall back to nothing when absent.
function loadingBands(warningSeries, overloadSeries) {
    const warning = lastNumeric(warningSeries);
    const overload = lastNumeric(overloadSeries);
    if (warning === null && overload === null) return [];
    const bands = [];
    if (warning !== null) {
        bands.push({ from: null, to: warning, color: "rgba(0, 135, 81, 0.055)" });
    }
    if (warning !== null && overload !== null && overload > warning) {
        bands.push({ from: warning, to: overload, color: "rgba(245, 158, 11, 0.07)" });
    }
    if (overload !== null) {
        bands.push({ from: overload, to: null, color: "rgba(220, 38, 38, 0.07)" });
    }
    return bands;
}

function loadingBandName(utilization, warning, overload) {
    const value = numericOrNull(utilization);
    const warn = numericOrNull(warning);
    const over = numericOrNull(overload);
    if (value === null) return "unknown";
    if (over !== null && value >= over) return "Overload";
    if (warn !== null && value >= warn) return "Warning";
    return "Normal";
}

function loadingHeadroom(utilization, overload) {
    const current = numericOrNull(utilization);
    const limit = numericOrNull(overload);
    if (current === null || limit === null) return "not available";
    const margin = limit - current;
    return margin >= 0 ? `${formatNumber(margin, 1)} pts` : `exceeded by ${formatNumber(Math.abs(margin), 1)} pts`;
}

// Maps stored outage events onto chart indices via their timestamps.
function outageMarkers(points, events) {
    if (!points || !points.length || !events || !events.length) return [];
    const indexByTime = new Map();
    points.forEach((point, index) => {
        const parsed = Date.parse(point?.timestamp);
        if (!Number.isNaN(parsed)) indexByTime.set(parsed, index);
    });
    const markers = [];
    const seen = new Set();
    events.forEach((event) => {
        const parsed = Date.parse(event?.timestamp);
        if (Number.isNaN(parsed) || !indexByTime.has(parsed)) return;
        const index = indexByTime.get(parsed);
        if (seen.has(index)) return;
        seen.add(index);
        markers.push({
            index,
            type: event.type,
            color: event.type === "critical_generation" ? "rgba(220, 38, 38, 0.75)" : "rgba(245, 158, 11, 0.8)",
        });
    });
    return markers;
}

function applyChartTheme(instance) {
    if (!instance) return;
    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    Object.values(instance.options.scales || {}).forEach((scale) => {
        if (scale.grid && scale.grid.display !== false) scale.grid.color = gridColor;
        if (scale.ticks) scale.ticks.color = cssVar("--muted", "#5B6B82");
    });
    // rebuild from theme defaults, keeping only the chart-specific callbacks
    instance.options.plugins.tooltip = analystTooltip({
        callbacks: (instance.options.plugins.tooltip || {}).callbacks,
    });
    if (instance.options.plugins.legend) {
        instance.options.plugins.legend.labels.color = cssVar("--muted", "#5B6B82");
    }
    if (instance.options.plugins.barValueLabels) {
        instance.options.plugins.barValueLabels.color = cssVar("--muted", "#5B6B82");
    }
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
    [chart, distributionChart, settlementChart].forEach((instance) => {
        if (!instance) return;
        applyChartTheme(instance);
        instance.update("none");
    });
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
        el.trend.className = "trend-change neutral";
        el["trend-arrow"].innerHTML = "&rarr;";
        el["trend-arrow"].className = "trend-arrow neutral";
        el["trend-percent"].textContent = "Awaiting stored readings";
        return;
    }
    const sign = trend.change_mw > 0 ? "+" : "";
    const directionClass = trend.direction === "up" ? "up" : trend.direction === "down" ? "down" : "neutral";
    el["trend-arrow"].innerHTML = trend.direction === "up" ? "&uarr;" : trend.direction === "down" ? "&darr;" : "&rarr;";
    el["trend-arrow"].className = `trend-arrow ${directionClass}`;
    const trendText = `${sign}${formatMW(trend.change_mw)}`;
    el.trend.textContent = trendText;
    el.trend.className = `trend-change ${directionClass}${figureScaleClass(trendText)}`;
    el["trend-percent"].textContent = trend.change_percent === null
        ? "No percentage change available"
        : `${sign}${formatNumber(trend.change_percent)}% over stored 24h window`;
}

function statusClassName(statusText, fallbackClass) {
    const normalized = String(statusText || "").toLowerCase();
    if (normalized.includes("critical")) return "critical";
    if (normalized.includes("stressed") || normalized.includes("stress")) return "stressed";
    if (normalized.includes("watch") || normalized.includes("fallback") || fallbackClass === "amber") return "watch";
    if (normalized.includes("stable") || normalized.includes("healthy") || normalized.includes("strong") || fallbackClass === "green") return "healthy";
    if (fallbackClass === "red") return "critical";
    return "watch";
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

    const mwText = formatNumber(mw);
    el.mw.innerHTML = `<span>${mwText}</span><span class="mw-unit">MW</span>`;
    el.mw.className = `mw${figureScaleClass(mwText)}`;
    if (previousMW !== null && mw > previousMW) el.mw.classList.add("green");
    if (previousMW !== null && mw < previousMW) el.mw.classList.add("red");
    previousMW = mw;

    el.status.textContent = statusText;
    const normalizedStatusClass = statusClassName(statusText, statusClass);
    el.status.className = `status-badge badge ${normalizedStatusClass}`;
    el["status-icon"].className = `status-icon ${normalizedStatusClass}`;
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
    el["chart-window"].textContent = describeWindow(analytics.window_hours ?? historyHours);
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

    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    const markers = outageMarkers(points, history?.analytics?.outage_detection?.events);
    const markerLookup = new Map(markers.map((marker) => [marker.index, marker]));
    // One consolidated readout: only the generation series drives the tooltip
    // body, so the rolling average and its delta are not repeated twice.
    const tooltipCallbacks = {
        title: (items) => (items.length ? fullTimestamp(points[items[0].dataIndex]?.timestamp) : ""),
        label: (context) => {
            if (context.datasetIndex !== 0) return "";
            return `Generation: ${formatMW(context.parsed.y)}`;
        },
        afterBody: (items) => {
            if (!items.length) return "";
            const index = items[0].dataIndex;
            const value = numericOrNull(generationReadings[index]);
            const average = numericOrNull(movingAverageReadings[index]);
            const lines = [];
            lines.push(`Rolling average: ${average === null ? "not available" : formatMW(average)}`);
            if (value !== null && average !== null) {
                const delta = value - average;
                lines.push(`Difference: ${delta >= 0 ? "+" : "-"}${formatMW(Math.abs(delta))}`);
            }
            lines.push(`Operating band: ${generationBandName(value)}`);
            const marker = markerLookup.get(index);
            if (marker) {
                lines.push(marker.type === "critical_generation"
                    ? "Event: below critical threshold"
                    : "Event: sharp generation drop");
            }
            return lines;
        },
    };

    if (!chart) {
        chart = new Chart(el.chart.getContext("2d"), {
            type: "line",
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: "Generation",
                        data: generationReadings,
                        borderColor: "#2563EB",
                        // faint: the operating bands behind must stay readable
                        backgroundColor: "rgba(37, 99, 235, 0.035)",
                        borderWidth: 1.8,
                        tension: 0.25,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: "#2563EB",
                        pointHoverBorderColor: "#FFFFFF",
                        fill: true,
                        order: 2,
                    },
                    {
                        // held back visually: the average is context, not the signal
                        label: "Rolling average",
                        data: movingAverageReadings,
                        borderColor: "rgba(0, 135, 81, 0.55)",
                        borderDash: [5, 5],
                        borderWidth: 1.2,
                        tension: 0.25,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        fill: false,
                        order: 1,
                    },
                ],
            },
            plugins: [operatingBandsPlugin, eventMarkersPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                normalized: true,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: analystLegend(),
                    tooltip: analystTooltip({ callbacks: tooltipCallbacks }),
                    operatingBands: { axis: "y", bands: generationBands() },
                    eventMarkers: { markers },
                    zoom: {
                        limits: { x: { min: "original", max: "original", minRange: 4 } },
                        pan: { enabled: true, mode: "x", modifierKey: null, onPanComplete: syncZoomState },
                        zoom: {
                            wheel: { enabled: true, speed: 0.08 },
                            pinch: { enabled: true },
                            drag: { enabled: false },
                            mode: "x",
                            onZoomComplete: syncZoomState,
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: Object.assign(analystTicks(), {
                            maxRotation: 0,
                            autoSkip: true,
                            autoSkipPadding: 24,
                            maxTicksLimit: 6,
                        }),
                        grid: { display: false },
                        border: { color: gridColor },
                    },
                    y: {
                        beginAtZero: false,
                        ticks: Object.assign(analystTicks(), { callback: (value) => formatNumber(value, 0), maxTicksLimit: 6 }),
                        grid: { color: gridColor, drawTicks: false },
                        border: { display: false },
                        title: { display: true, text: "MW", color: cssVar("--muted", "#5B6B82"), font: { size: 11, weight: "700" } },
                    },
                },
            },
        });
    } else {
        chart.options.plugins.eventMarkers.markers = markers;
        chart.options.plugins.tooltip.callbacks = tooltipCallbacks;
        applyChartTheme(chart);
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

    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    const basePointRadius = distributionUtilization.length <= 2 ? 5 : 0;
    const utilizationLabel = activeDisco ? `${activeDisco.company} utilization` : "Portfolio utilization";
    const bands = loadingBands(distributionWarning, distributionOverload);
    // Readings at or above the overload threshold get a visible red dot.
    const overloadFlags = distributionUtilization.map((value, index) => {
        const current = numericOrNull(value);
        const limit = numericOrNull(distributionOverload[index]);
        return current !== null && limit !== null && current >= limit;
    });
    const pointRadius = overloadFlags.map((flag) => (flag ? 4.5 : basePointRadius));
    const pointColors = overloadFlags.map((flag) => (flag ? "#DC2626" : "#16a66a"));
    const tooltipCallbacks = {
        title: (items) => (items.length ? fullTimestamp(points[items[0].dataIndex]?.timestamp) : ""),
        label: (context) => {
            if (context.datasetIndex !== 0) return "";
            return `${context.dataset.label}: ${formatNumber(context.parsed.y)}%`;
        },
        afterBody: (items) => {
            if (!items.length) return "";
            const index = items[0].dataIndex;
            const value = distributionUtilization[index];
            const warning = distributionWarning[index];
            const overload = distributionOverload[index];
            const lines = [`Status: ${loadingBandName(value, warning, overload)}`];
            if (numericOrNull(warning) !== null) lines.push(`Warning at ${formatNumber(warning, 0)}%`);
            if (numericOrNull(overload) !== null) lines.push(`Overload at ${formatNumber(overload, 0)}%`);
            lines.push(`Headroom to overload: ${loadingHeadroom(value, overload)}`);
            return lines;
        },
    };

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
                        backgroundColor: "rgba(22, 166, 106, 0.10)",
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius,
                        pointBackgroundColor: pointColors,
                        pointBorderColor: "#FFFFFF",
                        pointBorderWidth: 1.5,
                        pointHoverRadius: 5,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: pointColors,
                        pointHoverBorderColor: "#FFFFFF",
                        fill: true,
                        order: 3,
                    },
                    {
                        label: "Warning threshold",
                        data: distributionWarning,
                        borderColor: "#F59E0B",
                        borderDash: [7, 3],
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        fill: false,
                        order: 2,
                    },
                    {
                        label: "Overload threshold",
                        data: distributionOverload,
                        borderColor: "#DC2626",
                        borderDash: [2, 3],
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        fill: false,
                        order: 1,
                    },
                ],
            },
            plugins: [operatingBandsPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                normalized: true,
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: analystLegend(),
                    tooltip: analystTooltip({ callbacks: tooltipCallbacks }),
                    operatingBands: { axis: "y", bands },
                },
                scales: {
                    x: {
                        ticks: Object.assign(analystTicks(), { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 }),
                        grid: { display: false },
                        border: { color: gridColor },
                    },
                    y: {
                        suggestedMin: 40,
                        suggestedMax: 110,
                        ticks: Object.assign(analystTicks(), { callback: (value) => `${value}%`, maxTicksLimit: 6 }),
                        grid: { color: gridColor, drawTicks: false },
                        border: { display: false },
                    },
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
        distributionChart.data.datasets[0].pointBackgroundColor = pointColors;
        distributionChart.data.datasets[0].pointHoverBackgroundColor = pointColors;
        distributionChart.options.plugins.operatingBands.bands = bands;
        distributionChart.options.plugins.tooltip.callbacks = tooltipCallbacks;
        applyChartTheme(distributionChart);
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

    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    const settlementTooltip = {
        title: (items) => (items.length ? `Horizon: ${items[0].label}` : ""),
        label: (context) => (context.dataset.yAxisID === "stress"
            ? `${context.dataset.label}: ${formatNumber(context.parsed.y, 1)} / 100`
            : `${context.dataset.label}: ${formatMW(context.parsed.y)}`),
        afterBody: (items) => {
            if (!items.length) return "";
            const stress = numericOrNull(settlementStress[items[0].dataIndex]);
            if (stress === null) return "";
            const level = stress >= 70 ? "Elevated" : stress >= 45 ? "Moderate" : "Contained";
            return `Stress level: ${level}`;
        },
    };
    if (!settlementChart) {
        settlementChart = new Chart(el["settlement-chart"].getContext("2d"), {
            data: {
                labels: settlementLabels,
                datasets: [
                    {
                        type: "bar",
                        label: activeDisco ? `${activeDisco.company} load growth` : "Projected load growth",
                        data: settlementGrowth,
                        backgroundColor: "rgba(37, 99, 235, 0.42)",
                        hoverBackgroundColor: "rgba(37, 99, 235, 0.58)",
                        borderColor: "#2563EB",
                        borderWidth: 1,
                        borderRadius: 4,
                        maxBarThickness: 56,
                        yAxisID: "mw",
                        order: 2,
                    },
                    {
                        type: "line",
                        label: activeDisco ? `${activeDisco.company} stress` : "Settlement stress",
                        data: settlementStress,
                        borderColor: "#F59E0B",
                        backgroundColor: "rgba(245, 158, 11, 0.14)",
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointBackgroundColor: "#F59E0B",
                        pointBorderColor: "#FFFFFF",
                        pointBorderWidth: 1.5,
                        tension: 0.25,
                        yAxisID: "stress",
                        order: 1,
                    },
                ],
            },
            plugins: [operatingBandsPlugin, barValueLabelsPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                normalized: true,
                layout: { padding: { top: 18 } },
                interaction: { intersect: false, mode: "index" },
                plugins: {
                    legend: analystLegend(),
                    tooltip: analystTooltip({ callbacks: settlementTooltip }),
                    barValueLabels: {
                        datasetIndex: 0,
                        color: cssVar("--muted", "#5B6B82"),
                        format: (value) => formatNumber(value, 0),
                    },
                    // stress index is a 0-100 scale, so the elevated zone is fixed
                    operatingBands: {
                        axis: "stress",
                        bands: [
                            {
                                from: 70,
                                to: null,
                                color: "rgba(220, 38, 38, 0.08)",
                                label: "Elevated stress",
                                labelColor: "rgba(220, 38, 38, 0.85)",
                            },
                        ],
                    },
                },
                scales: {
                    x: { ticks: analystTicks(), grid: { display: false }, border: { color: gridColor } },
                    mw: {
                        beginAtZero: true,
                        ticks: Object.assign(analystTicks(), { callback: (value) => formatNumber(value, 0), maxTicksLimit: 6 }),
                        grid: { color: gridColor, drawTicks: false },
                        border: { display: false },
                        title: { display: true, text: "MW", color: cssVar("--muted", "#5B6B82"), font: { size: 11, weight: "700" } },
                    },
                    stress: {
                        position: "right",
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: Object.assign(analystTicks(), { callback: (value) => `${value}`, maxTicksLimit: 6 }),
                        grid: { drawOnChartArea: false },
                        border: { display: false },
                        title: { display: true, text: "Stress", color: cssVar("--muted", "#5B6B82"), font: { size: 11, weight: "700" } },
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
        settlementChart.options.plugins.tooltip.callbacks = settlementTooltip;
        applyChartTheme(settlementChart);
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
        fetchJSON(`/api/history?hours=${historyHours}&limit=${HISTORY_LIMIT}`),
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
        el.status.className = "status-badge badge critical";
        el["status-icon"].className = "status-icon critical";
        el.insight.textContent = "No live or stored grid data is currently available.";
    }

    const refreshText = `Last refresh ${new Date().toLocaleTimeString()}`;
    el["refresh-state"].textContent = refreshText;
    el.time.textContent = refreshText;
    document.body.classList.remove("loading");

    if (history) scheduleChartWork(el.chart, () => renderChart(history));
    if (distribution) {
        scheduleChartWork(el["distribution-chart"], () => renderDistribution(distribution, resultError(results, "distribution")));
    }
}

// Range switching only changes the window requested from the existing history
// endpoint; the stored data model is untouched.
function selectHistoryRange(hours, button) {
    if (historyHours === hours) return;
    historyHours = hours;
    [...el["chart-range"].querySelectorAll(".range-btn")].forEach((node) => {
        const active = node === button;
        node.classList.toggle("is-active", active);
        node.setAttribute("aria-pressed", active ? "true" : "false");
    });
    el["chart-window"].textContent = describeWindow(hours);
    const title = document.getElementById("generation-title");
    if (title) title.textContent = `${describeWindow(hours)} of generation and moving average`;
    resetChartZoom();
    refresh().catch((error) => setBanner(error.message));
}

initTheme();
el["theme-toggle"].addEventListener("click", toggleTheme);
el["distribution-back"].addEventListener("click", clearDiscoSelection);
if (el["chart-reset"]) el["chart-reset"].addEventListener("click", resetChartZoom);
if (el["chart-range"]) {
    el["chart-range"].addEventListener("click", (event) => {
        const button = event.target.closest(".range-btn");
        if (button) selectHistoryRange(Number(button.dataset.hours), button);
    });
}
refresh().catch((error) => {
    setBanner(error.message);
    el.status.textContent = "Source unavailable";
    el.status.className = "status-badge badge critical";
    el["status-icon"].className = "status-icon critical";
    el.insight.textContent = "No live or stored grid data is currently available.";
    document.body.classList.remove("loading");
});
setInterval(() => refresh().catch((error) => setBanner(error.message)), REFRESH_MS);
