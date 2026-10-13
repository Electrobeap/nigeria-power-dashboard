# Historical data and geographic access audit

Baseline inspected: main 0133f534. Stage 1 does not restrict these routes.
Public national/regional/state dashboards and existing free history must remain
available. Final products, historical windows and dataset rights need explicit
approval before any guard is attached.

## Route and export inventory

| Surface | Current access/data | Required Stage 2 treatment |
| --- | --- | --- |
| /data, /api/grid/live, /api/latest | Latest measured source payload, daily figures, DisCo/GenCo rows and 24h/7d summaries | Preserve public baseline; review nested summaries before extending |
| /api/grid/gencos, /api/grid/discos, /api/gencos, /api/discos | Live/current entity rows | Public |
| /api/history, /api/generation, /api/analytics | User hours/limit; up to 8760 hours | Authorize proposed extended windows before SQL and cache lookup; retain approved existing free history |
| /api/market-data | Current/daily market signals | Public; do not treat projections as paid verified data |
| /api/discos/<slug>, /api/gencos/<slug> | Up to 720 hours with forecasts/rankings | Audit nested derived series, enforce approved extended products consistently |
| /api/states/<slug>, /api/regions/<slug> | Fast blueprint first, then duplicate legacy rules; up to 720 hours | Preserve public baseline; any future policy must cover both implementations and run before shared cache |
| /api/states, /api/regions, /api/entities | Directories | Public |
| /api/distribution | Up to 168 hours; planning utilization/stress | Preserve public baseline |
| /api/geography/map | State nodes and metrics | Public |
| /api/geography/search | Search results include metrics for lower-level nodes | Potential premium bypass when waiver ends; return public discovery fields only unless authorized |
| /api/geography/<level>/<slug> | Metrics, estimates, forecasts and children with metrics | Waiver applies to all town/city paths; review LGA parent payloads and children/siblings for leakage |
| /state/<slug>, /region/<slug> | Static first HTML with async intelligence | Must remain quick and public; do not add historical/session SQL to initial rendering |
| /geography, /geography/<level>/<slug> | Public map and async hierarchy pages | Shell/search remains public; apply any future advanced-data guard to APIs as well |
| /discos/<slug>, /gencos/<slug> | SEO HTML includes intelligence summary/facts and FAQs | Do not leak a future restricted product through HTML, JSON-LD, or metadata; current free summary remains |
| /, dashboard modal/range buttons | Calls /api/history with selected hours; latest/health/distribution | Button disabling is not authorization |
| dashboard.js exportVisibleCsv | Builds CSV client-side from returned history | Any browser user can reproduce this export. Existing free downloads stay free; future advanced export needs its own guarded server endpoint |
| /articles and /research | Public educational content; approved research HTML/PDF/BibTeX/submission JSON | Remain public; never convert articles into scholarly content or subscription-gate discovery |
| /api/health, /api/metadata | Operational/public endpoint discovery | Preserve existing behavior; no premium data |
| /api/indexnow GET/POST | Existing status/admin-token submission | Preserve its separate authorization; not subscription access |
| /pricing, /api/subscriptions/pricing | Public independent NGN/USD catalog | Display-only, never a billing authorization |
| /account and account forms | Self-only, opt-in, CSRF-protected | Private/no-store; no account ID override |

There are no existing server CSV/XLSX export routes in the audited application.
The only CSV generation found is dashboard.js and its minified counterpart.
Entity, geo and hierarchy clients fetch the listed JSON endpoints. Static
JavaScript, images, article assets and the configurable geography dataset are
not permission boundaries.

## Data hiding is not access control

When a paid product is approved:
1. Normalize and validate hours, limits, hierarchy levels and identifiers once.
   Test duplicate query parameters, aliases, NaN/infinity/negative values,
   encoding/casing, pagination and direct requests independently of the UI.
2. Decide access centrally before database queries and before reading a shared
   analytics cache. Warm caches must not bypass a guard.
3. Guard every alias, API, server export, embedded JSON, SEO fact/FAQ and
   parent/search/sibling response that can expose the same restricted fields.
4. Keep public national/regional/state baseline responses and approved historical
   views unchanged. Do not silently truncate requested premium windows.
5. Return explicit JSON authentication/entitlement errors and an upgrade URL.
   Use private/no-store for personalized responses; never cache an account's
   paid data as public.
6. Keep PRO_PREVIEW_ENABLED=true until waiver removal is explicitly approved.
   When disabled in a future enforcement release, protect eligible town/city
   intelligence without hiding public geographic directories or measured state
   summaries. Retain planning-estimate provenance labels.
7. Test anonymous, Community, active/cancelled-paid-through Pro, expired/pending,
   disabled accounts, verified/unverified emails, both currencies, and preview
   on/off against every data-returning route.

Stage 1 implements and unit-tests the decision contract but does NOT claim this
matrix is enforced. Startup refuses the premature gating flag. No production
access changes occur from creating an account or selecting a display currency.
