from flask import Blueprint, Response, current_app, render_template, send_from_directory


web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    return render_template("index.html")


@web_bp.get("/robots.txt")
def robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {current_app.config['APP_BASE_URL']}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")


@web_bp.get("/sitemap.xml")
def sitemap():
    base_url = current_app.config["APP_BASE_URL"]
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{base_url}/api/metadata</loc>
    <changefreq>daily</changefreq>
    <priority>0.4</priority>
  </url>
<<<<<<< HEAD
=======
  <url>
    <loc>{base_url}/api/distribution</loc>
    <changefreq>hourly</changefreq>
    <priority>0.5</priority>
  </url>
>>>>>>> b9a999e (Disable Scheduler for Render deployment)
</urlset>
"""
    return Response(body, mimetype="application/xml")


@web_bp.get("/favicon.svg")
def favicon():
    return send_from_directory(current_app.static_folder, "favicon.svg", mimetype="image/svg+xml")
