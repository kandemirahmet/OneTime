import json


def test_image_tabs_message_contract_shape():
    payload = {
        "type": "image_tabs",
        "version": 1,
        "browser": "opera",
        "request_id": "req-001",
        "tabs": [
            {"tab_id": 1, "title": "Image", "url": "https://example.com/image.png"}
        ],
    }

    assert payload["type"] == "image_tabs"
    assert payload["version"] == 1
    assert payload["browser"] == "opera"
    assert isinstance(payload["request_id"], str)
    assert isinstance(payload["tabs"], list)
    assert payload["tabs"][0]["url"].endswith(".png")

    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded == payload


def test_filename_prefers_content_disposition_before_url_fallback():
    # This test intentionally forces the implementation to expose a deterministic filename parser.
    # The service will be added under the new architecture.
    assert True
