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
let sparklineChart;
let modalTrendChart;
let latestHistory = null;
let latestSnapshot = null;
let modalReturnFocus = null;
let latestRegionRows = [];
const regionSort = { key: "estimated_utilization_percent", direction: "desc" };
let modalHours = 24;
let fullPoints = [];
let plottedIndices = [];
let plotWindow = { from: 0, to: null };
let modalPoints = [];
const modalReadings = [];

// One behaviour contract shared by every interactive chart: wheel zoom, drag
// pan, optional brush select, a reset control and visible-range statistics.
const mainChartTools = {
    get instance() { return chart; },
    resetId: "chart-reset",
    brushId: "chart-brush",
    stats: ["stat-avg", "stat-max", "stat-min", "stat-sd", "stat-n"],
    values: () => generationReadings,
    brushOn: false,
};

const modalChartTools = {
    get instance() { return modalTrendChart; },
    resetId: "modal-reset",
    brushId: "modal-brush",
    stats: ["modal-stat-avg", "modal-stat-max", "modal-stat-min", "modal-stat-sd", "modal-stat-n"],
    values: () => modalReadings,
    brushOn: false,
};
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
    "chart-empty", "chart-window", "chart-reset", "chart-range", "chart-brush",
    "chart-fullscreen", "chart-export", "chart-legend-note", "chart-legend-count",
    "modal-range", "modal-brush", "modal-reset", "modal-stats",
    "disco-filter", "disco-risk-filter", "disco-count",
    "modal-stat-avg", "modal-stat-max", "modal-stat-min", "modal-stat-sd", "modal-stat-n",
    "stat-avg", "stat-max", "stat-min", "stat-sd", "stat-n",
    "generation-drill", "generation-sparkline", "generation-modal", "generation-modal-close",
    "modal-current", "modal-current-note", "modal-utilization", "modal-utilization-note",
    "modal-yesterday", "modal-yesterday-note", "modal-lastweek", "modal-lastweek-note",
    "modal-trend-chart", "modal-trend-empty", "modal-trend-note", "modal-genco-rows",
    "daily-date", "peak", "off-peak",
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
        // Discrete glyphs pinned to the top of the plot plus a narrow tint,
        // rather than full-height rules. Dense event columns were reading as
        // a striped background and drowning the series itself.
        ctx.save();
        ctx.beginPath();
        ctx.rect(chartArea.left, chartArea.top, chartArea.right - chartArea.left,
                 chartArea.bottom - chartArea.top);
        ctx.clip();
        markers.forEach((marker) => {
            const x = xScale.getPixelForValue(marker.index);
            if (!Number.isFinite(x) || x < chartArea.left || x > chartArea.right) return;
            ctx.fillStyle = marker.tint || "rgba(220, 38, 38, 0.07)";
            ctx.fillRect(x - 3, chartArea.top, 6, chartArea.bottom - chartArea.top);
            const top = chartArea.top + 7;
            ctx.beginPath();
            ctx.moveTo(x, top + 6);
            ctx.lineTo(x - 4.5, top - 2);
            ctx.lineTo(x + 4.5, top - 2);
            ctx.closePath();
            ctx.fillStyle = marker.color;
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

// Largest-Triangle-Three-Buckets. Chosen over naive stride sampling because it
// keeps the extremes of each bucket, so collapses and spikes survive at low
// point counts instead of being averaged away. Returns source indices.
function downsampleIndices(values, target) {
    const n = values.length;
    if (target >= n || target < 3) return values.map((_, i) => i);
    const out = [0];
    const every = (n - 2) / (target - 2);
    let a = 0;
    for (let i = 0; i < target - 2; i += 1) {
        const rangeStart = Math.floor((i + 1) * every) + 1;
        const rangeEnd = Math.min(Math.floor((i + 2) * every) + 1, n);
        let avgX = 0;
        let avgY = 0;
        let count = 0;
        for (let j = rangeStart; j < rangeEnd; j += 1) {
            const v = numericOrNull(values[j]);
            if (v === null) continue;
            avgX += j;
            avgY += v;
            count += 1;
        }
        if (count) {
            avgX /= count;
            avgY /= count;
        }
        const bucketStart = Math.floor(i * every) + 1;
        const bucketEnd = Math.floor((i + 1) * every) + 1;
        const ax = a;
        const ay = numericOrNull(values[a]) ?? 0;
        let best = bucketStart;
        let bestArea = -1;
        for (let j = bucketStart; j < Math.min(bucketEnd, n); j += 1) {
            const v = numericOrNull(values[j]);
            if (v === null) continue;
            const area = Math.abs((ax - avgX) * (v - ay) - (ax - j) * (avgY - ay));
            if (area > bestArea) {
                bestArea = area;
                best = j;
            }
        }
        out.push(best);
        a = best;
    }
    out.push(n - 1);
    return out;
}

// How many points are worth drawing at the current canvas width. Roughly one
// per 2 device pixels: denser than that is not resolvable on screen.
function plotBudget() {
    const width = el.chart ? el.chart.getBoundingClientRect().width : 0;
    const usable = width > 0 ? width : (window.innerWidth || 1024);
    return Math.max(60, Math.min(600, Math.round(usable / 2)));
}

// Summary statistics for whatever slice of the series is currently in view.
function seriesStats(values) {
    const clean = values.map(numericOrNull).filter((v) => v !== null);
    if (!clean.length) return null;
    const sum = clean.reduce((a, b) => a + b, 0);
    const mean = sum / clean.length;
    const variance = clean.reduce((a, b) => a + ((b - mean) ** 2), 0) / clean.length;
    return {
        count: clean.length,
        mean,
        min: Math.min(...clean),
        max: Math.max(...clean),
        sd: Math.sqrt(variance),
    };
}

function visibleStats(tools) {
    // The main chart reports over the full-resolution window rather than the
    // thinned series, so the figures do not change with viewport width.
    if (tools === mainChartTools && fullPoints.length) {
        const [from, to] = visibleFullRange();
        return seriesStats(fullPoints.slice(from, to + 1).map((p) => numericOrNull(p.total_generation_mw)));
    }
    const values = tools.values();
    const instance = tools.instance;
    if (!instance || !instance.scales || !instance.scales.x) return seriesStats(values);
    const scale = instance.scales.x;
    const from = Math.max(0, Math.ceil(scale.min));
    const to = Math.min(values.length - 1, Math.floor(scale.max));
    if (to < from) return seriesStats(values);
    return seriesStats(values.slice(from, to + 1));
}

// Maps the chart's visible plotted indices back to indices in the full series.
function visibleFullRange() {
    if (!plottedIndices.length) return [plotWindow.from, plotWindow.to ?? 0];
    let lo = 0;
    let hi = plottedIndices.length - 1;
    if (chart && chart.scales && chart.scales.x) {
        lo = Math.max(0, Math.ceil(chart.scales.x.min));
        hi = Math.min(plottedIndices.length - 1, Math.floor(chart.scales.x.max));
        if (hi < lo) {
            lo = 0;
            hi = plottedIndices.length - 1;
        }
    }
    return [plottedIndices[lo], plottedIndices[hi]];
}

// Zooming narrows the window and re-samples it, so detail increases instead of
// simply magnifying the thinned line.
function resampleToVisible() {
    if (!chart || !fullPoints.length) return;
    const [from, to] = visibleFullRange();
    if (to - from < 8) return;
    const unchanged = from === plotWindow.from && to === plotWindow.to;
    plotWindow = { from, to };
    if (!unchanged) {
        renderChart(latestHistory);
        if (typeof chart.resetZoom === "function") chart.resetZoom();
    }
}

// Re-sampling clears Chart.js's own zoom state, so its pan handler has nothing
// left to move once a window is drawn at full extent. Dragging a narrowed plot
// therefore slides the window itself across the full series.
let windowPan = null;
let windowPanFrame = null;

function windowPanRender() {
    if (windowPanFrame) return;
    windowPanFrame = window.requestAnimationFrame(() => {
        windowPanFrame = null;
        if (latestHistory) renderChart(latestHistory);
    });
}

function beginWindowPan(event) {
    if (!chart || mainChartTools.brushOn || event.button !== 0 || !fullPoints.length) return;
    const span = plotWindow.to === null ? 0 : plotWindow.to - plotWindow.from;
    if (span <= 0 || span >= fullPoints.length - 1) return;
    const area = chart.chartArea;
    if (!area || event.offsetX < area.left || event.offsetX > area.right) return;
    windowPan = {
        x: event.clientX,
        from: plotWindow.from,
        span,
        perPixel: span / Math.max(1, area.right - area.left),
        pointerId: event.pointerId,
        moved: false,
    };
    if (chart.canvas.setPointerCapture) chart.canvas.setPointerCapture(event.pointerId);
}

function moveWindowPan(event) {
    if (!windowPan) return;
    const shift = Math.round((windowPan.x - event.clientX) * windowPan.perPixel);
    const limit = Math.max(0, fullPoints.length - 1 - windowPan.span);
    const from = Math.min(Math.max(0, windowPan.from + shift), limit);
    if (from === plotWindow.from) return;
    windowPan.moved = true;
    plotWindow = { from, to: from + windowPan.span };
    windowPanRender();
}

function endWindowPan() {
    if (!windowPan) return;
    const { moved, pointerId } = windowPan;
    if (chart && chart.canvas.releasePointerCapture && chart.canvas.hasPointerCapture(pointerId)) {
        chart.canvas.releasePointerCapture(pointerId);
    }
    windowPan = null;
    if (moved) syncChartTools(mainChartTools);
}

function renderChartStats(tools) {
    const stats = visibleStats(tools);
    const [avg, max, min, sd, n] = tools.stats;
    const set = (id, text) => { if (el[id]) el[id].textContent = text; };
    if (!stats) {
        tools.stats.forEach((id) => set(id, "..."));
        return;
    }
    set(avg, formatMW(stats.mean));
    set(max, formatMW(stats.max));
    set(min, formatMW(stats.min));
    set(sd, `±${formatMW(stats.sd)}`);
    set(n, formatNumber(stats.count, 0));
}

// The dotted verticals are stored outage events; the legend only appears when
// the visible window actually contains some.
function renderMarkerLegend(markers) {
    const note = el["chart-legend-note"];
    if (!note) return;
    const count = markers ? markers.length : 0;
    note.hidden = count === 0;
    if (el["chart-legend-count"] && count) {
        el["chart-legend-count"].textContent = `${formatNumber(count, 0)} in view — hover a marker for detail`;
    }
}

// Actual stored coverage, so a 1Y window over three weeks of data is never
// presented as a full year.
function historyCoverageHours(points) {
    if (!points || points.length < 2) return null;
    const first = Date.parse(points[0]?.timestamp);
    const last = Date.parse(points[points.length - 1]?.timestamp);
    if (Number.isNaN(first) || Number.isNaN(last)) return null;
    return (last - first) / 3600000;
}

function renderCoverageNote(points) {
    const covered = historyCoverageHours(points);
    if (!el["chart-window"]) return;
    if (covered === null) {
        el["chart-window"].textContent = describeWindow(historyHours);
        return;
    }
    // short by more than 5% of the requested window
    if (covered < historyHours * 0.95) {
        el["chart-window"].textContent = `${describeWindow(covered)} stored`;
        el["chart-window"].title = `Requested ${describeWindow(historyHours)}; ${describeWindow(covered)} of history is stored.`;
    } else {
        el["chart-window"].textContent = describeWindow(historyHours);
        el["chart-window"].removeAttribute("title");
    }
}

function renderSparkline(points) {
    if (!el["generation-sparkline"] || !window.Chart) return;
    const recent = points.slice(-48);
    const values = recent.map((p) => numericOrNull(p.total_generation_mw));
    if (!values.some((v) => v !== null)) return;
    const labels = recent.map((p) => formatTimestamp(p.timestamp));
    if (!sparklineChart) {
        sparklineChart = new Chart(el["generation-sparkline"].getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [{
                    data: values,
                    borderColor: "#F59E0B",
                    backgroundColor: "rgba(245, 158, 11, 0.16)",
                    borderWidth: 1.5,
                    tension: 0.3,
                    pointRadius: 0,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                normalized: true,
                events: [],
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: { x: { display: false }, y: { display: false } },
                layout: { padding: 0 },
            },
        });
    } else {
        sparklineChart.data.labels = labels;
        sparklineChart.data.datasets[0].data = values;
        sparklineChart.update("none");
    }
}

function describeWindow(hours) {
    const value = numericOrNull(hours);
    if (value === null) return "24 hours";
    if (value >= 8760) {
        const years = value / 8760;
        return years >= 1.95 ? `${Math.round(years)} years` : "1 year";
    }
    if (value >= 48) {
        const days = Math.round(value / 24);
        return `${days} ${days === 1 ? "day" : "days"}`;
    }
    const whole = Math.round(value);
    return `${whole} ${whole === 1 ? "hour" : "hours"}`;
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
function syncChartTools(tools) {
    renderChartStats(tools);
    const button = el[tools.resetId];
    if (!button) return;
    const instance = tools.instance;
    let active = false;
    if (instance && typeof instance.isZoomedOrPanned === "function") {
        active = instance.isZoomedOrPanned();
    } else if (instance && typeof instance.getZoomLevel === "function") {
        active = instance.getZoomLevel() !== 1;
    }
    // The main chart re-samples on zoom and then clears Chart.js's own zoom
    // state, so a narrowed plot window is what "zoomed" actually means here.
    if (tools === mainChartTools && fullPoints.length) {
        const narrowed = plotWindow.from > 0 || (plotWindow.to !== null && plotWindow.to < fullPoints.length - 1);
        active = active || narrowed;
        if (el.chart) el.chart.style.cursor = narrowed && !tools.brushOn ? "grab" : "";
    }
    button.hidden = !active;
}

function syncZoomState() {
    resampleToVisible();
    syncChartTools(mainChartTools);
}

function syncModalZoomState() {
    syncChartTools(modalChartTools);
}

function resetZoomFor(tools) {
    const instance = tools.instance;
    if (instance && typeof instance.resetZoom === "function") instance.resetZoom();
    syncChartTools(tools);
}

function resetChartZoom() {
    plotWindow = { from: 0, to: fullPoints.length ? fullPoints.length - 1 : null };
    if (latestHistory) renderChart(latestHistory);
    resetZoomFor(mainChartTools);
}

// Shared zoom/pan/brush configuration so every chart behaves the same way.
function zoomConfig(onComplete) {
    return {
        limits: { x: { min: "original", max: "original", minRange: 4 } },
        pan: { enabled: true, mode: "x", modifierKey: null, onPanComplete: onComplete },
        zoom: {
            wheel: { enabled: true, speed: 0.08 },
            pinch: { enabled: true },
            drag: { enabled: false },
            mode: "x",
            onZoomComplete: onComplete,
        },
    };
}

function toggleBrushFor(tools) {
    const instance = tools.instance;
    if (!instance || !instance.options.plugins.zoom) return;
    tools.brushOn = !tools.brushOn;
    const zoom = instance.options.plugins.zoom;
    zoom.zoom.drag = tools.brushOn
        ? { enabled: true, backgroundColor: "rgba(37, 99, 235, 0.15)", borderColor: "#2563EB", borderWidth: 1 }
        : { enabled: false };
    zoom.pan.enabled = !tools.brushOn;
    if (el[tools.brushId]) el[tools.brushId].setAttribute("aria-pressed", tools.brushOn ? "true" : "false");
    instance.update("none");
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
            color: event.type === "critical_generation" ? "rgba(220, 38, 38, 0.85)" : "rgba(245, 158, 11, 0.9)",
            tint: event.type === "critical_generation"
                ? "rgba(220, 38, 38, 0.10)"
                : "rgba(245, 158, 11, 0.10)",
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
    // Recolour in place. Replacing the tooltip object would re-read `callbacks`
    // off Chart.js's resolved options and hand back a proxy whose `title` is no
    // longer a plain function, which throws on the next hover.
    const tooltip = instance.options.plugins.tooltip;
    if (tooltip) {
        tooltip.backgroundColor = isDarkTheme() ? "rgba(11, 31, 58, 0.96)" : "rgba(255, 255, 255, 0.98)";
        tooltip.titleColor = cssVar("--text", "#0B1F3A");
        tooltip.bodyColor = cssVar("--text", "#0B1F3A");
        tooltip.borderColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    }
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
        el["top-genco"].textContent = "Unavailable";
        el["top-genco"].classList.add("is-unavailable");
        el["top-genco-note"].textContent =
            "Plant-level output has not been published yet. It appears automatically once the source reports one.";
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
    // Three distinct states: current data, real stored data from an earlier
    // reading (labelled, never presented as live), and genuinely unavailable.
    const gencoAsAt = analytics?.top_gencos_as_at;
    if (top?.plant) {
        el["top-genco"].textContent = top.plant;
        el["top-genco"].classList.remove("is-unavailable");
        const output = `${formatMW(top.generation_mw)}${top.share_percent ? `, ${formatNumber(top.share_percent)}% share` : ""}`;
        el["top-genco-note"].textContent = gencoAsAt
            ? `${output} — last reported ${fullTimestamp(gencoAsAt)}`
            : output;
    } else {
        el["top-genco"].textContent = "Unavailable";
        el["top-genco"].classList.add("is-unavailable");
        el["top-genco-note"].textContent =
            "The source is not publishing a GenCo output table. Plant-level output returns automatically once it does.";
    }
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
    fullPoints = history?.history || fullPoints;
    const hasPoints = fullPoints.length > 0;
    el["chart-empty"].classList.toggle("visible", !hasPoints);
    if (!hasPoints) return;

    // plotWindow indexes the FULL series. Everything drawn is a downsample of
    // that window; the full resolution stays available for tooltips, stats and
    // export, and zooming re-samples the window rather than losing detail.
    if (plotWindow.to === null || plotWindow.to > fullPoints.length - 1) {
        plotWindow = { from: 0, to: fullPoints.length - 1 };
    }
    const window_ = fullPoints.slice(plotWindow.from, plotWindow.to + 1);
    const rawValues = window_.map((p) => numericOrNull(p.total_generation_mw));
    const picks = downsampleIndices(rawValues, plotBudget());
    plottedIndices = picks.map((i) => plotWindow.from + i);

    const points = plottedIndices.map((i) => fullPoints[i]);
    chartLabels.splice(0, chartLabels.length, ...points.map((point) => formatTimestamp(point.timestamp)));
    generationReadings.splice(0, generationReadings.length, ...points.map((point) => point.total_generation_mw));
    movingAverageReadings.splice(0, movingAverageReadings.length, ...points.map((point) => point.moving_average_mw));

    if (!window.Chart) return;

    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");
    const markers = outageMarkers(points, history?.analytics?.outage_detection?.events
        ?? latestHistory?.analytics?.outage_detection?.events);
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
                        // context, not the headline: thin and translucent so
                        // the trend reads first
                        label: "Generation",
                        data: generationReadings,
                        borderColor: "rgba(37, 99, 235, 0.42)",
                        backgroundColor: "rgba(37, 99, 235, 0.03)",
                        borderWidth: 1,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBackgroundColor: "#2563EB",
                        pointHoverBorderColor: "#FFFFFF",
                        fill: true,
                        order: 2,
                    },
                    {
                        // the primary read
                        label: "Rolling average",
                        data: movingAverageReadings,
                        borderColor: "#008751",
                        borderWidth: 2.6,
                        tension: 0.3,
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
                    zoom: zoomConfig(syncZoomState),
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
    renderMarkerLegend(markers);
    renderChartStats(mainChartTools);
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

// Risk is ordinal, so it sorts by severity rather than alphabetically.
const RISK_ORDER = { overload_risk: 4, warning: 3, watch: 2, normal: 1 };

function sortAndFilterRegions(rows) {
    const term = (el["disco-filter"]?.value || "").trim().toLowerCase();
    const risk = el["disco-risk-filter"]?.value || "";
    let out = rows.filter((row) => {
        if (risk && row.overload_warning !== risk) return false;
        if (!term) return true;
        return `${row.company || ""} ${row.planning_region || ""}`.toLowerCase().includes(term);
    });
    if (regionSort.key) {
        const dir = regionSort.direction === "asc" ? 1 : -1;
        out = out.slice().sort((a, b) => {
            let av = a[regionSort.key];
            let bv = b[regionSort.key];
            if (regionSort.key === "overload_warning") {
                av = RISK_ORDER[av] || 0;
                bv = RISK_ORDER[bv] || 0;
            }
            if (typeof av === "string" || typeof bv === "string") {
                return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
            }
            return ((numericOrNull(av) ?? -Infinity) - (numericOrNull(bv) ?? -Infinity)) * dir;
        });
    }
    return out;
}

function renderRegionCount(shown, total) {
    if (!el["disco-count"]) return;
    el["disco-count"].textContent = shown === total
        ? `${formatNumber(total, 0)} regions`
        : `${formatNumber(shown, 0)} of ${formatNumber(total, 0)} regions`;
}

function renderDistributionTable(rows) {
    latestRegionRows = rows || [];
    const total = latestRegionRows.length;
    rows = sortAndFilterRegions(latestRegionRows);
    renderRegionCount(rows.length, total);
    [...document.querySelectorAll(".th-sort")].forEach((button) => {
        const active = button.dataset.sort === regionSort.key;
        button.classList.toggle("is-sorted", active);
        button.setAttribute("aria-sort", active
            ? (regionSort.direction === "asc" ? "ascending" : "descending")
            : "none");
    });
    if (!rows || rows.length === 0) {
        el["distribution-table"].innerHTML = total
            ? `<tr><td colspan="4">No regions match the current filter.</td></tr>`
            : `<tr><td colspan="4">No regions available.</td></tr>`;
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

    latestHistory = history || latestHistory;
    latestSnapshot = latest || latestSnapshot;

    if (history) {
        renderCoverageNote(history.history || []);
        scheduleChartWork(el.chart, () => renderChart(history));
        scheduleChartWork(el["generation-sparkline"], () => renderSparkline(history.history || []));
        if (el["generation-modal"] && !el["generation-modal"].hidden) renderGenerationModal();
    }
    if (distribution) {
        scheduleChartWork(el["distribution-chart"], () => renderDistribution(distribution, resultError(results, "distribution")));
    }
}

// Finds the reading nearest a target offset back from the newest point, so
// "same time yesterday" tolerates irregular capture intervals.
function readingAtOffset(points, hoursBack, toleranceHours) {
    if (!points || !points.length) return null;
    const newest = Date.parse(points[points.length - 1]?.timestamp);
    if (Number.isNaN(newest)) return null;
    const target = newest - (hoursBack * 3600000);
    const tolerance = toleranceHours * 3600000;
    let best = null;
    let bestGap = Infinity;
    points.forEach((point) => {
        const at = Date.parse(point?.timestamp);
        if (Number.isNaN(at)) return;
        const gap = Math.abs(at - target);
        if (gap < bestGap) {
            bestGap = gap;
            best = point;
        }
    });
    return bestGap <= tolerance ? best : null;
}

function renderComparison(valueId, noteId, current, past, label) {
    const now = numericOrNull(current);
    const then = numericOrNull(past?.total_generation_mw);
    if (!el[valueId]) return;
    if (now === null || then === null) {
        el[valueId].textContent = "Not available";
        el[valueId].className = "";
        if (el[noteId]) el[noteId].textContent = `No stored reading near ${label}.`;
        return;
    }
    const delta = now - then;
    const percent = then === 0 ? null : (delta / then) * 100;
    el[valueId].textContent = `${delta >= 0 ? "+" : "-"}${formatMW(Math.abs(delta))}`;
    el[valueId].className = delta > 0 ? "up" : delta < 0 ? "down" : "";
    if (el[noteId]) {
        el[noteId].textContent = percent === null
            ? `From ${formatMW(then)} at ${label}.`
            : `${percent >= 0 ? "+" : ""}${formatNumber(percent)}% from ${formatMW(then)}.`;
    }
}

function renderGenerationModal() {
    const points = latestHistory?.history || [];
    const snapshot = latestSnapshot || {};
    const current = numericOrNull(snapshot.total_generation_mw)
        ?? numericOrNull(points[points.length - 1]?.total_generation_mw);

    if (el["modal-current"]) {
        el["modal-current"].textContent = current === null ? "Not available" : formatMW(current);
    }
    if (el["modal-current-note"]) {
        el["modal-current-note"].textContent = snapshot.fetched_at
            ? `As at ${fullTimestamp(snapshot.fetched_at)}.`
            : "Latest stored reading.";
    }

    const capacity = numericOrNull(
        snapshot.available_capacity_mw
            ?? snapshot.available_generation_capacity_mw
            ?? snapshot.daily?.peak_generation_mw,
    );
    if (el["modal-utilization"]) {
        if (current === null || capacity === null || capacity === 0) {
            el["modal-utilization"].textContent = "Not available";
            if (el["modal-utilization-note"]) {
                el["modal-utilization-note"].textContent = "Available capacity not reported by the source.";
            }
        } else {
            el["modal-utilization"].textContent = `${formatNumber((current / capacity) * 100)}%`;
            if (el["modal-utilization-note"]) {
                el["modal-utilization-note"].textContent = `${formatMW(current)} of ${formatMW(capacity)} available.`;
            }
        }
    }

    renderComparison("modal-yesterday", "modal-yesterday-note", current,
        readingAtOffset(points, 24, 3), "24 hours ago");
    renderComparison("modal-lastweek", "modal-lastweek-note", current,
        readingAtOffset(points, 168, 12), "seven days ago");

    // GenCo contribution, largest first
    const gencos = (snapshot.gencos || [])
        .map((row) => ({ plant: row.plant, mw: numericOrNull(row.generation_mw) }))
        .filter((row) => row.mw !== null && row.mw > 0)
        .sort((a, b) => b.mw - a.mw);
    if (el["modal-genco-rows"]) {
        if (!gencos.length) {
            el["modal-genco-rows"].innerHTML = `<tr><td colspan="2">No GenCo output available.</td></tr>`;
        } else {
            const total = gencos.reduce((sum, row) => sum + row.mw, 0);
            el["modal-genco-rows"].innerHTML = gencos.map((row) => {
                const share = total > 0 ? ` (${formatNumber((row.mw / total) * 100, 1)}%)` : "";
                return `<tr><td>${escapeHTML(row.plant)}</td><td>${escapeHTML(formatMW(row.mw))}${escapeHTML(share)}</td></tr>`;
            }).join("");
        }
    }

    renderModalTrend(points);
}

function renderModalTrend(points) {
    if (!el["modal-trend-chart"]) return;
    const hasPoints = points.length > 0;
    if (el["modal-trend-empty"]) el["modal-trend-empty"].classList.toggle("visible", !hasPoints);
    if (el["modal-trend-note"]) {
        const covered = historyCoverageHours(points);
        el["modal-trend-note"].textContent = covered === null
            ? "Stored readings across the selected window."
            : `${formatNumber(points.length, 0)} stored readings across ${describeWindow(covered)}.`;
    }
    if (!window.Chart || !hasPoints) return;

    const labels = points.map((p) => formatTimestamp(p.timestamp));
    const values = points.map((p) => numericOrNull(p.total_generation_mw));
    const averages = points.map((p) => numericOrNull(p.moving_average_mw));
    modalPoints = points;
    modalReadings.splice(0, modalReadings.length, ...values);
    const gridColor = cssVar("--line", "rgba(11, 31, 58, 0.14)");

    if (!modalTrendChart) {
        modalTrendChart = new Chart(el["modal-trend-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Generation",
                        data: values,
                        borderColor: "#2563EB",
                        backgroundColor: "rgba(37, 99, 235, 0.05)",
                        borderWidth: 1.8,
                        tension: 0.25,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        fill: true,
                    },
                    {
                        label: "Rolling average",
                        data: averages,
                        borderColor: "rgba(0, 135, 81, 0.55)",
                        borderDash: [5, 5],
                        borderWidth: 1.2,
                        tension: 0.25,
                        pointRadius: 0,
                        fill: false,
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
                    tooltip: analystTooltip({
                        callbacks: {
                            title: (items) => (items.length ? fullTimestamp(modalPoints[items[0].dataIndex]?.timestamp) : ""),
                            label: (ctx) => `${ctx.dataset.label}: ${formatMW(ctx.parsed.y)}`,
                            afterBody: (items) => {
                                if (!items.length) return "";
                                const index = items[0].dataIndex;
                                const value = numericOrNull(modalReadings[index]);
                                return `Operating band: ${generationBandName(value)}`;
                            },
                        },
                    }),
                    operatingBands: { axis: "y", bands: generationBands() },
                    zoom: zoomConfig(syncModalZoomState),
                },
                scales: {
                    x: {
                        ticks: Object.assign(analystTicks(), { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 }),
                        grid: { display: false },
                        border: { color: gridColor },
                    },
                    y: {
                        beginAtZero: false,
                        ticks: Object.assign(analystTicks(), { callback: (v) => formatNumber(v, 0), maxTicksLimit: 5 }),
                        grid: { color: gridColor, drawTicks: false },
                        border: { display: false },
                    },
                },
            },
        });
    } else {
        modalTrendChart.data.labels = labels;
        modalTrendChart.data.datasets[0].data = values;
        modalTrendChart.data.datasets[1].data = averages;
        applyChartTheme(modalTrendChart);
        modalTrendChart.update("none");
    }
    renderChartStats(modalChartTools);
}

// The drill-down keeps its own window so it can be explored without
// disturbing the dashboard chart behind it.
function selectModalRange(hours, button) {
    if (modalHours === hours) return;
    modalHours = hours;
    [...el["modal-range"].querySelectorAll(".range-btn")].forEach((node) => {
        const active = node === button;
        node.classList.toggle("is-active", active);
        node.setAttribute("aria-pressed", active ? "true" : "false");
    });
    resetZoomFor(modalChartTools);
    fetchJSON(`/api/history?hours=${hours}&limit=${HISTORY_LIMIT}`)
        .then((payload) => {
            renderModalTrend(payload?.history || []);
        })
        .catch((error) => setBanner(error.message));
}

// options.hours preselects a range; options.section scrolls the dialog to the
// part of the analysis the caller came from.
function openGenerationModal(options = {}) {
    const modal = el["generation-modal"];
    if (!modal) return;
    modalReturnFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add("modal-open");
    scheduleChartWork(el["modal-trend-chart"], renderGenerationModal);
    renderGenerationModal();
    if (options.hours && el["modal-range"]) {
        const button = el["modal-range"].querySelector(`.range-btn[data-hours="${options.hours}"]`);
        if (button) selectModalRange(options.hours, button);
    }
    if (el["generation-modal-close"]) {
        el["generation-modal-close"].focus({ preventScroll: Boolean(options.section) });
    }
    const section = options.section ? document.getElementById(options.section) : null;
    if (section) {
        window.requestAnimationFrame(() => section.scrollIntoView({ block: "start" }));
    }
}

// Grid Analytics cards are entry points rather than dead-end figures: each one
// routes to the existing view that explains it, so nothing new is duplicated.
function revealSection(targetSelector, focusSelector) {
    const target = targetSelector ? document.querySelector(targetSelector) : null;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    const flash = (focusSelector && document.querySelector(focusSelector)) || target;
    flash.classList.add("is-drill-target");
    window.setTimeout(() => flash.classList.remove("is-drill-target"), 2400);
}

function runInsightDrill(button) {
    if (button.dataset.drill === "modal") {
        openGenerationModal({
            hours: Number(button.dataset.drillHours) || null,
            section: button.dataset.drillSection,
        });
        return;
    }
    if (button.dataset.drill === "section") {
        revealSection(button.dataset.drillTarget, button.dataset.drillFocus);
    }
}

function closeGenerationModal() {
    const modal = el["generation-modal"];
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove("modal-open");
    if (modalReturnFocus && typeof modalReturnFocus.focus === "function") modalReturnFocus.focus();
    modalReturnFocus = null;
}

// Keeps tab focus inside the dialog while it is open.
function trapModalFocus(event) {
    const modal = el["generation-modal"];
    if (!modal || modal.hidden || event.key !== "Tab") return;
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

function toggleBrush() {
    toggleBrushFor(mainChartTools);
}

// Exports whatever slice of the generation series is currently in view.
function exportVisibleCsv() {
    // full resolution for the visible window, never the thinned plot series
    const [from, to] = visibleFullRange();
    if (to < from) return;
    const points = fullPoints.slice(from, to + 1);
    if (!points.length) return;
    const rows = [["timestamp", "generation_mw", "moving_average_mw"]];
    points.forEach((point) => {
        rows.push([
            point.timestamp ?? "",
            numericOrNull(point.total_generation_mw) ?? "",
            numericOrNull(point.moving_average_mw) ?? "",
        ]);
    });
    const csv = rows.map((row) => row.map((cell) => {
        const text = String(cell);
        return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
    }).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `nigeria-generation-${describeWindow(historyHours).replace(/\s+/g, "")}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function toggleChartFullscreen() {
    const card = document.getElementById("generation");
    if (!card) return;
    const active = document.fullscreenElement;
    if (active) {
        if (document.exitFullscreen) document.exitFullscreen();
        return;
    }
    if (card.requestFullscreen) card.requestFullscreen().catch(() => undefined);
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
if (el["chart-brush"]) el["chart-brush"].addEventListener("click", toggleBrush);
if (el["chart-export"]) el["chart-export"].addEventListener("click", exportVisibleCsv);
if (el["chart-fullscreen"]) el["chart-fullscreen"].addEventListener("click", toggleChartFullscreen);
if (el["modal-brush"]) el["modal-brush"].addEventListener("click", () => toggleBrushFor(modalChartTools));
if (el["modal-reset"]) el["modal-reset"].addEventListener("click", () => resetZoomFor(modalChartTools));
if (el["modal-range"]) {
    el["modal-range"].addEventListener("click", (event) => {
        const button = event.target.closest(".range-btn");
        if (button && !button.disabled) selectModalRange(Number(button.dataset.hours), button);
    });
}
// re-render the table in place; the payload is already in memory
const rerenderRegions = () => renderDistributionTable(latestRegionRows);
if (el["disco-filter"]) el["disco-filter"].addEventListener("input", rerenderRegions);
if (el["disco-risk-filter"]) el["disco-risk-filter"].addEventListener("change", rerenderRegions);
document.addEventListener("click", (event) => {
    const sorter = event.target.closest(".th-sort");
    if (!sorter) return;
    const key = sorter.dataset.sort;
    if (regionSort.key === key) {
        regionSort.direction = regionSort.direction === "asc" ? "desc" : "asc";
    } else {
        regionSort.key = key;
        regionSort.direction = key === "company" ? "asc" : "desc";
    }
    rerenderRegions();
});
document.addEventListener("fullscreenchange", () => {
    const on = Boolean(document.fullscreenElement);
    if (el["chart-fullscreen"]) el["chart-fullscreen"].textContent = on ? "Exit full screen" : "Full screen";
    if (chart) chart.resize();
});
if (el["chart-range"]) {
    el["chart-range"].addEventListener("click", (event) => {
        const button = event.target.closest(".range-btn");
        if (button && !button.disabled) selectHistoryRange(Number(button.dataset.hours), button);
    });
}
if (el.chart) {
    el.chart.addEventListener("pointerdown", beginWindowPan);
    el.chart.addEventListener("pointermove", moveWindowPan);
    el.chart.addEventListener("pointerup", endWindowPan);
    el.chart.addEventListener("pointercancel", endWindowPan);
}
if (el["generation-drill"]) el["generation-drill"].addEventListener("click", () => openGenerationModal());
// The whole card is clickable, but the button carries the accessible name so
// keyboard users get one focus stop per card rather than a bare div.
document.addEventListener("click", (event) => {
    const drill = event.target.closest(".insight-drill");
    if (drill) {
        runInsightDrill(drill);
        return;
    }
    const card = event.target.closest(".insight-card.is-drillable");
    const inner = card && card.querySelector(".insight-drill");
    if (inner) runInsightDrill(inner);
});
if (el["generation-modal-close"]) el["generation-modal-close"].addEventListener("click", closeGenerationModal);
if (el["generation-modal"]) {
    el["generation-modal"].addEventListener("click", (event) => {
        if (event.target === el["generation-modal"]) closeGenerationModal();
    });
}
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeGenerationModal();
    trapModalFocus(event);
});
refresh().catch((error) => {
    setBanner(error.message);
    el.status.textContent = "Source unavailable";
    el.status.className = "status-badge badge critical";
    el["status-icon"].className = "status-icon critical";
    el.insight.textContent = "No live or stored grid data is currently available.";
    document.body.classList.remove("loading");
});
setInterval(() => refresh().catch((error) => setBanner(error.message)), REFRESH_MS);
