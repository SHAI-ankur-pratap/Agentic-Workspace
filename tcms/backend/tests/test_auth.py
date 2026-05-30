def test_register_first_user_becomes_admin(client):
    resp = client.post("/api/auth/register", json={
        "email": "first@test.com", "password": "pass1234", "full_name": "First"
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


def test_register_second_user_is_qa_lead(client, admin_user):
    resp = client.post("/api/auth/register", json={
        "email": "second@test.com", "password": "pass1234", "full_name": "Second"
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "qa_lead"


def test_login_valid(client, admin_user):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "x"})
    assert resp.status_code == 401


def test_protected_endpoint_no_token(client):
    resp = client.get("/api/projects")
    assert resp.status_code == 401


def test_protected_endpoint_invalid_token(client):
    resp = client.get("/api/projects", headers={"Authorization": "Bearer totally-invalid"})
    assert resp.status_code == 401


def test_api_key_create_and_use(client, admin_user, admin_token):
    # Create API key
    resp = client.post("/api/auth/api-keys",
        json={"name": "CI Key"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    raw_key = resp.json()["raw_key"]
    assert raw_key.startswith("tcms_")

    # Use raw key as Bearer token
    resp2 = client.get("/api/projects", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp2.status_code == 200


def test_api_key_list(client, admin_user, admin_token):
    client.post("/api/auth/api-keys", json={"name": "K1"},
                headers={"Authorization": f"Bearer {admin_token}"})
    resp = client.get("/api/auth/api-keys",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    assert keys[0]["raw_key"] == ""  # never returned after creation


def test_register_invalid_email(client):
    resp = client.post("/api/auth/register", json={
        "email": "not-an-email", "password": "pass1234", "full_name": "Bad"
    })
    assert resp.status_code == 422
