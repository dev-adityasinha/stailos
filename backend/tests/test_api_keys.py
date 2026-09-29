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


# ---------------------------------------------------------------------------
# Escalation: a key must not be tradeable for something that outlives it
# ---------------------------------------------------------------------------


def test_a_key_cannot_be_exchanged_for_a_session(client, admin):
    """The hole this closes: /auth/exchange/issue authenticates with
    get_current_user, which accepts API keys. A key holder could take a code,
    redeem it on the unauthenticated endpoint for a JWT and a 7-day rotating
    refresh family, and keep that session alive after the key was revoked."""
    key = _create_key(client, admin)["key"]
    headers = {"Authorization": f"Bearer {key}"}

    refused = client.post("/api/v1/auth/exchange/issue", headers=headers)
    assert refused.status_code == 403, refused.text

    # The same endpoint still works for a real signed-in session.
    allowed = client.post("/api/v1/auth/exchange/issue", headers=admin)
    assert allowed.status_code == 200, allowed.text


def test_a_key_cannot_mint_more_keys(client, admin):
    """Otherwise revoking a leaked key closes nothing: it made successors."""
    key = _create_key(client, admin)["key"]
    headers = {"Authorization": f"Bearer {key}"}

    assert client.post("/api/v1/api-keys", headers=headers, json={"name": "child"}).status_code == 403
    assert client.get("/api/v1/api-keys", headers=headers).status_code == 403

    listed = client.get("/api/v1/api-keys", headers=admin).json()["data"]
    assert len(listed) == 1


def test_a_key_cannot_create_or_re_role_users(client, admin):
    """A key is necessarily an admin key, so without this it could leave behind
    an account with a chosen password that revocation does not touch."""
    key = _create_key(client, admin)["key"]
    headers = {"Authorization": f"Bearer {key}"}

    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "backdoor@stail.com",
            "password": STRONG_PASSWORD,
            "full_name": "Backdoor",
            "role": "super_admin",
        },
    )
    assert created.status_code == 403, created.text

    # And no account was left behind.
    users = client.get("/api/v1/users", headers=admin).json()["data"]
    assert not any(u["email"] == "backdoor@stail.com" for u in users)


def test_a_key_still_does_the_work_it_exists_for(client, admin):
    """The gate is on identity, not on data. Leads must still work."""
    key = _create_key(client, admin)["key"]
    headers = {"Authorization": f"Bearer {key}"}

    created = client.post(
        "/api/v1/leads",
        headers=headers,
        json={"full_name": "Aditi Rao", "phone": "+919876500011", "source": "viralitea"},
    )
    assert created.status_code == 201, created.text
    assert client.get("/api/v1/leads", headers=headers).status_code == 200


def test_the_creation_audit_row_names_the_key(client, admin):
    """Without a flush the id is None, so a revocation names an id that no
    creation event matches."""
    created = _create_key(client, admin)
    audit = client.get("/api/v1/audit", headers=admin)
    assert audit.status_code == 200, audit.text
    rows = [r for r in audit.json()["data"] if r["action"] == "auth.api_key_created"]
    assert rows, "no creation audit row"
    assert rows[0]["entity_id"] == created["id"]
