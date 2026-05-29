import io


def test_create_test_case(client, admin_token, project):
    resp = client.post(f"/api/projects/{project['id']}/testcases",
        json={"title": "TC one", "steps": "1. Do thing", "expected_result": "Thing done", "priority": "P2"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["tc_id"] == "TC-001"
    assert data["title"] == "TC one"


def test_tc_id_sequence_within_project(client, admin_token, project):
    pid = project["id"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = {"steps": "1. step", "expected_result": "result"}
    r1 = client.post(f"/api/projects/{pid}/testcases",
        json={"title": "First", **base}, headers=headers)
    r2 = client.post(f"/api/projects/{pid}/testcases",
        json={"title": "Second", **base}, headers=headers)
    assert r1.json()["tc_id"] == "TC-001"
    assert r2.json()["tc_id"] == "TC-002"


def test_tc_id_scoped_per_project(client, admin_token, db):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = {"steps": "1. step", "expected_result": "result"}

    p1 = client.post("/api/projects", json={"name": "Proj A"}, headers=headers).json()
    p2 = client.post("/api/projects", json={"name": "Proj B"}, headers=headers).json()

    r1 = client.post(f"/api/projects/{p1['id']}/testcases",
                     json={"title": "P1 TC", **base}, headers=headers)
    r2 = client.post(f"/api/projects/{p2['id']}/testcases",
                     json={"title": "P2 TC", **base}, headers=headers)

    assert r1.json()["tc_id"] == "TC-001"
    assert r2.json()["tc_id"] == "TC-001"  # Scoped — starts fresh for new project


def test_get_test_case_by_tc_id(client, admin_token, project, test_case):
    resp = client.get(f"/api/projects/{project['id']}/testcases/{test_case['tc_id']}",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == test_case["id"]


def test_update_test_case(client, admin_token, project, test_case):
    resp = client.put(f"/api/projects/{project['id']}/testcases/{test_case['tc_id']}",
        json={"title": "Updated Title", "priority": "P1"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


def test_delete_test_case(client, admin_token, project):
    headers = {"Authorization": f"Bearer {admin_token}"}
    tc = client.post(f"/api/projects/{project['id']}/testcases",
        json={"title": "To delete", "steps": "1. step", "expected_result": "done"},
        headers=headers).json()
    del_resp = client.delete(f"/api/projects/{project['id']}/testcases/{tc['tc_id']}",
                             headers=headers)
    assert del_resp.status_code == 200
    get_resp = client.get(f"/api/projects/{project['id']}/testcases/{tc['tc_id']}",
                          headers=headers)
    assert get_resp.status_code == 404


def test_csv_import_happy_path(client, admin_token, project):
    csv_content = b"title,steps,expected_result,priority\n" \
                  b"Login test,1. Go to login,Logged in,P1\n" \
                  b"Logout test,1. Click logout,Logged out,P2\n"
    resp = client.post(f"/api/projects/{project['id']}/testcases/import-csv",
        files={"file": ("cases.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["imported"] == 2
    assert resp.json()["errors"] == []


def test_csv_import_missing_title_column(client, admin_token, project):
    csv_content = b"name,steps\nLogin,1. step\n"
    resp = client.post(f"/api/projects/{project['id']}/testcases/import-csv",
        files={"file": ("bad.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 422


def test_csv_import_empty_file(client, admin_token, project):
    resp = client.post(f"/api/projects/{project['id']}/testcases/import-csv",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 422


def test_template_import(client, admin_token, project, react_template):
    resp = client.post(f"/api/projects/{project['id']}/testcases/import-template",
        json={"template_type": "react-crud"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["imported"] == 5  # fixture has 5 cases
