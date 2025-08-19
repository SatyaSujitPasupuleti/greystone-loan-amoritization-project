from fastapi.testclient import TestClient


def test_create_and_list_users(client: TestClient):
    # Create users
    r1 = client.post("/users", json={"username": "alice", "email": "alice@example.com"})
    assert r1.status_code == 201, r1.text
    r2 = client.post("/users", json={"username": "bob", "email": "bob@example.com"})
    assert r2.status_code == 201, r2.text

    # Duplicate username/email rejected
    r_dup_user = client.post("/users", json={"username": "alice", "email": "alice2@example.com"})
    assert r_dup_user.status_code == 400
    r_dup_email = client.post("/users", json={"username": "bob2", "email": "bob@example.com"})
    assert r_dup_email.status_code == 400

    # List users
    r_list = client.get("/users")
    assert r_list.status_code == 200
    users = r_list.json()
    assert len(users) == 2
    names = {u["username"] for u in users}
    assert names == {"alice", "bob"}
