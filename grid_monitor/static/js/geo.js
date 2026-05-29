const GEO_REFRESH_MS = 120000;
let geoChart;

const geoIds = [
    "theme-toggle", "geo-refresh-state", "geo-error-banner", "geo-title",
    "geo-lede", "geo-rank-pill", "geo-risk-pill", "geo-region-pill",
    "geo-disco-summary", "geo-generated", "geo-allocation", "geo-trend",
    "geo-risk", "geo-allocation-note", "geo-peak-demand", "geo-demand-note",
    "geo-reliability", "geo-reliability-note", "geo-transformer-risk",
    "geo-transformer-note", "geo-window", "geo-chart", "geo-chart-empty",
    "geo-allocation-rank", "geo-allocation-rank-note", "geo-stress-rank",
    "geo-stress-rank-note", "geo-availability", "geo-availability-note",
    "geo-summary", "geo-forecast-method", "geo-forecast-24h",
    "geo-forecast-7d", "geo-population", "geo-settlement", "geo-risk-driver",
    "geo-stress", "geo-demand-growth", "geo-high", "geo-low", "geo-related",
    "geo-related-title",
];
const geoEl = Object.fromEntries(geoIds.map((id) => [id, document.getElementById(id)]));

function initGeoTheme() {
    const stored = localStorage.getItem("grid-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored || (prefersDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    geoEl["theme-toggle"].textContent = theme === "dark" ? "Light" : "Dark";
}

function toggleGeoTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("grid-theme", next);
    geoEl["theme-toggle"].textContent = next === "dark" ? "Light" : "Dark";
    if (geoChart) geoChart.update();
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
    if (["critical", "elevated", "warning"].includes(value)) return "red";
    if (["watch", "stressed"].includes(value)) return "amber";
    if (["normal", "stable", "strong"].includes(value)) return "green";
    return "blue";
}

function setGeoBanner(message) {
    geoEl["geo-error-banner"].textContent = message || "";
    geoEl["geo-error-banner"].classList.toggle("visible", Boolean(message));
}

async function fetchGeoJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed: ${url}`);
    return payload;
}

function renderGeoChart(payload) {
    const history = payload.history || [];
    const hasPoints = history.length > 0;
    geoEl["geo-chart-empty"].classList.toggle("visible", !hasPoints);
    if (!window.Chart || !hasPoints) return;

    const labels = history.map((point) => formatTimestamp(point.timestamp));
    const allocation = history.map((point) => point.estimated_allocation_mw);
    const movingAverage = history.map((point) => point.moving_average_mw);
    const availability = history.map((point) => point.power_availability_estimate_percent);
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();

    if (!geoChart) {
        geoChart = new Chart(geoEl["geo-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Estimated allocation",
                        data: allocation,
                        borderColor: "#206bc4",
                        backgroundColor: "rgba(32, 107, 196, 0.13)",
                        borderWidth: 3,
                        tension: 0.32,
                        pointRadius: 2,
                        fill: true,
                        yAxisID: "mw",
                    },
                    {
                        label: "Moving average",
                        data: movingAverage,
                        borderColor: "#18a66a",
                        borderDash: [6, 4],
                        borderWidth: 2,
                        tension: 0.28,
                        pointRadius: 0,
                        yAxisID: "mw",
                    },
                    {
                        label: "Availability estimate",
                        data: availability,
                        borderColor: "#f2b84b",
                        borderWidth: 2,
                        tension: 0.25,
                        pointRadius: 0,
                        yAxisID: "availability",
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
                            label: (context) => context.dataset.yAxisID === "availability"
                                ? `${context.dataset.label}: ${formatNumber(context.parsed.y)}%`
                                : `${context.dataset.label}: ${formatMW(context.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } },
                    mw: {
                        beginAtZero: false,
                        ticks: { callback: (value) => formatNumber(value, 0) },
                        grid: { color: gridColor },
                    },
                    availability: {
                        position: "right",
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: { callback: (value) => `${value}%` },
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    } else {
        geoChart.data.labels = labels;
        geoChart.data.datasets[0].data = allocation;
        geoChart.data.datasets[1].data = movingAverage;
        geoChart.data.datasets[2].data = availability;
        geoChart.options.scales.mw.grid.color = gridColor;
        geoChart.update();
    }
}

function renderRelated(payload) {
    const related = payload.scope === "region" ? payload.states || [] : payload.related || [];
    geoEl["geo-related-title"].textContent = payload.scope === "region" ? "States In Region" : "State Peers";
    geoEl["geo-related"].innerHTML = related
        .map((item) => `<a href="${escapeHTML(item.url)}"><strong>${escapeHTML(item.short_name || item.name)}</strong><span>${escapeHTML(item.region || "")}</span></a>`)
        .join("");
}

function renderGeo(payload) {
    const entity = payload.entity || {};
    const stats = payload.statistics || {};
    const metrics = payload.metrics || {};
    const trend = payload.trend || {};
    const forecast = payload.forecast || {};
    const risk = payload.risk || {};
    const rankings = payload.rankings || {};
    const discos = payload.responsible_discos || [];
    const peerLabel = payload.scope === "region" ? "regions" : "states/FCT";

    document.title = `${entity.short_name || entity.name} ${payload.scope === "region" ? "Regional" : "State"} Intelligence | Nigeria Power Data`;
    geoEl["geo-title"].textContent = entity.short_name || entity.name;
    geoEl["geo-lede"].textContent = `${entity.name} ${payload.scope} allocation, demand, infrastructure stress, transformer risk, and reliability indicators.`;
    geoEl["geo-region-pill"].textContent = payload.scope === "region" ? `${payload.states?.length || 0} states` : entity.region;
    geoEl["geo-disco-summary"].textContent = discos.length
        ? `Responsible DisCo(s): ${discos.map((item) => item.name).join(", ")}`
        : "Responsible DisCos pending source data";
    geoEl["geo-generated"].textContent = `Generated ${formatTimestamp(payload.generated_at)}`;
    geoEl["geo-window"].textContent = `${payload.window_hours} hours`;

    geoEl["geo-allocation"].innerHTML = `<span>${formatNumber(stats.latest_mw)}</span><span class="mw-unit">MW</span>`;
    geoEl["geo-allocation"].className = "mw";
    geoEl["geo-allocation-note"].textContent = `${payload.sample_count} stored readings. Peak demand estimate ${formatMW(metrics.estimated_peak_demand_mw)}.`;

    const trendClass = trend.direction === "up" ? "green" : trend.direction === "down" ? "red" : "blue";
    const trendArrow = trend.direction === "up" ? "&uarr;" : trend.direction === "down" ? "&darr;" : "&rarr;";
    geoEl["geo-trend"].innerHTML = `${trendArrow} ${trend.change_mw > 0 ? "+" : ""}${formatMW(trend.change_mw)}`;
    geoEl["geo-trend"].className = `badge ${trendClass}`;

    geoEl["geo-risk"].textContent = labelize(risk.classification);
    geoEl["geo-risk"].className = `badge ${badgeClassForRisk(risk.classification)}`;
    geoEl["geo-risk-pill"].textContent = `Risk: ${labelize(risk.classification)}`;
    geoEl["geo-risk-pill"].className = `badge ${badgeClassForRisk(risk.classification)}`;

    geoEl["geo-peak-demand"].textContent = formatMW(metrics.estimated_peak_demand_mw);
    geoEl["geo-demand-note"].textContent = `${formatNumber(metrics.estimated_demand_growth_percent, 1)}% estimated demand growth.`;
    geoEl["geo-reliability"].textContent = `${formatNumber(metrics.grid_reliability_score, 1)}/100`;
    geoEl["geo-reliability-note"].textContent = `Reliability rank ${rankings.reliability_rank || "..."} of ${rankings.peer_count} ${peerLabel}.`;
    geoEl["geo-transformer-risk"].textContent = `${formatNumber(metrics.transformer_risk_score, 1)}/100`;
    geoEl["geo-transformer-note"].textContent = `Driven by settlement growth and infrastructure stress.`;
    geoEl["geo-allocation-rank"].textContent = rankings.allocation_rank ? `#${rankings.allocation_rank}` : "...";
    geoEl["geo-allocation-rank-note"].textContent = `Out of ${rankings.peer_count} ${peerLabel}.`;
    geoEl["geo-rank-pill"].textContent = rankings.allocation_rank ? `Allocation rank #${rankings.allocation_rank}` : "Ranking pending";
    geoEl["geo-stress-rank"].textContent = rankings.stress_rank ? `#${rankings.stress_rank}` : "...";
    geoEl["geo-stress-rank-note"].textContent = `Lower stress ranks better among ${peerLabel}.`;
    geoEl["geo-availability"].textContent = `${formatNumber(metrics.power_availability_estimate_percent, 1)}%`;
    geoEl["geo-availability-note"].textContent = "Estimated allocation divided by peak demand proxy.";
    geoEl["geo-summary"].textContent = payload.analysis_summary;
    geoEl["geo-forecast-method"].textContent = labelize(forecast.method);
    geoEl["geo-forecast-24h"].textContent = formatMW(forecast.next_24h_mw);
    geoEl["geo-forecast-7d"].textContent = formatMW(forecast.next_7d_mw);
    geoEl["geo-population"].textContent = `${formatNumber(metrics.population_served_estimate_m, 2)}m`;
    geoEl["geo-settlement"].textContent = `${formatNumber(metrics.settlement_growth_indicator, 1)}/100`;
    geoEl["geo-risk-driver"].textContent = labelize(risk.primary_driver);
    geoEl["geo-stress"].textContent = `${formatNumber(metrics.infrastructure_stress_score, 1)}/100`;
    geoEl["geo-demand-growth"].textContent = `${formatNumber(metrics.estimated_demand_growth_percent, 1)}%`;
    geoEl["geo-high"].textContent = formatMW(stats.highest_mw);
    geoEl["geo-low"].textContent = formatMW(stats.lowest_mw);

    renderGeoChart(payload);
    renderRelated(payload);
}

async function refreshGeo() {
    document.body.classList.add("loading");
    geoEl["geo-refresh-state"].textContent = "Refreshing...";
    setGeoBanner("");
    try {
        const page = window.GEO_PAGE || {};
        const payload = await fetchGeoJSON(`/api/${page.collection}/${page.slug}?hours=168&limit=1000`);
        renderGeo(payload);
        geoEl["geo-refresh-state"].textContent = `Last refresh ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        setGeoBanner(error.message);
        geoEl["geo-refresh-state"].textContent = "Refresh failed";
    } finally {
        document.body.classList.remove("loading");
    }
}

initGeoTheme();
geoEl["theme-toggle"].addEventListener("click", toggleGeoTheme);
refreshGeo();
setInterval(refreshGeo, GEO_REFRESH_MS);
