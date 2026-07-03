const CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js";
let hierarchyChart;
let searchTimer;
let chartLibraryPromise = null;
window.requestAnimationFrame(() => document.body.classList.add("brand-loaded"));

const hierarchyIds = [
    "theme-toggle", "hierarchy-refresh-state", "hierarchy-error-banner",
    "hierarchy-search", "hierarchy-search-results", "state-marker-layer",
    "hierarchy-state-grid", "map-count", "hierarchy-dataset",
    "hierarchy-dataset-note", "hierarchy-watch-count", "hierarchy-search-count",
    "hierarchy-breadcrumbs", "hierarchy-eyebrow", "hierarchy-title",
    "hierarchy-lede", "hierarchy-level-pill", "hierarchy-health-pill",
    "hierarchy-disco-pill", "hierarchy-path", "hierarchy-generated",
    "hierarchy-demand", "hierarchy-growth", "hierarchy-source",
    "hierarchy-demand-note", "hierarchy-population", "hierarchy-population-note",
    "hierarchy-transformer", "hierarchy-transformer-note", "hierarchy-health",
    "hierarchy-health-note", "hierarchy-demand-chart", "hierarchy-chart-empty",
    "hierarchy-classification", "hierarchy-peak", "hierarchy-availability",
    "hierarchy-stress", "hierarchy-summary", "hierarchy-primary-disco",
    "hierarchy-coverage", "hierarchy-upgrade-count", "hierarchy-upgrades",
    "hierarchy-children-title", "hierarchy-children",
];
const hierarchyEl = Object.fromEntries(hierarchyIds.map((id) => [id, document.getElementById(id)]));

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

function scheduleChartRender(target, callback) {
    const run = () => {
        if ("requestIdleCallback" in window) {
            window.requestIdleCallback(() => loadChartLibrary().then(callback).catch((error) => setBanner(error.message)), { timeout: 1800 });
        } else {
            window.setTimeout(() => loadChartLibrary().then(callback).catch((error) => setBanner(error.message)), 0);
        }
    };
    if (window.Chart) {
        window.requestAnimationFrame(run);
        return;
    }
    if (target && "IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                observer.disconnect();
                window.requestAnimationFrame(run);
            }
        }, { rootMargin: "180px 0px" });
        observer.observe(target);
        return;
    }
    window.setTimeout(run, 3500);
}

function hasEl(id) {
    return Boolean(hierarchyEl[id]);
}

function initHierarchyTheme() {
    const stored = localStorage.getItem("grid-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = stored || (prefersDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
    if (hasEl("theme-toggle")) hierarchyEl["theme-toggle"].textContent = theme === "dark" ? "Light" : "Dark";
}

function toggleHierarchyTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("grid-theme", next);
    if (hasEl("theme-toggle")) hierarchyEl["theme-toggle"].textContent = next === "dark" ? "Light" : "Dark";
    if (hierarchyChart) hierarchyChart.update("none");
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

function formatPopulation(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "...";
    const numeric = Number(value);
    if (numeric >= 1000000) return `${formatNumber(numeric / 1000000, 2)}m`;
    if (numeric >= 1000) return `${formatNumber(numeric / 1000, 1)}k`;
    return formatNumber(numeric, 0);
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
    return String(value || "unknown").replaceAll("_", " ").replaceAll("-", " ");
}

function riskClass(value) {
    if (["critical"].includes(value)) return "red";
    if (["elevated", "watch"].includes(value)) return "amber";
    if (["stable", "normal"].includes(value)) return "green";
    return "blue";
}

function setBanner(message) {
    if (!hasEl("hierarchy-error-banner")) return;
    hierarchyEl["hierarchy-error-banner"].textContent = message || "";
    hierarchyEl["hierarchy-error-banner"].classList.toggle("visible", Boolean(message));
}

async function fetchJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed: ${url}`);
    return payload;
}

function searchResultHTML(item) {
    const metrics = item.metrics || {};
    const badge = item.risk_classification ? `<span class="badge ${riskClass(item.risk_classification)}">${escapeHTML(labelize(item.risk_classification))}</span>` : "";
    return `
        <a class="search-result-item" href="${escapeHTML(item.url)}">
            <strong>${escapeHTML(item.name)}</strong>
            <span>${escapeHTML(item.level_label)} in ${escapeHTML(item.state)} · ${escapeHTML(item.region)}</span>
            <small>${formatPopulation(metrics.estimated_population)} people · ${formatMW(metrics.estimated_current_demand_mw)} demand</small>
            ${badge}
        </a>
    `;
}

async function runSearch() {
    if (!hasEl("hierarchy-search") || !hasEl("hierarchy-search-results")) return;
    const query = hierarchyEl["hierarchy-search"].value.trim();
    if (query.length < 2) {
        hierarchyEl["hierarchy-search-results"].innerHTML = "";
        hierarchyEl["hierarchy-search-results"].classList.remove("visible");
        return;
    }
    try {
        const payload = await fetchJSON(`/api/geography/search?q=${encodeURIComponent(query)}&limit=12`);
        hierarchyEl["hierarchy-search-results"].innerHTML = payload.results.length
            ? payload.results.map(searchResultHTML).join("")
            : `<div class="search-empty">No geography results found.</div>`;
        hierarchyEl["hierarchy-search-results"].classList.add("visible");
    } catch (error) {
        hierarchyEl["hierarchy-search-results"].innerHTML = `<div class="search-empty">${escapeHTML(error.message)}</div>`;
        hierarchyEl["hierarchy-search-results"].classList.add("visible");
    }
}

function bindSearch() {
    if (!hasEl("hierarchy-search")) return;
    hierarchyEl["hierarchy-search"].addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(runSearch, 180);
    });
}

function stateCardHTML(state) {
    const metrics = state.metrics || {};
    const risk = state.risk_classification || "unknown";
    return `
        <a href="${escapeHTML(state.url)}">
            <strong>${escapeHTML(state.short_name || state.name)}</strong>
            <span>${escapeHTML(state.region)} · ${formatMW(metrics.estimated_current_demand_mw)} demand</span>
            <small class="badge ${riskClass(risk)}">${escapeHTML(labelize(risk))}</small>
        </a>
    `;
}

function renderMap(payload) {
    const states = payload.states || [];
    const watchCount = states.filter((state) => ["critical", "elevated", "watch"].includes(state.risk_classification)).length;
    if (hasEl("map-count")) hierarchyEl["map-count"].textContent = `${states.length} state markers`;
    if (hasEl("hierarchy-dataset")) hierarchyEl["hierarchy-dataset"].textContent = labelize(payload.dataset?.active_dataset);
    if (hasEl("hierarchy-dataset-note")) hierarchyEl["hierarchy-dataset-note"].textContent = payload.dataset?.method || "Planning dataset";
    if (hasEl("hierarchy-watch-count")) hierarchyEl["hierarchy-watch-count"].textContent = watchCount;
    if (hasEl("hierarchy-search-count")) {
        const counts = payload.counts || {};
        const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
        hierarchyEl["hierarchy-search-count"].textContent = total.toLocaleString();
    }
    if (hasEl("state-marker-layer")) {
        hierarchyEl["state-marker-layer"].innerHTML = states.map((state) => {
            const metrics = state.metrics || {};
            return `
                <a class="state-marker ${riskClass(state.risk_classification)}" href="${escapeHTML(state.url)}"
                   style="left: ${state.map_x}%; top: ${state.map_y}%"
                   title="${escapeHTML(state.name)} · ${formatMW(metrics.estimated_current_demand_mw)}">
                    <span>${escapeHTML((state.short_name || state.name).slice(0, 3))}</span>
                </a>
            `;
        }).join("");
    }
    if (hasEl("hierarchy-state-grid")) {
        hierarchyEl["hierarchy-state-grid"].innerHTML = states.map(stateCardHTML).join("");
    }
}

function renderBreadcrumbs(payload) {
    if (!hasEl("hierarchy-breadcrumbs")) return;
    const crumbs = payload.breadcrumbs || [];
    hierarchyEl["hierarchy-breadcrumbs"].innerHTML = [
        `<a href="/geography">Map</a>`,
        ...crumbs.map((crumb, index) => {
            const current = index === crumbs.length - 1;
            return current
                ? `<span>${escapeHTML(crumb.name)}</span>`
                : `<a href="${escapeHTML(crumb.url)}">${escapeHTML(crumb.name)}</a>`;
        }),
    ].join(`<span class="breadcrumb-separator">/</span>`);
}

function linkGridHTML(items) {
    if (!items || !items.length) return `<div class="empty-inline">No child areas in the current dataset.</div>`;
    return items.map((item) => {
        const metrics = item.metrics || {};
        const risk = item.risk_classification || "unknown";
        return `
            <a href="${escapeHTML(item.url)}">
                <strong>${escapeHTML(item.short_name || item.name)}</strong>
                <span>${escapeHTML(item.level_label || "")} · ${formatPopulation(metrics.estimated_population)}</span>
                <small>${formatMW(metrics.estimated_current_demand_mw)} · ${formatNumber(metrics.transformer_loading_percent, 1)}% loading</small>
                <small class="badge ${riskClass(risk)}">${escapeHTML(labelize(risk))}</small>
            </a>
        `;
    }).join("");
}

function renderCoverage(payload) {
    if (!hasEl("hierarchy-coverage")) return;
    const discos = payload.coverage?.responsible_discos || [];
    hierarchyEl["hierarchy-coverage"].innerHTML = discos.length
        ? discos.map((disco) => `
            <a href="${escapeHTML(disco.url)}">
                <strong>${escapeHTML(disco.name)}</strong>
                <span>${formatNumber(disco.share_of_state_percent, 1)}% state share basis</span>
            </a>
        `).join("")
        : `<div class="empty-inline">DisCo coverage pending.</div>`;
    if (hasEl("hierarchy-primary-disco")) {
        hierarchyEl["hierarchy-primary-disco"].textContent = payload.coverage?.primary_disco?.name || "Coverage pending";
    }
}

function renderUpgrades(payload) {
    if (!hasEl("hierarchy-upgrades")) return;
    const upgrades = payload.recommended_upgrades || [];
    if (hasEl("hierarchy-upgrade-count")) hierarchyEl["hierarchy-upgrade-count"].textContent = `${upgrades.length} actions`;
    hierarchyEl["hierarchy-upgrades"].innerHTML = upgrades.map((item) => `
        <div class="upgrade-item">
            <span class="badge blue">${escapeHTML(item.priority)}</span>
            <strong>${escapeHTML(item.title)}</strong>
            <p>${escapeHTML(item.rationale)}</p>
        </div>
    `).join("");
}

function renderProjectionChart(metrics) {
    if (!hasEl("hierarchy-demand-chart")) return;
    const values = [
        metrics.estimated_current_demand_mw,
        metrics.projected_12m_demand_mw,
        metrics.projected_36m_demand_mw,
    ];
    const hasValues = values.every((value) => value !== null && value !== undefined);
    if (hasEl("hierarchy-chart-empty")) hierarchyEl["hierarchy-chart-empty"].classList.toggle("visible", !hasValues);
    if (!window.Chart || !hasValues) return;
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
    if (!hierarchyChart) {
        hierarchyChart = new Chart(hierarchyEl["hierarchy-demand-chart"].getContext("2d"), {
            type: "line",
            data: {
                labels: ["Current", "12 months", "36 months"],
                datasets: [{
                    label: "Demand estimate",
                    data: values,
                    borderColor: "#2563EB",
                    backgroundColor: "rgba(37, 99, 235, 0.14)",
                    borderWidth: 3,
                    pointRadius: 4,
                    tension: 0.28,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (context) => formatMW(context.parsed.y) } },
                },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        beginAtZero: false,
                        grid: { color: gridColor },
                        ticks: { callback: (value) => formatNumber(value, 0) },
                    },
                },
            },
        });
    } else {
        hierarchyChart.data.datasets[0].data = values;
        hierarchyChart.options.scales.y.grid.color = gridColor;
        hierarchyChart.update("none");
    }
}

function renderDetail(payload) {
    const entity = payload.entity || {};
    const metrics = payload.metrics || {};
    const health = payload.grid_health || {};
    const primaryDisco = payload.coverage?.primary_disco?.name || "DisCo coverage pending";
    const classification = health.classification || "unknown";

    document.title = `${entity.name} ${entity.level_label} Intelligence | Nigeria Power Data`;
    renderBreadcrumbs(payload);
    hierarchyEl["hierarchy-eyebrow"].textContent = `${entity.level_label} Intelligence`;
    hierarchyEl["hierarchy-title"].textContent = entity.name;
    hierarchyEl["hierarchy-lede"].textContent = `${entity.name} power demand, transformer loading, DisCo coverage, grid health, and infrastructure upgrade signals.`;
    hierarchyEl["hierarchy-level-pill"].textContent = entity.level_label;
    hierarchyEl["hierarchy-health-pill"].textContent = `Health: ${labelize(classification)}`;
    hierarchyEl["hierarchy-health-pill"].className = `badge ${riskClass(classification)}`;
    hierarchyEl["hierarchy-disco-pill"].textContent = primaryDisco;
    hierarchyEl["hierarchy-path"].textContent = `${entity.state} · ${entity.region}`;
    hierarchyEl["hierarchy-generated"].textContent = `Generated ${formatTimestamp(payload.generated_at)}`;

    hierarchyEl["hierarchy-demand"].innerHTML = `<span>${formatNumber(metrics.estimated_current_demand_mw)}</span><span class="mw-unit">MW</span>`;
    hierarchyEl["hierarchy-demand"].className = "mw";
    hierarchyEl["hierarchy-growth"].textContent = `${formatNumber(metrics.projected_demand_growth_percent, 1)}% growth`;
    hierarchyEl["hierarchy-growth"].className = "badge blue";
    hierarchyEl["hierarchy-source"].textContent = labelize(metrics.allocation_source);
    hierarchyEl["hierarchy-demand-note"].textContent = `Peak demand estimate ${formatMW(metrics.estimated_peak_demand_mw)}.`;
    hierarchyEl["hierarchy-population"].textContent = formatPopulation(metrics.estimated_population);
    hierarchyEl["hierarchy-population-note"].textContent = `${formatNumber(metrics.estimated_population_m, 3)} million planning estimate.`;
    hierarchyEl["hierarchy-transformer"].textContent = `${formatNumber(metrics.transformer_loading_percent, 1)}%`;
    hierarchyEl["hierarchy-transformer-note"].textContent = `Settlement indicator ${formatNumber(metrics.settlement_growth_indicator, 1)}/100.`;
    hierarchyEl["hierarchy-health"].textContent = `${formatNumber(metrics.grid_health_score, 1)}/100`;
    hierarchyEl["hierarchy-health-note"].textContent = `${labelize(classification)} grid health classification.`;
    hierarchyEl["hierarchy-classification"].textContent = labelize(classification);
    hierarchyEl["hierarchy-classification"].className = `badge ${riskClass(classification)}`;
    hierarchyEl["hierarchy-peak"].textContent = formatMW(metrics.estimated_peak_demand_mw);
    hierarchyEl["hierarchy-availability"].textContent = `${formatNumber(metrics.power_availability_percent, 1)}%`;
    hierarchyEl["hierarchy-stress"].textContent = `${formatNumber(metrics.infrastructure_stress_score, 1)}/100`;
    hierarchyEl["hierarchy-summary"].textContent = payload.analysis_summary;

    scheduleChartRender(hierarchyEl["hierarchy-demand-chart"], () => renderProjectionChart(metrics));
    renderCoverage(payload);
    renderUpgrades(payload);
    if (hasEl("hierarchy-children-title")) {
        hierarchyEl["hierarchy-children-title"].textContent = payload.child_level
            ? `${labelize(payload.child_level)} Drill-Down Areas`
            : "Terminal Settlement Zone";
    }
    if (hasEl("hierarchy-children")) hierarchyEl["hierarchy-children"].innerHTML = linkGridHTML(payload.children || []);
}

async function loadIndex() {
    document.body.classList.add("loading");
    setBanner("");
    try {
        const payload = await fetchJSON("/api/geography/map");
        renderMap(payload);
        if (hasEl("hierarchy-refresh-state")) hierarchyEl["hierarchy-refresh-state"].textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        setBanner(error.message);
        if (hasEl("hierarchy-refresh-state")) hierarchyEl["hierarchy-refresh-state"].textContent = "Map failed";
    } finally {
        document.body.classList.remove("loading");
    }
}

async function loadDetail() {
    document.body.classList.add("loading");
    setBanner("");
    try {
        const page = window.HIERARCHY_PAGE || {};
        const payload = await fetchJSON(`/api/geography/${page.level}/${page.slug}`);
        renderDetail(payload);
        if (hasEl("hierarchy-refresh-state")) hierarchyEl["hierarchy-refresh-state"].textContent = `Loaded ${new Date().toLocaleTimeString()}`;
    } catch (error) {
        setBanner(error.message);
        if (hasEl("hierarchy-refresh-state")) hierarchyEl["hierarchy-refresh-state"].textContent = "Load failed";
    } finally {
        document.body.classList.remove("loading");
    }
}

initHierarchyTheme();
if (hasEl("theme-toggle")) hierarchyEl["theme-toggle"].addEventListener("click", toggleHierarchyTheme);
bindSearch();
if ((window.HIERARCHY_PAGE || {}).mode === "detail") {
    loadDetail();
} else {
    loadIndex();
}
