async def _fake_connection_ok() -> bool:
    return True


async def _fake_connection_down() -> bool:
    return False


def test_ready_reports_unavailable_when_database_unreachable(client, monkeypatch):
    monkeypatch.setattr("src.api.routes.ready.check_connection", _fake_connection_down)

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"][0]["ok"] is False


def test_ready_reports_ok_when_database_reachable(client, monkeypatch):
    monkeypatch.setattr("src.api.routes.ready.check_connection", _fake_connection_ok)

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"][0]["ok"] is True
