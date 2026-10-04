from app import config
from app.auth import hash_password, verify_credentials, verify_password


def test_correct_credentials_pass(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", hash_password("correct-horse-battery"))
    assert verify_credentials("testadmin", "correct-horse-battery") is True


def test_wrong_password_fails(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", hash_password("correct-horse-battery"))
    assert verify_credentials("testadmin", "wrong-password") is False


def test_wrong_username_fails(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", hash_password("correct-horse-battery"))
    assert verify_credentials("someoneelse", "correct-horse-battery") is False


def test_password_over_72_bytes_does_not_crash(monkeypatch):
    long_password = "x" * 200
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", hash_password(long_password))
    assert verify_credentials("testadmin", long_password) is True


def test_unset_password_hash_fails_closed(monkeypatch):
    # If ADMIN_PASSWORD_HASH was never configured, login must be refused
    # rather than silently accepted.
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin")
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "")
    assert verify_credentials("testadmin", "anything") is False


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_with_bad_credentials_shows_error(client):
    response = client.post("/login", data={"username": "nope", "password": "nope"})
    assert response.status_code == 401
    assert "Invalid username or password" in response.text