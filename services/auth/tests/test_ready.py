def test_ready_is_not_ready_without_firebase_project(client, monkeypatch):
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_ready_is_ready_when_firebase_project_configured(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-project")

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
