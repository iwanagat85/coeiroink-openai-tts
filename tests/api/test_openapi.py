"""公開するOpenAPIの音声形式・認証・エラー定義を、実際の応答と突き合わせる"""

import pytest

from tests.support import post_speech


@pytest.mark.parametrize("cors_origins", [(), ("http://localhost:3000",)])
def test_openapi_describes_audio_and_bearer_auth(client_factory, cors_origins):
    client = client_factory(cors_origins=cors_origins)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    speech = paths["/v1/audio/speech"]["post"]
    content = speech["responses"]["200"]["content"]
    assert set(content) == {
        "audio/wav",
        "audio/mpeg",
        "audio/ogg",
        "audio/aac",
        "audio/flac",
        "application/octet-stream",
    }
    assert all(
        item["schema"] == {"type": "string", "format": "binary"} for item in content.values()
    )
    assert "422" not in speech["responses"]
    schemes = schema["components"]["securitySchemes"]
    for path, method in (
        ("/v1/models", "get"),
        ("/v1/voices", "get"),
        ("/v1/audio/speech", "post"),
    ):
        operation = paths[path][method]
        assert len(operation["security"]) == 1
        name, scopes = next(iter(operation["security"][0].items()))
        assert schemes[name]["type"] == "http"
        assert schemes[name]["scheme"] == "bearer"
        assert scopes == []
        assert not any(p["name"] == "authorization" for p in operation.get("parameters", []))
        assert "401" in operation["responses"]
    assert not paths["/health"]["get"].get("security")
    assert client.get("/health").status_code == 200


def test_openapi_error_schema_matches_validation_response(client):
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/v1/audio/speech"]["post"]["responses"]
    assert {"400", "401", "500", "502", "503", "504", "default"} <= responses.keys()
    error_ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
    for status in ("401", "500", "502", "503", "504", "default"):
        assert responses[status]["content"]["application/json"]["schema"]["$ref"] == error_ref
    models = schema["components"]["schemas"]
    envelope = models[error_ref.rsplit("/", 1)[1]]
    details_ref = envelope["properties"]["error"]["$ref"]
    details = models[details_ref.rsplit("/", 1)[1]]
    response = post_speech(client, speed=9)
    assert response.status_code == 400
    assert set(envelope["required"]) == set(response.json()) == {"error"}
    assert set(details["required"]) == set(response.json()["error"])
    assert set(details["properties"]) == {"message", "type", "param", "code"}
    assert details["properties"]["type"]["enum"] == ["invalid_request_error", "server_error"]
    for field in ("param", "code"):
        assert {"type": "null"} in details["properties"][field]["anyOf"]
