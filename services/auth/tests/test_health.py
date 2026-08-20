def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_echoes_request_id(client):
    response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"


def test_health_generates_request_id_when_absent(client):
    response = client.get("/health")

    assert response.headers["X-Request-ID"]
