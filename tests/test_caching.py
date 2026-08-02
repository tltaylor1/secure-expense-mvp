"""Served pages must demand revalidation, so a deploy is visible on next load."""


def test_page_and_statics_send_no_cache(client):
    for path in ("/", "/static/app.js", "/static/style.css"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers.get("cache-control") == "no-cache", path


def test_api_responses_are_not_marked_cacheable(client):
    # The middleware scopes to the frontend paths; API responses carry no
    # cache directive at all rather than a misleading one.
    r = client.get("/health")
    assert "cache-control" not in r.headers
