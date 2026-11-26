"""Tests for authentication, JWT security, and user management."""

from tests.conftest import client


class TestAuthRegistration:
    def test_register_user_success(self):
        payload = {
            "username": "joaovictor",
            "email": "joao@example.com",
            "password": "strongPassword123!",
        }
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "joaovictor"
        assert data["email"] == "joao@example.com"
        assert data["is_active"] is True
        assert "password" not in data
        assert "hashed_password" not in data

    def test_register_duplicate_username(self):
        payload = {
            "username": "alice_dev",
            "email": "alice1@example.com",
            "password": "password123",
        }
        client.post("/auth/register", json=payload)

        # Attempt same username with different email
        payload2 = {
            "username": "alice_dev",
            "email": "alice2@example.com",
            "password": "password123",
        }
        resp = client.post("/auth/register", json=payload2)
        assert resp.status_code == 400
        assert "Username already taken" in resp.json()["detail"]

    def test_register_duplicate_email(self):
        payload = {
            "username": "bob1",
            "email": "bob@example.com",
            "password": "password123",
        }
        client.post("/auth/register", json=payload)

        # Attempt different username with same email
        payload2 = {
            "username": "bob2",
            "email": "bob@example.com",
            "password": "password123",
        }
        resp = client.post("/auth/register", json=payload2)
        assert resp.status_code == 400
        assert "Email already registered" in resp.json()["detail"]

    def test_register_invalid_username_characters(self):
        payload = {
            "username": "invalid user!",
            "email": "invalid@example.com",
            "password": "password123",
        }
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 422

    def test_register_short_password(self):
        payload = {
            "username": "charlie",
            "email": "charlie@example.com",
            "password": "123",  # Less than 6 characters
        }
        resp = client.post("/auth/register", json=payload)
        assert resp.status_code == 422


class TestAuthLogin:
    def setup_method(self):
        client.post(
            "/auth/register",
            json={
                "username": "pilot_user",
                "email": "pilot@example.com",
                "password": "PilotSecret2026!",
            },
        )

    def test_login_success_with_username(self):
        resp = client.post(
            "/auth/login",
            json={"username": "pilot_user", "password": "PilotSecret2026!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "pilot_user"

    def test_login_success_with_email(self):
        resp = client.post(
            "/auth/login",
            json={"username": "pilot@example.com", "password": "PilotSecret2026!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "pilot_user"

    def test_login_invalid_password(self):
        resp = client.post(
            "/auth/login",
            json={"username": "pilot_user", "password": "wrongPassword"},
        )
        assert resp.status_code == 401
        assert "Invalid username/email or password" in resp.json()["detail"]

    def test_login_nonexistent_user(self):
        resp = client.post(
            "/auth/login",
            json={"username": "ghost_user", "password": "somePassword"},
        )
        assert resp.status_code == 401

    def test_login_missing_credentials(self):
        resp = client.post("/auth/login", json={})
        assert resp.status_code == 422

    def test_deactivated_user_cannot_login(self):
        from app.models import User
        from tests.conftest import TestingSessionLocal

        # Register user
        client.post(
            "/auth/register",
            json={
                "username": "disabled_user",
                "email": "disabled@example.com",
                "password": "Password123!",
            },
        )
        # Deactivate user in DB
        db = TestingSessionLocal()
        u = db.query(User).filter(User.username == "disabled_user").first()
        u.is_active = False
        db.commit()
        db.close()

        # Attempt login
        resp = client.post(
            "/auth/login",
            json={"username": "disabled_user", "password": "Password123!"},
        )
        assert resp.status_code == 400
        assert "deactivated" in resp.json()["detail"].lower()


class TestAuthProtectedEndpoints:
    def test_get_me_authenticated(self):
        # Register and login
        client.post(
            "/auth/register",
            json={
                "username": "secured_user",
                "email": "secured@example.com",
                "password": "SecuredPass123!",
            },
        )
        login_resp = client.post(
            "/auth/login",
            json={"username": "secured_user", "password": "SecuredPass123!"},
        )
        token = login_resp.json()["access_token"]

        # Access /auth/me
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "secured_user"
        assert data["email"] == "secured@example.com"

    def test_get_me_unauthorized_no_token(self):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_get_me_invalid_token(self):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.fake.token"})
        assert resp.status_code == 401

    def test_create_project_with_auth_sets_owner(self):
        # Register user
        client.post(
            "/auth/register",
            json={
                "username": "project_owner",
                "email": "owner@example.com",
                "password": "OwnerPass123!",
            },
        )
        login_resp = client.post(
            "/auth/login",
            json={"username": "project_owner", "password": "OwnerPass123!"},
        )
        token = login_resp.json()["access_token"]
        user_id = login_resp.json()["user"]["id"]

        # Create project with auth header
        resp = client.post(
            "/projects",
            json={"name": "Owned Project", "description": "Has owner"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Owned Project"
        assert data["owner_id"] == user_id
