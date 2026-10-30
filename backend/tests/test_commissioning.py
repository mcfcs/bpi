import json

import httpx

from app.commissioning import NoopAdapter, WebhookAdapter
from tests.conftest import auth

OBJECTIVES = [
    "Understand why SME owners abandon online loan applications",
    "Explore whether SME owners want a named contact person during a loan application",
    "Size the market for crop insurance among rice farmers",
]


def run_check(client, who="ben"):
    response = client.post("/api/commissioning/coverage", headers=auth(client, who),
                           json={"title": "SME digital lending refresh", "objectives": OBJECTIVES})
    assert response.status_code == 200, response.text
    return response.json()


def test_coverage_result_is_structured(client):
    check = run_check(client)
    result = check["result"]
    assert set(result) == {"objectives", "new_problems", "recommended_new_scope"}
    keys = {"text", "coverage", "coverage_label", "new_problem", "newest_fieldwork", "caveats", "finding_ids"}
    assert [set(o) for o in result["objectives"]] == [keys] * 3
    assert [o["coverage"] for o in result["objectives"]] == ["covered", "partial", "gap"]
    assert result["objectives"][2]["finding_ids"] == [] and result["objectives"][2]["new_problem"] is True
    assert result["new_problems"] == [OBJECTIVES[2]]
    assert "crop insurance" in result["recommended_new_scope"]


def test_noop_adapter_stores_and_offers_exports(client, db):
    check = run_check(client)
    headers = auth(client, "ben")
    submitted = client.post(f"/api/commissioning/{check['id']}/submit", headers=headers).json()
    assert submitted["adapter"] == "noop" and submitted["status"] == "stored"
    assert submitted["exports"]["json"].endswith("/export.json")

    exported = client.get(f"/api/commissioning/{check['id']}/export.json", headers=headers)
    assert exported.json()["objectives"] == check["result"]["objectives"]
    pdf = client.get(f"/api/commissioning/{check['id']}/export.pdf", headers=headers)
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")

    # Other users cannot open someone else's check.
    assert client.get(f"/api/commissioning/{check['id']}", headers=auth(client, "carla")).status_code == 404
    with db.as_service() as conn:
        actions = [r["action"] for r in conn.execute(
            "select action from public.audit_log where entity_id = %s order by id", [check["id"]])]
    assert actions == ["commissioning.checked", "commissioning.submitted", "commissioning.exported", "commissioning.exported"]


def test_webhook_adapter_posts_the_structured_result(make_client):
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append((request.headers.get("x-flow-key"), json.loads(request.content)))
        return httpx.Response(202)

    adapter = WebhookAdapter("https://example.invalid/flow", {"x-flow-key": "secret"},
                             client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = make_client(adapter=adapter)
    check = run_check(client)
    submitted = client.post(f"/api/commissioning/{check['id']}/submit", headers=auth(client, "ben")).json()
    assert submitted == {"adapter": "webhook", "status": "sent", "status_code": 202}
    key, payload = received[0]
    assert key == "secret"
    assert payload["check_id"] == check["id"] and payload["result"] == check["result"]


def test_webhook_failures_are_reported_and_audited(make_client, db):
    adapter = WebhookAdapter("https://example.invalid/flow",
                             client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    client = make_client(adapter=adapter)
    check = run_check(client)
    response = client.post(f"/api/commissioning/{check['id']}/submit", headers=auth(client, "ben"))
    assert response.status_code == 502
    with db.as_service() as conn:
        actions = [r["action"] for r in conn.execute(
            "select action from public.audit_log where entity_id = %s order by id", [check["id"]])]
    assert actions == ["commissioning.checked", "commissioning.submit_failed"]


def test_noop_adapter_contract():
    assert NoopAdapter().submit({"id": "abc"}).status == "stored"
