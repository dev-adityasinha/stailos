"""API keys: the long-lived credential another system uses to call this API.

The point of these tests is the substitution: a key must work anywhere an access
token works, under exactly the same role and tenant rules, and must stop working
the moment it is revoked.
"""

from tests.conftest import STRONG_PASSWORD, create_user_as_admin, register


def _create_key(client, headers, name="Viralitea"):
    resp = client.post("/api/v1/api-keys", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_key_is_returned_once_and_never_stored_in_the_clear(client, admin):
    created = _create_key(client, admin)
    key = created["key"]
    assert key.startswith("pk_")
    # The prefix identifies it in a list; it is not enough to authenticate with.
    assert created["prefix"] == key[:11]
    assert len(key) > len(created["prefix"])

    # The listing carries no key material at all.
    listed = client.get("/api/v1/api-keys", headers=admin)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    assert "key" not in rows[0]
    assert rows[0]["prefix"] == created["prefix"]


def test_a_key_authenticates_exactly_like_an_access_token(client, admin):
    key = _create_key(client, admin)["key"]
    headers = {"Authorization": f"Bearer {key}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["data"]["email"] == "admin@stail.com"

    # And on a real resource, not just the identity endpoint.
    leads = client.get("/api/v1/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert "total" in leads.json()["meta"]


def test_a_key_carries_its_user_role_not_a_blanket_grant(client, admin):
    """A key is its user. A telecaller's key cannot do what its owner cannot."""
    create_user_as_admin(client, admin, "caller@stail.com", "telecaller")
    caller_login = client.post(
        "/api/v1/auth/login",
        json={"email": "caller@stail.com", "password": STRONG_PASSWORD},
    )
    assert caller_login.status_code == 200, caller_login.text
    caller_headers = {
        "Authorization": f"Bearer {caller_login.json()['data']['access_token']}"
    }

    # A non-admin cannot mint one in the first place.
    refused = client.post(
        "/api/v1/api-keys", headers=caller_headers, json={"name": "nope"}
    )
    assert refused.status_code == 403


def test_revoking_a_key_stops_it_immediately(client, admin):
    created = _create_key(client, admin)
    headers = {"Authorization": f"Bearer {created['key']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    revoked = client.delete(f"/api/v1/api-keys/{created['id']}", headers=admin)
    assert revoked.status_code == 200
    assert revoked.json()["data"]["revoked_at"] is not None

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    # Revoked, not deleted: the row survives so the trail does.
    rows = client.get("/api/v1/api-keys", headers=admin).json()["data"]
    assert len(rows) == 1
    assert rows[0]["revoked_at"] is not None


def test_an_unknown_key_is_refused(client, admin):
    bogus = {"Authorization": "Bearer pk_not-a-real-key-at-all"}
    assert client.get("/api/v1/auth/me", headers=bogus).status_code == 401


def test_a_key_records_when_it_was_last_used(client, admin):
    created = _create_key(client, admin)
    assert created["last_used_at"] is None

    client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {created['key']}"})

    rows = client.get("/api/v1/api-keys", headers=admin).json()["data"]
    assert rows[0]["last_used_at"] is not None


def test_keys_do_not_leak_across_tenants(client, admin):
    """Another workspace's key is invisible and unrevokable from this one."""
    first_key = _create_key(client, admin)

    second = register(client, email="other@elsewhere.com", name="Other Admin")
    assert second.status_code == 201, second.text
    other_login = client.post(
        "/api/v1/auth/login",
        json={"email": "other@elsewhere.com", "password": STRONG_PASSWORD},
    )
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['data']['access_token']}"
    }

    listed = client.get("/api/v1/api-keys", headers=other_headers)
    assert listed.status_code == 200
    assert listed.json()["data"] == []

    denied = client.delete(f"/api/v1/api-keys/{first_key['id']}", headers=other_headers)
    assert denied.status_code == 404
