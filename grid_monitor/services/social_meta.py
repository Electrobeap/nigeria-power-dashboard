from __future__ import annotations

from typing import Any

from flask import current_app


SITE_NAME = "Nigeria Power Data"


def _absolute_url(path: str) -> str:
    base_url = current_app.config["APP_BASE_URL"].rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url}{normalized_path}"


def _title_with_site(title: str) -> str:
    if SITE_NAME.lower() in title.lower():
        return title
    return f"{title} | {SITE_NAME}"


def build_social_meta(
    *,
    title: str,
    description: str,
    path: str,
    image_path: str | None = None,
    image_alt: str | None = None,
    og_type: str = "website",
    published_time: str | None = None,
    modified_time: str | None = None,
) -> dict[str, Any]:
    title = _title_with_site(title)
    url = _absolute_url(path)
    image = _absolute_url(image_path or current_app.config["SOCIAL_DEFAULT_IMAGE"])
    return {
        "title": title,
        "description": description,
        "url": url,
        "image": image,
        "image_alt": image_alt or f"{SITE_NAME} social preview",
        "site_name": SITE_NAME,
        "locale": "en_NG",
        "og_type": og_type,
        "image_width": current_app.config["SOCIAL_IMAGE_WIDTH"],
        "image_height": current_app.config["SOCIAL_IMAGE_HEIGHT"],
        "image_type": "image/png",
        "twitter_card": current_app.config["TWITTER_CARD"],
        "twitter_site": current_app.config.get("TWITTER_SITE"),
        "published_time": published_time or current_app.config["SCHEMA_DATE_PUBLISHED"]
        if og_type == "article"
        else None,
        "modified_time": modified_time or current_app.config["SCHEMA_DATE_MODIFIED"]
        if og_type == "article"
        else None,
    }
