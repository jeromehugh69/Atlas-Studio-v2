import pytest

from atlas_studio.site_policy import validate_site_url


def test_site_inspection_allows_only_the_internal_atlas_origin():
    origins = {"http://app:8080"}
    assert validate_site_url("http://app:8080/static/index.html", origins) == "http://app:8080/static/index.html"
    with pytest.raises(ValueError):
        validate_site_url("https://example.com/", origins)


def test_site_inspection_rejects_credentials():
    with pytest.raises(ValueError):
        validate_site_url("http://user:secret@app:8080/", {"http://app:8080"})
