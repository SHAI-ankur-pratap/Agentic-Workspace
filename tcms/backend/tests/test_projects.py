def test_create_project(client, admin_token):
    resp = client.post("/api/projects",
        json={"name": "My Project", "client_name": "Client A"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["client_name"] == "Client A"
    assert data["status"] == "active"


def test_list_projects_returns_stats(client, admin_token, project):
    resp = client.get("/api/projects", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    first = items[0]
    assert "total_cases" in first
    assert "coverage_pct" in first
    assert "needs_attention" in first


def test_get_project(client, admin_token, project):
    resp = client.get(f"/api/projects/{project['id']}",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == project["id"]


def test_get_project_not_found(client, admin_token):
    resp = client.get("/api/projects/nonexistent-id",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_update_project(client, admin_token, project):
    resp = client.put(f"/api/projects/{project['id']}",
        json={"name": "Updated Name"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_delete_project(client, admin_token):
    create = client.post("/api/projects",
        json={"name": "To Delete"},
        headers={"Authorization": f"Bearer {admin_token}"})
    pid = create.json()["id"]
    resp = client.delete(f"/api/projects/{pid}",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    # Verify gone
    get_resp = client.get(f"/api/projects/{pid}",
                          headers={"Authorization": f"Bearer {admin_token}"})
    assert get_resp.status_code == 404


def test_component_tag_rule_crud(client, admin_token, project):
    pid = project["id"]
    # Create rule
    resp = client.post(f"/api/projects/{pid}/component-tag-rules",
        json={"file_pattern": "src/auth/**", "component_tag": "auth"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    # List rules
    list_resp = client.get(f"/api/projects/{pid}/component-tag-rules",
                           headers={"Authorization": f"Bearer {admin_token}"})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Delete rule
    del_resp = client.delete(f"/api/projects/{pid}/component-tag-rules/{rule_id}",
                             headers={"Authorization": f"Bearer {admin_token}"})
    assert del_resp.status_code == 200


def test_needs_attention_low_coverage(client, db, admin_token):
    """Project with 0% coverage should be marked needs_attention=True."""
    create = client.post("/api/projects",
        json={"name": "Low Coverage Project"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert create.status_code == 201

    resp = client.get("/api/projects", headers={"Authorization": f"Bearer {admin_token}"})
    projects = resp.json()
    lc = next(p for p in projects if p["project"]["name"] == "Low Coverage Project")
    assert lc["needs_attention"] is True  # Never run = needs attention
