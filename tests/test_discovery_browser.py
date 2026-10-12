"""Desktop/tablet/mobile rendering with controlled third-party resources."""
from threading import Thread

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from grid_monitor.services.articles import ARTICLES


def test_discovery_and_articles_responsive_without_overlap(app, tmp_path):
    app.config["RESEARCH_CONTENT_DIR"] = str(tmp_path)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            def offline_external(route):
                if route.request.url.startswith(base):
                    route.continue_()
                elif route.request.resource_type == "image":
                    # A predictable response tests reserved dimensions without depending on Unsplash uptime.
                    route.fulfill(content_type="image/svg+xml", body='<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>')
                else:
                    route.fulfill(content_type="application/javascript", body="")

            page.route("**/*", offline_external)
            for width, height in ((1440, 1000), (768, 1024), (390, 844), (320, 740)):
                page.set_viewport_size({"width": width, "height": height})
                for path in ("/research", *(article["url"] for article in ARTICLES)):
                    response = page.goto(base + path, wait_until="networkidle")
                    assert response.status == 200
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (path, width)
                    for image in page.locator(".research-guide-image, .article-feature-image").all():
                        box = image.bounding_box()
                        assert box is not None and box["width"] > 0 and box["height"] > 0
                    if path == "/research":
                        cards = page.locator(".research-guide-card")
                        assert cards.count() == 10
                        for card in cards.all():
                            image = card.locator(".research-guide-image").bounding_box()
                            title = card.locator("h3").bounding_box()
                            assert title["y"] >= image["y"] + image["height"], width
                        before = cards.first.bounding_box()
                        page.click("#theme-toggle")
                        after = cards.first.bounding_box()
                        assert before == after
                        page.locator("#research-query").fill("distribution")
                        page.locator(".research-filters button").click()
                        page.wait_for_url("**/research?**")
                        assert page.locator('#energy-guides a[href="/articles/electricity-distribution-in-nigeria"]').count() == 1
                    else:
                        heading = page.locator("#article-title").bounding_box()
                        image = page.locator(".article-feature-image").bounding_box()
                        assert image["y"] >= heading["y"] + heading["height"], (path, width)
            browser.close()
        assert errors == []
    finally:
        server.shutdown()
        worker.join(timeout=5)
