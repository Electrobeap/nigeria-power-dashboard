from __future__ import annotations

from math import ceil
from typing import Any


ARTICLE_AUTHOR = "Nigeria Power Data Team"
ARTICLE_PUBLISHED_AT = "2026-07-15"
ARTICLE_UPDATED_AT = "2026-07-15"

ARTICLE_CATEGORIES = (
    "Grid Operations",
    "Generation",
    "Distribution",
    "Transmission",
    "Market",
    "Policy",
    "States",
    "Data Analysis",
    "Renewable Energy",
)


def _section(
    section_id: str,
    heading: str,
    paragraphs: list[str],
    table: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": section_id,
        "heading": heading,
        "paragraphs": paragraphs,
    }
    if table:
        payload["table"] = table
    return payload


def _article(
    *,
    slug: str,
    title: str,
    description: str,
    category: str,
    keywords: list[str],
    sections: list[dict[str, Any]],
    faqs: list[dict[str, str]],
    references: list[dict[str, str]],
    featured: bool = False,
    popular_score: int = 50,
) -> dict[str, Any]:
    sections = [*sections, _research_notes_section(title, category)]
    article = {
        "slug": slug,
        "url": f"/articles/{slug}",
        "title": title,
        "description": description,
        "category": category,
        "author": ARTICLE_AUTHOR,
        "published_at": ARTICLE_PUBLISHED_AT,
        "updated_at": ARTICLE_UPDATED_AT,
        "keywords": keywords,
        "sections": sections,
        "faqs": faqs,
        "references": references,
        "featured": featured,
        "popular_score": popular_score,
    }
    article["word_count"] = _word_count(article)
    article["read_minutes"] = max(4, ceil(article["word_count"] / 220))
    article["internal_links"] = _internal_links_for(article)
    article["summary"] = _summary_from(article)
    return article


def _research_notes_section(title: str, category: str) -> dict[str, Any]:
    category_focus = {
        "Grid Operations": "system stability, operating reserves, frequency movement, and short-term restoration patterns",
        "Generation": "plant availability, fuel constraints, moving averages, output concentration, and reserve headroom",
        "Distribution": "allocation pressure, feeder constraints, transformer capacity, settlement growth, and customer reliability",
        "Transmission": "bulk power movement, interface constraints, line or substation outages, and delivery limits",
        "Market": "commercial settlement, regulatory incentives, cost recovery, liquidity, and service accountability",
        "Policy": "implementation timelines, institutional responsibility, investment incentives, and measurable service outcomes",
        "States": "state demand growth, responsible DisCos, population served, transformer stress, and local investment priorities",
        "Data Analysis": "data freshness, trend windows, source limitations, outlier handling, and repeatable interpretation",
        "Renewable Energy": "grid integration, embedded generation, storage, load matching, and local reliability benefits",
    }
    focus = category_focus.get(category, "source freshness, historical trend, operational context, and visible limitations")
    return _section(
        "research-and-planning-notes",
        "Research And Planning Notes",
        [
            f"Use this article as a starting point for structured analysis, not as a standalone conclusion. The strongest reading of {title} comes from comparing the explanation with live dashboard values, stored history, source timestamps, and the methodology notes that describe how Nigeria Power Data calculates trend, ranking, risk, and forecast indicators. In the {category.lower()} context, the most important signals to verify are {focus}.",
            "A practical workflow is to begin with the national dashboard, check whether the current reading is fresh, compare the latest value with the 24-hour and 7-day trend, and then drill into the relevant entity or state page. If the article concerns generation, review GenCo output and volatility. If it concerns distribution, review DisCo allocation and transformer utilization. If it concerns market or policy, pair the visible operating data with official regulatory documents and public source publications.",
            "Readers should also separate measured values from planning estimates. Total generation, published allocation, and timestamps are direct public-data signals when available. Transformer stress, settlement growth, state-level allocation, demand growth, and infrastructure recommendations are analytical estimates designed to support screening, journalism, research, and planning conversations. They are useful because they make pressure points visible, but they should be verified with official feeder, transformer, customer, market, or regulatory datasets before operational, investment, or legal decisions.",
            "For citation and reproducibility, record the page URL, the metric name, the date accessed, the source timestamp, and the comparison window used. This habit makes electricity analysis easier to audit and helps future readers distinguish a temporary operational swing from a persistent structural trend.",
            "When new official datasets become available, compare them against these dashboard interpretations rather than replacing context with a single number. Better evidence should sharpen the analysis, clarify uncertainty, and improve how each grid, market, state, or distribution signal is explained to the public.",
        ],
    )


def _word_count(article: dict[str, Any]) -> int:
    words = [article["title"], article["description"], article["category"]]
    for section in article["sections"]:
        words.append(section["heading"])
        words.extend(section.get("paragraphs", []))
        table = section.get("table") or {}
        words.extend(table.get("headers", []))
        for row in table.get("rows", []):
            words.extend(str(cell) for cell in row)
    for item in article["faqs"]:
        words.extend((item["question"], item["answer"]))
    return len(" ".join(words).split())


def _summary_from(article: dict[str, Any]) -> str:
    first_section = article["sections"][0]
    return first_section["paragraphs"][0]


def _internal_links_for(article: dict[str, Any]) -> list[dict[str, str]]:
    links = [
        {"label": "Live generation dashboard", "url": "/#generation"},
        {"label": "Distribution intelligence", "url": "/#distribution"},
        {"label": "State intelligence", "url": "/states"},
        {"label": "Methodology", "url": "/methodology"},
        {"label": "Data sources", "url": "/data-sources"},
    ]
    if article["category"] == "Generation":
        links.insert(1, {"label": "GenCo intelligence directory", "url": "/gencos"})
    if article["category"] == "Distribution":
        links.insert(1, {"label": "DisCo intelligence directory", "url": "/discos"})
    if article["category"] == "Transmission":
        links.insert(1, {"label": "Geographic power map", "url": "/geography"})
    if article["category"] == "States":
        links.insert(1, {"label": "Browse Nigerian states", "url": "/states"})
    if article["category"] == "Market":
        links.insert(1, {"label": "Market data panel", "url": "/#market-data"})
    return links


COMMON_REFERENCES = [
    {"label": "NIGGRID 24-hour Grid Performance Dashboard", "url": "https://www.niggrid.org/Dashboard"},
    {"label": "Nigerian Electricity Regulatory Commission", "url": "https://nerc.gov.ng/"},
    {"label": "Transmission Company of Nigeria", "url": "https://www.tcn.org.ng/"},
    {"label": "Nigeria Power Data methodology", "url": "/methodology"},
]


ARTICLES = (
    _article(
        slug="understanding-nigerias-national-grid",
        title="Understanding Nigeria's National Grid",
        description="A practical guide to how Nigeria's national grid connects generation, transmission, distribution, and live operating data.",
        category="Grid Operations",
        featured=True,
        popular_score=99,
        keywords=["national grid", "NIGGRID", "TCN", "grid operations", "power system"],
        sections=[
            _section(
                "overview",
                "Overview",
                [
                    "Nigeria's national grid is the synchronized electricity network that connects power stations, high-voltage transmission infrastructure, distribution companies, and end users. It is not a single machine or a single control room. It is a constantly balanced system where electricity generated at the same moment must be transmitted and consumed with tight operating discipline.",
                    "For readers using Nigeria Power Data, the national grid should be understood as an operational chain. GenCos produce electricity, the transmission network moves bulk power across long distances, and DisCos receive allocated supply for distribution to homes, businesses, public institutions, and industrial loads. The dashboard turns public signals from that chain into trend, allocation, reliability, and risk indicators.",
                ],
            ),
            _section(
                "operating-chain",
                "The Operating Chain",
                [
                    "Generation begins at thermal, hydro, and other power plants. The generated electricity is stepped up by transformers so it can travel efficiently over high-voltage lines. Transmission substations then step voltage down for distribution networks, where DisCos deliver supply to feeders, transformers, and customers.",
                    "Because electricity cannot be stored at national scale in the current grid architecture, system operators constantly balance generation and demand. When demand is higher than available generation, load shedding or constrained supply can occur. When generation, demand, frequency, and network limits move outside stable ranges, the system faces operational stress.",
                ],
                {
                    "headers": ["Layer", "Main responsibility", "Example signals"],
                    "rows": [
                        ["Generation", "Produce electrical energy", "Plant output, available capacity, GenCos online"],
                        ["Transmission", "Move bulk power nationally", "Grid frequency, wheeling constraints, system stability"],
                        ["Distribution", "Deliver electricity locally", "DisCo allocation, feeder loading, transformer pressure"],
                        ["Consumers", "Use electricity", "Demand, peak load, settlement growth"],
                    ],
                },
            ),
            _section(
                "why-live-data-matters",
                "Why Live Grid Data Matters",
                [
                    "Live grid data helps convert broad statements about power supply into measurable context. A total generation number shows how much power is available to the grid at a moment in time. DisCo allocation shows how that supply is shared across distribution regions. Historical trends reveal whether the system is improving, weakening, or simply moving within normal daily variation.",
                    "The most useful insight rarely comes from a single number. It comes from comparing current generation with the previous 24 hours, checking moving averages, watching volatility, and seeing whether distribution allocation is concentrated in a few regions. This is why Nigeria Power Data combines live readings with stored history and planning-grade analytics.",
                ],
            ),
            _section(
                "limits",
                "What The Grid Data Does Not Show",
                [
                    "Public grid readings are powerful, but they do not show every feeder, transformer, outage, embedded generator, captive plant, or customer interruption. A state may receive estimated allocation from a DisCo while some communities within that state still experience weak local supply because of feeder faults, transformer overload, vandalism, low voltage, or distribution constraints.",
                    "This distinction matters. National generation can rise while a local network remains constrained. A DisCo allocation can look stable while a specific town faces transformer overload. A data platform should therefore separate national, regional, state, and local indicators rather than treating one number as the whole story.",
                ],
            ),
            _section(
                "how-to-use",
                "How To Use This Dashboard",
                [
                    "Start with current generation and grid status to understand the national operating picture. Then review the generation trend and moving average to see whether supply is rising or falling. Next, check Top GenCos and Top DisCos for concentration and performance. Finally, use the state and distribution modules to connect national power supply to geographic demand and infrastructure pressure.",
                    "For research and public reporting, cite the source date, the dashboard timestamp, and the metric being discussed. For operational or regulatory decisions, always cross-check with official publications and direct system operator information.",
                ],
            ),
        ],
        faqs=[
            {"question": "Who operates Nigeria's national grid?", "answer": "The transmission network and system operations are associated with the Transmission Company of Nigeria and national system operating functions. Nigeria Power Data is an independent public-data dashboard and does not operate the grid."},
            {"question": "Does higher generation always mean better local supply?", "answer": "Not always. Local supply also depends on transmission constraints, DisCo allocation, feeder condition, transformer capacity, outages, and demand pressure."},
            {"question": "How often should grid data be reviewed?", "answer": "For trend monitoring, a 24-hour and 7-day view is more useful than relying on a single snapshot."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="how-electricity-is-generated-in-nigeria",
        title="How Electricity Is Generated in Nigeria",
        description="An accessible explanation of Nigeria's power generation mix, GenCo output, availability, and the difference between installed and delivered capacity.",
        category="Generation",
        popular_score=94,
        keywords=["electricity generation", "GenCos", "thermal power", "hydropower", "capacity"],
        sections=[
            _section(
                "generation-basics",
                "Generation Basics",
                [
                    "Electricity generation in Nigeria is produced mainly by grid-connected thermal and hydro power plants, supported by smaller renewable and embedded resources outside the main public dispatch picture. Thermal plants typically use natural gas to drive turbines, while hydro plants convert water flow into mechanical rotation and electrical output.",
                    "The live generation number on a public dashboard is not the same as the country's theoretical installed capacity. Installed capacity describes what plants could produce under ideal conditions. Available capacity considers whether equipment, fuel, water, transmission access, and operational conditions allow a plant to generate. Delivered grid generation is the actual output sent into the system at a particular time.",
                ],
            ),
            _section(
                "capacity-types",
                "Installed, Available, And Sent-Out Capacity",
                [
                    "A common misunderstanding is to compare installed capacity directly with actual supply and conclude that the missing power is a single failure. In practice, output is reduced by fuel constraints, maintenance, unit outages, water levels, transmission bottlenecks, commercial issues, and system stability limits.",
                    "Nigeria Power Data focuses on operating signals: current generation, plant output where available, moving averages, daily highs and lows, and GenCo rankings. These indicators are useful because they describe what is happening in the grid now, not merely what could be possible in a perfect operating environment.",
                ],
                {
                    "headers": ["Capacity term", "What it means", "Why it matters"],
                    "rows": [
                        ["Installed capacity", "Nameplate technical capacity", "Shows long-term infrastructure base"],
                        ["Available capacity", "Capacity ready to generate", "Reflects fuel, equipment, and network readiness"],
                        ["Sent-out generation", "Power actually delivered", "Best signal for live grid supply"],
                    ],
                },
            ),
            _section(
                "genco-performance",
                "Reading GenCo Performance",
                [
                    "GenCo performance should be read as a time series. A plant that is low today may be on maintenance, constrained by gas, or affected by network limits. A plant that is consistently near the top of the ranking may be more available, better dispatched, or serving an important stability role. Ranking alone does not explain the cause, but it directs attention to the right questions.",
                    "The dashboard's GenCo pages are designed for that purpose. They combine latest output, average output, volatility, short-term forecast, and peer ranking. This allows users to distinguish a short dip from persistent underperformance and to understand which generating units are carrying a large share of grid supply.",
                ],
            ),
            _section(
                "renewables-context",
                "Where Renewable Energy Fits",
                [
                    "Renewable energy is increasingly important in Nigeria's broader power future, especially solar for commercial, residential, mini-grid, and captive use cases. However, much of that capacity may not appear in the main grid generation snapshot if it is behind-the-meter, embedded, or outside national dispatch visibility.",
                    "For a grid intelligence platform, this means renewable data should be handled carefully. Grid-connected renewable output, embedded generation, customer-owned solar, mini-grids, and battery storage are different categories. Future datasets can be added without changing the Articles interface because the content architecture is designed to link back to live datasets and methodology pages.",
                ],
            ),
            _section(
                "practical-reading",
                "Practical Reading Tips",
                [
                    "When reading generation data, look first at total output, then at the 24-hour trend, then at the moving average. If current generation is above the moving average, supply may be strengthening. If it is below the moving average and volatility is high, the system may be under pressure. Next, check whether one or two GenCos are carrying unusually high output concentration.",
                    "For public reporting, avoid saying that a single generation figure represents all electricity consumed in Nigeria. It represents visible grid generation at the time of reporting. Many consumers also depend on embedded supply, captive generation, solar systems, batteries, and backup generators.",
                ],
            ),
        ],
        faqs=[
            {"question": "What is a GenCo?", "answer": "A GenCo is a generation company or generating plant group that produces electricity for the grid or market."},
            {"question": "Why is actual generation lower than installed capacity?", "answer": "Fuel constraints, maintenance, unit outages, transmission constraints, water levels, and commercial conditions can reduce actual output."},
            {"question": "Does Nigeria Power Data forecast generation?", "answer": "It provides short-term statistical trend estimates based on stored readings. These are monitoring estimates, not dispatch schedules."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="understanding-discos-and-gencos",
        title="Understanding DISCOs and GENCOs",
        description="A clear guide to the roles of distribution companies and generation companies in Nigeria's electricity market.",
        category="Market",
        popular_score=91,
        keywords=["DISCOs", "GENCOs", "electricity market", "power sector", "distribution companies"],
        sections=[
            _section(
                "roles",
                "Two Different Roles",
                [
                    "DISCOs and GENCOs are often mentioned together, but they perform different functions in the electricity value chain. GenCos produce power. DisCos distribute power to customers. Between them sits the transmission network, which transports bulk electricity from generating plants to distribution interfaces across the country.",
                    "Understanding the distinction is essential for reading power-sector data. A generation problem may reduce total supply even if a DisCo network is healthy. A distribution problem may affect customer supply even when national generation is stable. A transmission constraint may limit delivery between both ends.",
                ],
            ),
            _section(
                "comparison",
                "DISCOs Versus GENCOs",
                [
                    "A GenCo's operational questions are about plant availability, fuel, dispatch, output, and performance ranking. A DisCo's operational questions are about allocation, network loading, transformer capacity, feeder reliability, collections, and customer demand. The metrics for each entity should therefore be different.",
                    "Nigeria Power Data separates these views. GenCo pages emphasize output trends, volatility, moving averages, forecasts, and rankings. DisCo pages emphasize load allocation, transformer utilization estimates, settlement expansion pressure, capacity margin, and distribution risk classification.",
                ],
                {
                    "headers": ["Entity", "Primary role", "Useful dashboard indicators"],
                    "rows": [
                        ["GenCo", "Generate electricity", "Output, ranking, volatility, forecast"],
                        ["DisCo", "Distribute electricity", "Allocation, transformer loading, settlement growth, risk"],
                        ["TCN", "Transmit bulk power", "Frequency, grid stability, network delivery constraints"],
                    ],
                },
            ),
            _section(
                "allocation",
                "Why Allocation Matters",
                [
                    "DisCo allocation is a bridge between national generation and local supply experience. If total grid generation rises, DisCos may receive higher allocation. But the actual customer experience still depends on feeder condition, local outages, transformer loading, metering, and demand at the time of supply.",
                    "Allocation can also reveal concentration. If a few DisCos receive a large share of available power, load concentration may rise. That can be normal for high-demand regions, but it can also point to stress if settlement growth and transformer loading are rising faster than infrastructure upgrades.",
                ],
            ),
            _section(
                "market-context",
                "Market Context",
                [
                    "The electricity market connects technical operations with commercial settlement. GenCos need payment assurance for energy supplied. DisCos need revenue collection and customer management. Transmission infrastructure needs investment and maintenance. Regulatory rules shape tariffs, service quality, market obligations, and reporting standards.",
                    "A public data platform does not replace official market settlement systems. Its value is interpretation: it helps users see whether generation, distribution allocation, grid health, and demand pressure are moving in a way that deserves attention.",
                ],
            ),
            _section(
                "how-to-read",
                "How To Read Entity Pages",
                [
                    "For a GenCo page, start with latest output and compare it with average output. A large gap suggests unusual movement. Then review volatility and rankings. For a DisCo page, start with current allocation, then check transformer utilization and projected 12-month utilization. If settlement growth is high and capacity margin is low, risk may be rising.",
                    "Entity pages are especially useful when paired with state pages. A state may be served by one or more DisCos, and the state-level view translates franchise-area data into geographic demand and infrastructure stress estimates.",
                ],
            ),
        ],
        faqs=[
            {"question": "Are DISCOs and GENCOs the same?", "answer": "No. GenCos generate electricity. DisCos distribute electricity to customers through local networks."},
            {"question": "Why can a DisCo receive allocation but customers still have outages?", "answer": "Local feeder faults, transformer overload, distribution constraints, scheduled load management, and commercial factors can affect customer supply."},
            {"question": "Can I compare all GenCos directly?", "answer": "You can compare output trends, but plant technology, fuel access, capacity, and dispatch role should be considered."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="what-causes-grid-collapse",
        title="What Causes Grid Collapse?",
        description="A practical explanation of grid collapse, frequency instability, cascading failures, and why power systems need constant balance.",
        category="Grid Operations",
        popular_score=88,
        keywords=["grid collapse", "frequency", "system instability", "outage", "power system"],
        sections=[
            _section(
                "definition",
                "What Grid Collapse Means",
                [
                    "A grid collapse occurs when the synchronized power system can no longer remain stable and large parts of the network shut down automatically or lose supply. It is usually not caused by one simple event. It is often the result of generation loss, transmission faults, frequency deviation, protection trips, and cascading imbalance.",
                    "Modern power systems are protected by relays and control schemes that disconnect equipment when dangerous operating limits are reached. This protects assets and people, but if multiple trips occur quickly, the system can fragment or shut down across wide areas.",
                ],
            ),
            _section(
                "frequency-and-balance",
                "Frequency And Balance",
                [
                    "Power systems require a close match between generation and load. If load rises faster than generation, frequency tends to fall. If generation exceeds load, frequency tends to rise. Operators and generators respond continuously to keep frequency near the target range.",
                    "When frequency moves too far or too quickly, equipment protection may operate. That can remove more generation or load, making the imbalance worse. This is one reason grid collapse risk is connected to both technical faults and the system's ability to absorb shocks.",
                ],
            ),
            _section(
                "common-drivers",
                "Common Drivers Of Collapse Risk",
                [
                    "A large generator trip can remove significant supply. A major transmission line fault can isolate part of the network. Gas constraints can reduce available generation. Poor spinning reserve can leave the system with little room to respond. Protection miscoordination can worsen a disturbance. Extreme demand movement can increase stress.",
                    "Public dashboards usually cannot reveal every cause in real time. They can, however, show warning signals such as sharp generation drops, high volatility, abnormal frequency, falling moving averages, or reduced numbers of reporting GenCos.",
                ],
                {
                    "headers": ["Risk driver", "Operational effect", "Dashboard signal"],
                    "rows": [
                        ["Generation trip", "Sudden supply loss", "Sharp MW decline"],
                        ["Transmission fault", "Network separation or congestion", "Allocation disruption"],
                        ["Frequency excursion", "Protection trips and instability", "Grid frequency outside normal band"],
                        ["Low reserve", "Weak shock absorption", "High volatility and stressed status"],
                    ],
                },
            ),
            _section(
                "outage-detection",
                "Outage Detection In Analytics",
                [
                    "Nigeria Power Data uses stored readings to estimate outage and stress conditions. If generation drops unusually quickly relative to recent history, or if moving averages weaken while volatility increases, the dashboard can classify the operating condition as watch, stressed, or critical depending on thresholds.",
                    "This is not official incident diagnosis. It is a monitoring aid. The correct interpretation is that the system is showing a statistical stress pattern and users should look for official statements, additional readings, and follow-up data.",
                ],
            ),
            _section(
                "resilience",
                "What Improves Resilience",
                [
                    "Grid resilience improves when generation is diversified, reserve margins are adequate, transmission corridors are reinforced, protection systems are coordinated, and distribution networks can manage demand reliably. Better data also helps. Operators, regulators, researchers, and the public make stronger decisions when they can observe trends rather than relying only on isolated incidents.",
                    "For Nigeria, resilience discussions should include both the national grid and local distribution systems. A stable transmission grid is necessary, but transformer loading, feeder reliability, settlement growth, and demand management also shape the electricity experience of households and businesses.",
                ],
            ),
        ],
        faqs=[
            {"question": "Is grid collapse the same as load shedding?", "answer": "No. Load shedding is a controlled reduction in supply. Grid collapse is a wider system stability failure or shutdown."},
            {"question": "Can public data predict collapse?", "answer": "Public data can show stress patterns, but it cannot reliably predict every collapse without full operational telemetry."},
            {"question": "What should I check after a reported collapse?", "answer": "Check official operator updates, current generation, frequency, restoration trend, and DisCo allocation recovery."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="understanding-grid-frequency",
        title="Understanding Grid Frequency",
        description="A plain-language guide to grid frequency, why it matters, and how frequency relates to generation-demand balance.",
        category="Grid Operations",
        popular_score=86,
        keywords=["grid frequency", "50 Hz", "generation demand balance", "system stability"],
        sections=[
            _section(
                "what-frequency-is",
                "What Grid Frequency Is",
                [
                    "Grid frequency is the electrical rhythm of an alternating current power system. In Nigeria, as in many countries, the nominal frequency is 50 hertz. This means the direction of alternating current changes 50 cycles per second under normal operation.",
                    "Frequency is one of the clearest system-stability indicators because it reflects the balance between generation and demand. If demand exceeds generation, frequency tends to fall. If generation exceeds demand, frequency tends to rise. Operators manage this balance continuously.",
                ],
            ),
            _section(
                "why-it-matters",
                "Why Frequency Matters",
                [
                    "Many power system devices are designed to operate within a narrow frequency range. Sustained deviation can damage equipment, trigger protective systems, or force generators to disconnect. Even small changes can be meaningful when they persist or move quickly.",
                    "Frequency is therefore not just a technical detail. It is a live signal of system health. A grid can have a high generation number but still be under stress if frequency is unstable or if reserve capacity is too thin to respond to sudden changes.",
                ],
            ),
            _section(
                "reading-frequency",
                "How To Read Frequency With Other Metrics",
                [
                    "Frequency should be read together with generation, trend, volatility, and grid status. A stable frequency with rising generation suggests improving balance. Falling generation with weakening frequency can indicate stress. High volatility with frequency movement deserves attention because it suggests the system is absorbing disturbances.",
                    "A dashboard can simplify this by converting raw signals into classifications such as healthy, watch, stressed, or critical. The classification is not a replacement for professional system-operation data, but it helps non-specialist readers understand the direction of risk.",
                ],
                {
                    "headers": ["Signal pattern", "Possible interpretation", "What to check next"],
                    "rows": [
                        ["Stable frequency, stable MW", "Balanced operating period", "Moving average"],
                        ["Falling MW, falling frequency", "Supply-demand pressure", "GenCos online and outages"],
                        ["High volatility", "Disturbance or unstable dispatch", "24h trend and official updates"],
                    ],
                },
            ),
            _section(
                "frequency-and-consumers",
                "Does Frequency Explain Local Supply?",
                [
                    "Frequency helps explain national grid stability, but it does not fully explain local power availability. A customer can experience outage because of a local feeder fault even when national frequency is normal. A state can have rising allocation while some settlements remain constrained by transformer capacity.",
                    "This is why Nigeria Power Data pairs frequency and generation metrics with DisCo allocation, transformer loading estimates, state intelligence, and geographic drill-down pages.",
                ],
            ),
            _section(
                "best-practice",
                "Best-Practice Interpretation",
                [
                    "For a quick health check, review frequency first as a stability signal, then generation as a supply signal, then trend and volatility as movement signals. If all four are aligned positively, the grid picture is stronger. If they conflict, read cautiously and look for additional context.",
                    "Always avoid overinterpreting one timestamp. Frequency and generation can change quickly. Historical windows provide better evidence than a single screenshot.",
                ],
            ),
        ],
        faqs=[
            {"question": "What is Nigeria's nominal grid frequency?", "answer": "Nigeria's alternating current grid is nominally operated around 50 Hz."},
            {"question": "Is frequency visible on every public data source?", "answer": "Not always. Availability depends on the public source and how readings are published."},
            {"question": "Why does frequency change?", "answer": "Frequency changes when generation and demand are not perfectly balanced or when the system responds to disturbances."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="nigerias-electricity-market-explained",
        title="Nigeria's Electricity Market Explained",
        description="An overview of Nigeria's electricity market structure, from generation and transmission to distribution, regulation, and settlement.",
        category="Market",
        popular_score=84,
        keywords=["electricity market", "NERC", "settlement", "tariff", "power sector"],
        sections=[
            _section(
                "market-structure",
                "Market Structure",
                [
                    "Nigeria's electricity market connects technical power flows with commercial obligations. Generators produce electricity, the transmission network transports it, distribution companies serve customers, and regulators define rules for tariffs, service quality, market conduct, and reporting.",
                    "A market structure is useful only when energy, money, and information flow reliably. If generation is constrained, supply falls. If collection is weak, market liquidity suffers. If networks are overloaded, customers may not receive power even when the upstream system is producing.",
                ],
            ),
            _section(
                "stakeholders",
                "Major Stakeholders",
                [
                    "The key stakeholders include GenCos, DisCos, the transmission company, regulators, market operators, gas suppliers, large customers, state governments, investors, and consumers. Each group sees the market through a different lens: technical reliability, financial settlement, customer service, regulatory compliance, or investment return.",
                    "Nigeria Power Data is not a settlement platform. It is a public intelligence layer that helps users observe the technical and planning signals that influence market outcomes.",
                ],
                {
                    "headers": ["Stakeholder", "Core concern", "Relevant analytics"],
                    "rows": [
                        ["Regulator", "Rules and service quality", "Reliability trends, allocation patterns"],
                        ["GenCo", "Output and payment assurance", "Generation ranking and volatility"],
                        ["DisCo", "Customer supply and collections", "Allocation, transformer risk, demand growth"],
                        ["Investor", "Risk and growth signals", "State demand and infrastructure stress"],
                    ],
                },
            ),
            _section(
                "settlement",
                "Settlement And Liquidity",
                [
                    "Settlement is the commercial process that determines how energy supplied is paid for. When customers pay bills and DisCos remit market obligations, the chain has better liquidity. When collections are weak or tariffs do not recover costs, the market faces cash pressure that can affect investment and operational reliability.",
                    "Technical dashboards cannot show the full settlement ledger, but they can show demand pressure, allocation trends, supply volatility, and geographic stress. These indicators help researchers and analysts ask better market questions.",
                ],
            ),
            _section(
                "state-market-link",
                "Why States Matter More Now",
                [
                    "State-level electricity planning is becoming more important as policy reforms allow greater subnational participation in electricity markets. That makes geographic intelligence valuable. States need to understand demand growth, distribution constraints, responsible DisCos, transformer pressure, and potential infrastructure gaps.",
                    "The Articles section links market explainers to state intelligence pages so readers can move from policy concepts into data-backed local context.",
                ],
            ),
            _section(
                "how-to-use-data",
                "Using Market Data Responsibly",
                [
                    "Public market analytics should be treated as evidence for questions, not as final legal or financial conclusions. When a trend looks important, users should verify it with official regulatory documents, market reports, company disclosures, and source publications.",
                    "For research, the strongest approach is to combine live data, stored trends, official rules, and local infrastructure information. This produces a clearer picture than any single metric.",
                ],
            ),
        ],
        faqs=[
            {"question": "Is Nigeria Power Data an official market operator?", "answer": "No. It is an independent public-data analytics platform."},
            {"question": "Why does market liquidity matter?", "answer": "Liquidity affects the ability of market participants to maintain assets, buy fuel, invest, and provide reliable service."},
            {"question": "Where should market claims be verified?", "answer": "Use official regulator, market operator, company, and government publications before making commercial or regulatory decisions."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="role-of-tcn-in-power-transmission",
        title="Role of TCN in Power Transmission",
        description="A concise guide to the transmission layer of Nigeria's power system and why bulk power movement shapes reliability.",
        category="Transmission",
        popular_score=80,
        keywords=["TCN", "transmission", "grid", "substations", "bulk power"],
        sections=[
            _section(
                "transmission-role",
                "The Transmission Role",
                [
                    "Transmission is the high-voltage middle layer between generation and distribution. It moves bulk electricity from power plants to load centers through transmission lines, substations, transformers, protection systems, and control infrastructure.",
                    "In Nigeria's electricity chain, the transmission layer is central to national grid stability. Even when generation is available, power must travel through corridors that have technical limits. Congestion, faults, equipment failures, and stability constraints can affect how much power reaches DisCos.",
                ],
            ),
            _section(
                "substations",
                "Substations And Interface Points",
                [
                    "Substations are the physical points where voltage is transformed and power is routed. They connect generating stations, transmission corridors, and distribution networks. A DisCo allocation reading ultimately depends on what can be delivered through these interface points.",
                    "For public dashboards, transmission data is often less granular than generation and distribution allocation data. That means users should interpret transmission stress indirectly through frequency, generation movement, allocation changes, and official operator updates.",
                ],
                {
                    "headers": ["Transmission element", "Function", "Data relevance"],
                    "rows": [
                        ["High-voltage lines", "Move bulk power", "Network delivery capacity"],
                        ["Substations", "Switch and transform voltage", "DisCo interface delivery"],
                        ["Protection systems", "Trip unsafe equipment", "Fault isolation and stability"],
                        ["Control operations", "Balance and dispatch visibility", "Frequency and reliability"],
                    ],
                },
            ),
            _section(
                "bottlenecks",
                "Transmission Bottlenecks",
                [
                    "A transmission bottleneck occurs when power cannot move through part of the network at the level desired. Bottlenecks can be caused by line capacity, transformer limits, outages, voltage constraints, or system stability concerns.",
                    "This is why generation output and customer supply can diverge. More generation at a plant does not automatically guarantee more power in every state if the path to that demand center is constrained.",
                ],
            ),
            _section(
                "dashboard-context",
                "Transmission Context On The Dashboard",
                [
                    "Nigeria Power Data uses transmission-related signals indirectly. Grid frequency, total generation, daily peaks, outage detection, and allocation movement help users understand when the upstream system is healthy or stressed.",
                    "Future official transmission datasets could improve this module with line loading, substation availability, interface constraints, and outage logs. The platform architecture is designed so those datasets can be added as structured data without changing the public article layout.",
                ],
            ),
            _section(
                "reliability",
                "Why Transmission Reliability Matters",
                [
                    "Transmission reliability supports generation dispatch, market settlement, and distribution delivery. When transmission is reliable, the grid can move power from where it is generated to where it is needed. When it is constrained, even available generation may not produce the expected customer benefit.",
                    "A strong transmission network is therefore a national economic asset. It improves energy access, supports industrial demand, and gives distribution systems a more stable supply base.",
                ],
            ),
        ],
        faqs=[
            {"question": "What does TCN do?", "answer": "TCN is associated with Nigeria's transmission network and bulk power movement across the national grid."},
            {"question": "Can transmission constraints reduce supply?", "answer": "Yes. Network constraints can limit how much generated power reaches distribution companies."},
            {"question": "Does Nigeria Power Data show line-level transmission data?", "answer": "Not currently. It uses public national and distribution signals and is prepared for future official datasets."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="electricity-distribution-in-nigeria",
        title="Electricity Distribution in Nigeria",
        description="A distribution planning guide to DisCo allocation, feeder constraints, transformer loading, and settlement growth pressure.",
        category="Distribution",
        popular_score=82,
        keywords=["distribution", "DISCO", "transformer loading", "feeder", "settlement growth"],
        sections=[
            _section(
                "distribution-basics",
                "Distribution Basics",
                [
                    "Electricity distribution is the local delivery layer of the power system. After electricity travels through transmission networks, DisCos deliver supply through lower-voltage networks, feeders, distribution transformers, service lines, meters, and customer interfaces.",
                    "Distribution is where many customers experience the power system most directly. Even when national generation is stable, local outages, overloaded transformers, weak feeders, vandalism, metering gaps, or demand growth can affect service quality.",
                ],
            ),
            _section(
                "allocation-to-service",
                "From Allocation To Customer Service",
                [
                    "A DisCo allocation reading indicates how much bulk power is assigned or delivered to a distribution company at a point in time. It is an upstream distribution signal, not a guarantee that every customer receives supply equally.",
                    "To understand local reliability, allocation should be interpreted with infrastructure stress. A fast-growing settlement may demand more energy than its transformers and feeders can reliably carry. This can produce low voltage, frequent trips, or load management even if the broader DisCo allocation is improving.",
                ],
                {
                    "headers": ["Distribution signal", "Meaning", "Planning question"],
                    "rows": [
                        ["DisCo allocation", "Bulk supply to franchise area", "Is supply rising or falling?"],
                        ["Transformer utilization", "Estimated loading pressure", "Is local equipment near overload?"],
                        ["Settlement growth", "Demand expansion proxy", "Will demand outgrow assets?"],
                        ["Capacity margin", "Headroom before overload", "How urgent are upgrades?"],
                    ],
                },
            ),
            _section(
                "transformer-risk",
                "Transformer Loading And Risk",
                [
                    "Distribution transformers convert electricity to voltage levels customers can use. When transformers operate near or above their planning capacity for too long, the risk of overheating, failure, low-voltage complaints, and outage increases.",
                    "Nigeria Power Data's transformer risk module is a planning-grade estimate. It combines DisCo allocation, settlement growth assumptions, capacity margin, and simulated utilization trends. It does not claim to be direct transformer telemetry, but it helps identify where infrastructure stress may be rising.",
                ],
            ),
            _section(
                "state-views",
                "Why State Views Help",
                [
                    "DisCo franchise areas do not always match how people think about geography. Users often ask about Lagos, Kano, Rivers, Oyo, or the FCT rather than a DisCo acronym. State intelligence bridges that gap by mapping responsible DisCos to state-level demand, population served, estimated allocation, reliability, and transformer stress.",
                    "This is especially useful for planning, journalism, public policy, and investment screening. A state page provides a geographic interpretation of distribution data without requiring readers to know every franchise boundary.",
                ],
            ),
            _section(
                "upgrade-priorities",
                "Upgrade Priorities",
                [
                    "Distribution upgrades may include transformer reinforcement, feeder reconfiguration, capacitor banks, protection coordination, metering improvement, vegetation management, network automation, and targeted embedded generation. The right upgrade depends on the cause of stress.",
                    "A data-driven platform can recommend categories of upgrades by reading utilization, settlement growth, demand pressure, and reliability indicators. Future official feeder and transformer datasets would make these recommendations more precise.",
                ],
            ),
        ],
        faqs=[
            {"question": "Does DisCo allocation equal customer supply?", "answer": "No. Allocation is an upstream signal. Local supply depends on feeders, transformers, outages, demand, and operational decisions."},
            {"question": "What is transformer utilization?", "answer": "It is an estimate of how heavily distribution transformer capacity is being used relative to planning limits."},
            {"question": "Why does settlement growth matter?", "answer": "Growing settlements increase demand and can push transformers and feeders toward overload if infrastructure is not upgraded."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="power-sector-reforms-explained",
        title="Power Sector Reforms Explained",
        description="A neutral guide to Nigerian power-sector reforms, why they matter, and how data can support better electricity decisions.",
        category="Policy",
        popular_score=76,
        keywords=["power sector reform", "policy", "state electricity markets", "regulation", "tariffs"],
        sections=[
            _section(
                "why-reforms-happen",
                "Why Reforms Happen",
                [
                    "Power-sector reforms are attempts to improve electricity reliability, investment, accountability, competition, and service quality. In Nigeria, reform discussions often involve market structure, tariffs, private participation, state-level electricity powers, transmission investment, distribution performance, and consumer protection.",
                    "Reform is not a single event. It is a sequence of legal, regulatory, technical, commercial, and institutional changes. Each change can take years to show results because electricity systems are capital-intensive and operationally complex.",
                ],
            ),
            _section(
                "data-role",
                "The Role Of Data",
                [
                    "Good reform requires good measurement. Without reliable data, it is hard to know whether generation is improving, distribution constraints are worsening, market liquidity is rising, or service quality is changing. Public dashboards make reform debates more concrete by grounding them in visible trends.",
                    "Nigeria Power Data contributes by organizing public grid readings, state intelligence, distribution stress estimates, and entity rankings into searchable pages. This does not replace official audits, but it improves public understanding and research efficiency.",
                ],
                {
                    "headers": ["Reform question", "Useful data signal", "Why it matters"],
                    "rows": [
                        ["Is supply improving?", "Generation trend and moving average", "Tracks delivered grid output"],
                        ["Where is demand pressure rising?", "State demand growth and settlement indicators", "Guides planning and investment"],
                        ["Are local networks stressed?", "Transformer utilization and capacity margin", "Highlights infrastructure risk"],
                        ["Is market performance concentrated?", "GenCo and DisCo rankings", "Shows operating concentration"],
                    ],
                },
            ),
            _section(
                "state-electricity",
                "State Electricity Planning",
                [
                    "A major direction in reform is greater state-level involvement in electricity planning and markets. State governments can play roles in policy, investment attraction, regulatory coordination, embedded generation, mini-grids, and infrastructure prioritization.",
                    "For state-level planning, data must be geographic. It should show responsible DisCos, estimated allocation, demand growth, population served, settlement expansion, transformer risk, and reliability rankings. This is why state pages are part of Nigeria Power Data's SEO and analytics architecture.",
                ],
            ),
            _section(
                "consumer-impact",
                "Consumer Impact",
                [
                    "Consumers judge reform by service quality, price, reliability, safety, and fairness. A technically impressive reform that does not improve the customer's actual supply experience will struggle for public trust. That is why distribution-level indicators are as important as national generation metrics.",
                    "Data can help identify where investment will be felt most. A transformer upgrade in a high-growth area, feeder reinforcement in an overloaded corridor, or better metering in a high-loss region can matter as much as national policy language.",
                ],
            ),
            _section(
                "reading-reform-claims",
                "Reading Reform Claims Responsibly",
                [
                    "Reform claims should be tested against evidence. Look for changes in generation output, outage patterns, distribution allocation, reliability scores, and state-level demand gaps. Also check whether improvements persist across weeks and months rather than appearing only in one day's data.",
                    "Public data is strongest when combined with official policy documents, regulator publications, company data, consumer experience, and independent technical analysis.",
                ],
            ),
        ],
        faqs=[
            {"question": "Can data prove that a reform worked?", "answer": "Data can provide evidence of change, but reform evaluation should combine operational, financial, regulatory, and customer-service indicators."},
            {"question": "Why are state pages important for reform?", "answer": "They connect national electricity issues to local demand, DisCo coverage, infrastructure stress, and planning priorities."},
            {"question": "Is Nigeria Power Data a policy advocacy platform?", "answer": "No. It is a neutral public data and analytics portal."},
        ],
        references=COMMON_REFERENCES,
    ),
    _article(
        slug="reading-nigeria-power-data-dashboard",
        title="Reading Nigeria Power Data Dashboard",
        description="A user guide for reading the Nigeria Power Data dashboard, charts, KPIs, rankings, state pages, and distribution analytics.",
        category="Data Analysis",
        popular_score=96,
        keywords=["dashboard guide", "Nigeria Power Data", "analytics", "KPI", "methodology"],
        sections=[
            _section(
                "start-here",
                "Start With The KPI Cards",
                [
                    "The homepage is designed as a live electricity operations dashboard. The first row gives the national picture: current generation, grid frequency where available, available capacity, energy deficit estimate, GenCos online, DisCo count, and last updated timestamp.",
                    "Read these cards from left to right. Current generation tells you the live supply signal. Frequency tells you stability. Capacity and deficit provide planning context. GenCos and DisCos show reporting coverage. Last updated tells you whether the reading is fresh enough for your use case.",
                ],
            ),
            _section(
                "trend-chart",
                "Use The Generation Trend",
                [
                    "The generation chart is more useful than a single number because it shows movement over time. A rising line can indicate improving supply. A falling line can indicate reduced output or system stress. The moving average smooths short-term noise so the underlying direction is easier to see.",
                    "If the latest value is far from the moving average, ask why. It may be a normal daily swing, a plant outage, a restoration event, or a data gap. Always pair the chart with the last updated timestamp and source status.",
                ],
                {
                    "headers": ["Dashboard element", "Best use", "Caution"],
                    "rows": [
                        ["KPI cards", "Fast status scan", "Do not rely on one card alone"],
                        ["Generation chart", "Trend and moving average", "Check data freshness"],
                        ["Top GenCos", "Output concentration", "Ranking does not explain cause"],
                        ["Distribution panel", "Transformer and settlement stress", "Planning estimate, not telemetry"],
                    ],
                },
            ),
            _section(
                "entity-pages",
                "Read Entity Pages For Detail",
                [
                    "DisCo and GenCo pages turn table rows into drill-down analytics. A DisCo page shows allocation history, transformer loading, settlement growth pressure, capacity margin, and risk classification. A GenCo page shows output history, volatility, forecast, and performance ranking.",
                    "These pages are built for repeated monitoring. They help users track whether an entity's latest reading is unusual compared with its own history and peers.",
                ],
            ),
            _section(
                "state-pages",
                "Use State Pages For Geographic Questions",
                [
                    "Many users think in terms of states, towns, and communities rather than market entities. The state intelligence module translates DisCo coverage into state-level estimates for allocation, peak demand, demand growth, population served, settlement expansion, infrastructure stress, transformer risk, and reliability.",
                    "State pages are especially useful for policy research, local journalism, investment screening, and infrastructure planning. They show how national power data relates to geography.",
                ],
            ),
            _section(
                "methodology-and-limits",
                "Methodology And Limits",
                [
                    "The dashboard combines public source readings, stored history, and planning-grade estimates. Metrics such as transformer utilization and settlement growth are analytical proxies. They are useful for screening and research, but they should not be treated as official feeder telemetry or regulatory determinations.",
                    "For the strongest analysis, use the dashboard with the Methodology and Data Sources pages. Note the timestamp, compare multiple windows, and verify important claims against official sources.",
                ],
            ),
        ],
        faqs=[
            {"question": "Which dashboard number should I read first?", "answer": "Start with current generation and last updated, then review trend, frequency, and distribution indicators."},
            {"question": "Are dashboard forecasts official?", "answer": "No. Forecasts are statistical monitoring estimates based on stored readings."},
            {"question": "Can I cite Nigeria Power Data?", "answer": "Yes, for public research and reporting. Include the page URL, metric name, timestamp, and source context."},
        ],
        references=COMMON_REFERENCES,
    ),
)


ARTICLE_INDEX = {article["slug"]: article for article in ARTICLES}


def article_categories() -> tuple[str, ...]:
    return ARTICLE_CATEGORIES


def list_articles() -> list[dict[str, Any]]:
    return sorted(ARTICLES, key=lambda article: article["published_at"], reverse=True)


def get_article(slug: str) -> dict[str, Any] | None:
    return ARTICLE_INDEX.get(slug)


def featured_article() -> dict[str, Any]:
    return next((article for article in ARTICLES if article.get("featured")), ARTICLES[0])


def latest_articles(limit: int = 6) -> list[dict[str, Any]]:
    return list_articles()[:limit]


def popular_articles(limit: int = 5) -> list[dict[str, Any]]:
    return sorted(ARTICLES, key=lambda article: article["popular_score"], reverse=True)[:limit]


def related_topics() -> list[dict[str, Any]]:
    counts = {category: 0 for category in ARTICLE_CATEGORIES}
    for article in ARTICLES:
        counts[article["category"]] = counts.get(article["category"], 0) + 1
    return [
        {"label": category, "url": f"/articles?category={category.replace(' ', '+')}", "count": counts[category]}
        for category in ARTICLE_CATEGORIES
        if counts.get(category)
    ]


def _search_blob(article: dict[str, Any]) -> str:
    parts = [article["title"], article["description"], article["category"], " ".join(article["keywords"])]
    for section in article["sections"]:
        parts.append(section["heading"])
        parts.extend(section.get("paragraphs", []))
        table = section.get("table") or {}
        parts.extend(table.get("headers", []))
        for row in table.get("rows", []):
            parts.extend(str(cell) for cell in row)
    return " ".join(parts).lower()


def search_articles(
    *,
    query: str = "",
    category: str = "",
    page: int = 1,
    per_page: int = 6,
) -> dict[str, Any]:
    normalized_query = (query or "").strip().lower()
    normalized_category = (category or "").strip()
    page = max(1, int(page or 1))
    results = list_articles()
    if normalized_category:
        results = [
            article
            for article in results
            if article["category"].lower() == normalized_category.lower()
        ]
    if normalized_query:
        terms = [term for term in normalized_query.split() if term]
        results = [
            article
            for article in results
            if all(term in _search_blob(article) for term in terms)
        ]
    total = len(results)
    total_pages = max(1, ceil(total / per_page))
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "articles": results[start:end],
        "query": query,
        "category": normalized_category,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1,
        "next_page": page + 1,
    }


def related_articles(article: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    keywords = set(article.get("keywords") or [])
    candidates: list[tuple[int, dict[str, Any]]] = []
    for candidate in ARTICLES:
        if candidate["slug"] == article["slug"]:
            continue
        score = 0
        if candidate["category"] == article["category"]:
            score += 5
        score += len(keywords.intersection(candidate.get("keywords") or []))
        candidates.append((score, candidate))
    return [
        candidate
        for score, candidate in sorted(candidates, key=lambda item: (item[0], item[1]["popular_score"]), reverse=True)
        if score > 0
    ][:limit] or popular_articles(limit)


def adjacent_articles(slug: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    articles = list_articles()
    for index, article in enumerate(articles):
        if article["slug"] == slug:
            previous_article = articles[index - 1] if index > 0 else None
            next_article = articles[index + 1] if index < len(articles) - 1 else None
            return previous_article, next_article
    return None, None


def related_articles_for_context(context: str, slug: str | None = None, limit: int = 4) -> list[dict[str, Any]]:
    context = (context or "").lower()
    if context in {"state", "region", "geography"}:
        categories = {"States", "Distribution", "Data Analysis"}
    elif context in {"disco", "distribution"}:
        categories = {"Distribution", "Market", "Data Analysis"}
    elif context in {"genco", "generation"}:
        categories = {"Generation", "Grid Operations", "Data Analysis"}
    else:
        categories = {"Grid Operations", "Data Analysis", "Market"}
    ranked = [
        article
        for article in sorted(ARTICLES, key=lambda item: item["popular_score"], reverse=True)
        if article["category"] in categories
    ]
    return ranked[:limit]
