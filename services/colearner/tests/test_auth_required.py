"""Auth-boundary tests, following the same pattern as
services/core/tests/test_deps.py: "no header" is tested against the real
dependency chain (UnauthorizedError raises before any Firebase call), and
"invalid token" monkeypatches src.api.deps.verify_token directly rather
than exercising a real Firebase network call.
"""

import pytest
from shared.errors import UnauthorizedError
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize("path", ["/api/v1/colearner/chained", "/api/v1/colearner/multimodal"])
def test_post_requires_authorization_header(client, path):
    response = client.post(path, json={})

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/colearner/chained", "/api/v1/colearner/multimodal"])
def test_post_rejects_invalid_bearer_token(client, path, monkeypatch):
    def fake_verify(token: str):
        raise UnauthorizedError("Invalid or expired authentication token.")

    monkeypatch.setattr("src.api.deps.verify_token", fake_verify)

    response = client.post(path, json={}, headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401


@pytest.mark.parametrize("stream_path", ["/api/v1/colearner/chained/stream", "/api/v1/colearner/multimodal/stream"])
def test_websocket_closes_with_4401_on_invalid_token(client, stream_path, monkeypatch):
    def fake_verify(token: str):
        raise UnauthorizedError("Invalid or expired authentication token.")

    monkeypatch.setattr("src.api.deps.verify_token", fake_verify)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"{stream_path}?token=bad-token") as ws:
            # The server accept()s, then immediately close()s with 4401 -
            # this receive is what surfaces that close frame as a
            # WebSocketDisconnect (a bare `with` block that never reads
            # never observes it).
            ws.receive_text()

    assert exc_info.value.code == 4401
