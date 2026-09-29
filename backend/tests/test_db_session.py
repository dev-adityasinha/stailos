"""The request session must commit before the response goes out.

With FastAPI's default request scope for yield dependencies, get_db() committed
only after the response was sent: a client could read stale data straight
after a successful write, and a failing commit still reached it as a success.
"""
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.main import app
from tests.test_leads import make_lead


def test_every_route_uses_the_function_scoped_session():
    def unscoped(dependant, path):
        for dep in dependant.dependencies:
            if dep.call is get_db and dep.scope != "function":
                yield path
            yield from unscoped(dep, path)

    offenders = sorted({
        p for route in app.routes if isinstance(route, APIRoute)
        for p in unscoped(route.dependant, f"{sorted(route.methods)} {route.path}")
    })
    assert offenders == [], 'use Depends(get_db, scope="function") in: ' + ", ".join(offenders)


def test_failed_commit_is_reported_not_acknowledged(client, admin, monkeypatch):
    def failing_commit(self):
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(Session, "commit", failing_commit)
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = make_lead(c, admin)
    assert resp.status_code == 500, resp.text

    monkeypatch.undo()
    assert client.get("/api/v1/leads", headers=admin).json()["data"] == []


def test_write_is_visible_to_the_very_next_request(client, admin):
    lead = make_lead(client, admin).json()["data"]
    for stage in ["contacted", "qualified", "interested", "negotiation"]:
        resp = client.patch(
            f"/api/v1/pipeline/leads/{lead['id']}/stage", headers=admin, json={"stage": stage}
        )
        assert resp.status_code == 200, resp.text
        assert client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]["stage"] == stage
