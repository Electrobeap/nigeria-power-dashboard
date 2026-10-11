import pytest

from grid_monitor.services.cache import clear_cache
from grid_monitor.services.state_intelligence import list_regions, list_states


@pytest.fixture(autouse=True)
def _clear_analytics_cache():
    clear_cache()
    yield
    clear_cache()


def test_fast_geography_routes_are_registered_before_legacy_routes(app):
    expected_first_routes = {
        "/state/<slug>": "geo_fast.fast_state_page",
        "/region/<slug>": "geo_fast.fast_region_page",
        "/api/states/<slug>": "geo_fast.fast_state_detail",
        "/api/regions/<slug>": "geo_fast.fast_region_detail",
    }

    for rule_path, endpoint in expected_first_routes.items():
        matching = [rule for rule in app.url_map.iter_rules() if rule.rule == rule_path and "GET" in rule.methods]
        assert matching, rule_path
        assert matching[0].endpoint == endpoint


def test_all_state_and_region_pages_render_without_history_calculations(client, monkeypatch):
    def fail_if_legacy_history_loader_runs(*args, **kwargs):
        raise AssertionError("Geography HTML pages must render from static context first")

    monkeypatch.setattr("grid_monitor.routes.web.state_intelligence", fail_if_legacy_history_loader_runs)
    monkeypatch.setattr("grid_monitor.routes.web.region_intelligence", fail_if_legacy_history_loader_runs)

    paths = [state["url"] for state in list_states()] + [region["url"] for region in list_regions()]
    assert len(paths) == 43

    for path in paths:
        response = client.get(path)
        body = response.get_data(as_text=True)
        assert response.status_code == 200, path
        assert "Historical Allocation Trend" in body
        assert "Loading geography" in body
        assert "geo.min.js?v=geo-fast-20261012" in body


def test_representative_geography_apis_return_timed_payloads(client):
    for path in ("/api/states/lagos", "/api/states/edo", "/api/regions/north-central"):
        response = client.get(f"{path}?hours=168&limit=336")
        payload = response.get_json()
        assert response.status_code == 200, path
        assert payload["entity"]["slug"]
        assert payload["data_status"]["source"] == "stored_disco_allocation_history"
        assert "response_timestamp" in payload
        assert payload["performance"]["elapsed_ms"] >= 0
        assert isinstance(payload["history"], list)


def test_geography_api_returns_static_fallback_when_history_loader_fails(client, monkeypatch):
    def fail_history_loader(*args, **kwargs):
        raise RuntimeError("simulated historical query timeout")

    monkeypatch.setattr("grid_monitor.routes.geography.state_intelligence", fail_history_loader)

    response = client.get("/api/states/lagos?hours=168&limit=336")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["entity"]["slug"] == "lagos"
    assert payload["data_status"]["ok"] is False
    assert payload["data_status"]["source"] == "static_geography_profile"
    assert payload["data_status"]["error_type"] == "RuntimeError"
    assert payload["history"] == []
    assert payload["performance"]["elapsed_ms"] >= 0


def test_unknown_state_and_region_routes_return_404(client):
    for path in ("/state/not-a-state", "/region/not-a-region", "/api/states/not-a-state", "/api/regions/not-a-region"):
        response = client.get(path)
        assert response.status_code == 404, path
