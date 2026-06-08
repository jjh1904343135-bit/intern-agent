from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app

client = TestClient(app)


def _register_user_headers() -> dict[str, str]:
    email = f"telegram-{uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test1234!", "name": "Telegram User"},
    )
    assert response.status_code == 201
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_telegram_bind_code_requires_authentication() -> None:
    response = client.post("/api/v1/telegram/bind-code")

    assert response.status_code == 401


def test_get_telegram_status_returns_bound_account_for_current_user() -> None:
    headers = _register_user_headers()
    chat_id = str(int(uuid4().int % 900000000 + 100000000))
    # Decode-free lookup keeps the test focused on the Telegram endpoint behavior.
    with session_local() as session:
        user_id = session.execute(text("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")).scalar_one()
        session.execute(
            text(
                """
                INSERT INTO telegram_accounts (user_id, chat_id, username, first_name, enabled, last_seen_at)
                VALUES (:user_id, :chat_id, 'qingcheng_user', 'Qingcheng', true, now())
                """
            ),
            {"user_id": user_id, "chat_id": chat_id},
        )
        session.commit()

    response = client.get("/api/v1/telegram/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["bound"] is True
    assert body["data"]["enabled"] is True
    assert body["data"]["username"] == "qingcheng_user"
    assert body["data"]["chat_id_masked"] == f"{chat_id[:3]}***{chat_id[-2:]}"


def test_create_telegram_bind_code_returns_one_time_command_without_plaintext_storage() -> None:
    headers = _register_user_headers()

    response = client.post("/api/v1/telegram/bind-code", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert len(data["code"]) == 8
    assert data["command"] == f"/bind {data['code']}"
    assert data["expires_at"]

    with session_local() as session:
        row = session.execute(
            text(
                """
                SELECT code_hash, used_at
                FROM telegram_bind_codes
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).mappings().one()

    assert row["used_at"] is None
    assert row["code_hash"] != data["code"]
