from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import session_local
from app.main import app

client = TestClient(app)


def _reset_users() -> None:
    with session_local() as session:
        # 中文注释：Day 8 后 users 还会被 chat_sessions 关联，先删更深的子表。
        session.execute(text("DELETE FROM chat_sessions"))
        session.execute(text("DELETE FROM interview_sessions"))
        session.execute(text("DELETE FROM applications"))
        session.execute(text("DELETE FROM resumes"))
        session.execute(text("DELETE FROM users"))
        session.commit()


def test_auth_register_login_refresh_flow() -> None:
    _reset_users()
    register_payload = {
        "email": "test@example.com",
        "password": "Test1234!",
        "name": "测试用户",
    }
    register_resp = client.post("/api/v1/auth/register", json=register_payload)
    assert register_resp.status_code == 201
    register_body = register_resp.json()
    assert register_body["code"] == 0
    assert "user_id" in register_body["data"]
    assert "access_token" in register_body["data"]
    assert "refresh_token" in register_body["data"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "Test1234!"},
    )
    assert login_resp.status_code == 200
    login_body = login_resp.json()
    assert login_body["code"] == 0
    assert "access_token" in login_body["data"]
    assert "refresh_token" in login_body["data"]
    assert login_body["data"]["expires_in"] == 900

    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_body["data"]["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    refresh_body = refresh_resp.json()
    assert refresh_body["code"] == 0
    assert "access_token" in refresh_body["data"]
    assert refresh_body["data"]["expires_in"] == 900


def test_register_duplicate_email_returns_409() -> None:
    _reset_users()
    payload = {"email": "dup@example.com", "password": "Test1234!", "name": "用户A"}
    first_resp = client.post("/api/v1/auth/register", json=payload)
    assert first_resp.status_code == 201

    second_resp = client.post("/api/v1/auth/register", json=payload)
    assert second_resp.status_code == 409
    second_body = second_resp.json()
    assert second_body["code"] == 1001


def test_login_wrong_password_returns_401() -> None:
    _reset_users()
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrong@example.com", "password": "Test1234!", "name": "用户B"},
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "WrongPass123!"},
    )
    assert login_resp.status_code == 401
    body = login_resp.json()
    assert body["code"] == 1002


def test_default_admin_account_can_login_with_short_alias() -> None:
    _reset_users()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "password"},
    )

    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["code"] == 0
    assert "access_token" in body["data"]
    assert "refresh_token" in body["data"]

    with session_local() as session:
        admin_email = session.execute(text("SELECT email FROM users WHERE name = 'admin'")).scalar_one()
    assert admin_email == "admin@example.com"


def test_access_token_for_deleted_user_returns_401() -> None:
    _reset_users()
    register_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "deleted@example.com", "password": "Test1234!", "name": "用户C"},
    )
    token = register_resp.json()["data"]["access_token"]

    with session_local() as session:
        session.execute(text("DELETE FROM users WHERE email = 'deleted@example.com'"))
        session.commit()

    health_resp = client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "请给我一点面试建议"},
    )
    assert health_resp.status_code == 401
