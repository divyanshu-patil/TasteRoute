"""F12: sign in keeps a workspace across devices; one click sends a draft from the user's own Gmail."""

import base64
import email
import json
import uuid

import httpx

from tasteroute_api.services import runs as run_service

from ..conftest import make_brand, new_workspace, scout

USERS = {"Bearer token-ana-1": {"id": str(uuid.uuid4()), "email": "ana@brand.test"}}


def supabase(request: httpx.Request) -> httpx.Response:
    assert request.headers["apikey"] == "anon-test"
    user = USERS.get(request.headers["authorization"])
    return httpx.Response(200, json=user) if user else httpx.Response(401, json={"msg": "invalid JWT"})


async def login(client: httpx.AsyncClient, ws: dict[str, str] | None) -> httpx.Response:
    return await client.post("/v1/workspaces/login", json={
        "access_token": "token-ana-1", "workspace_token": ws["X-Workspace-Token"] if ws else None})


async def test_login_keeps_work_and_merges_a_second_device(client, ws, svc, net):
    net["supabase"].side_effect = supabase
    await make_brand(client, ws, svc)
    first = (await login(client, ws)).json()  # this browser's workspace becomes the account's
    assert first["email"] == "ana@brand.test" and first["workspace_token"] == ws["X-Workspace-Token"]

    other = await new_workspace(client)  # another device, used before signing in
    await make_brand(client, other, svc)
    for headers in (ws, other):  # the same do-not-contact entry on both: kept once
        await client.post("/v1/suppressions", headers=headers, json={"kind": "domain", "value": "rival.test"})
    second = (await login(client, other)).json()
    assert second["workspace_token"] == first["workspace_token"]  # the same account workspace
    n = await svc.pool.fetchval("select count(*) from brands where workspace_id = $1", uuid.UUID(first["workspace_id"]))
    assert n == 2  # the second device's brand joined the account
    sup = (await client.get("/v1/suppressions", headers={"X-Workspace-Token": first["workspace_token"]})).json()
    assert [x["value"] for x in sup] == ["rival.test"]
    assert not await svc.pool.fetchval("select count(*) from workspaces where id = $1",
                                       uuid.UUID(other["X-Workspace-Token"].split(".")[0]))
    assert (await login(client, None)).json()["workspace_token"] == first["workspace_token"]  # a fresh browser

    r = await client.post("/v1/workspaces/login", json={"access_token": "token-forged-1"})
    assert r.status_code == 400 and r.json()["code"] == "signin_failed"


async def test_send_from_gmail_once(client, ws, svc, net):
    brand = await make_brand(client, ws, svc)
    run_id = await scout(client, ws, brand)
    venues = (await client.get(f"/v1/runs/{run_id}/venues", headers=ws)).json()["items"]
    await client.post(f"/v1/runs/{run_id}/contacts", headers=ws, json={"venue_ids": [v["venue_id"] for v in venues[:6]]})
    await run_service.drain()
    d0, d1 = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()[:2]
    send = {"google_access_token": "ya29.google-token"}

    r = await client.post(f"/v1/drafts/{d0['id']}/send", headers=ws, json=send)
    assert r.status_code == 403 and r.json()["code"] == "signin_required"  # anonymous workspaces can't send

    net["supabase"].side_effect = supabase
    await login(client, ws)
    sent: list[httpx.Request] = []
    net["gmail"].side_effect = lambda request: sent.append(request) or httpx.Response(200, json={"id": "18c0ffee"})
    r = await client.post(f"/v1/drafts/{d0['id']}/send", headers=ws, json=send)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent" and r.json()["sent_at"]
    assert sent[0].headers["authorization"] == "Bearer ya29.google-token"
    msg = email.message_from_bytes(base64.urlsafe_b64decode(json.loads(sent[0].content)["raw"]))
    assert msg["To"] == d0["contact_email"] and msg["Subject"] == d0["subject"]
    assert d0["body"].strip() in msg.get_payload(decode=True).decode()

    assert (await client.post(f"/v1/drafts/{d0['id']}/send", headers=ws, json=send)).status_code == 409  # never twice
    assert (await client.patch(f"/v1/drafts/{d0['id']}", headers=ws, json={"subject": "x"})).status_code == 409
    assert len(sent) == 1

    net["gmail"].side_effect = lambda request: httpx.Response(401, json={"error": {"code": 401}})
    r = await client.post(f"/v1/drafts/{d1['id']}/send", headers=ws, json=send)
    assert r.status_code == 403 and r.json()["code"] == "gmail_reconnect"
    after = (await client.get(f"/v1/runs/{run_id}/drafts", headers=ws)).json()
    assert next(d for d in after if d["id"] == d1["id"])["sent_at"] is None  # a failed send can be retried

    await client.post("/v1/suppressions", headers=ws, json={"kind": "email", "value": d1["contact_email"]})
    assert (await client.post(f"/v1/drafts/{d1['id']}/send", headers=ws, json=send)).status_code in (404, 409)


async def test_delete_account_removes_work_and_supabase_user(client, ws, svc, net):
    net["supabase"].side_effect = supabase
    await make_brand(client, ws, svc)
    acct = (await login(client, ws)).json()
    uid = uuid.UUID(USERS["Bearer token-ana-1"]["id"])
    await svc.pool.execute("create schema if not exists auth; create table if not exists auth.users (id uuid primary key)")
    try:
        await svc.pool.execute("insert into auth.users (id) values ($1)", uid)  # Supabase's own copy of the account
        r = await client.delete("/v1/workspaces/me", headers=ws)
        assert r.status_code == 204
        wid = uuid.UUID(acct["workspace_id"])
        assert not await svc.pool.fetchval("select count(*) from brands where workspace_id = $1", wid)
        assert not await svc.pool.fetchval("select count(*) from workspaces where id = $1", wid)
        assert not await svc.pool.fetchval("select count(*) from auth.users where id = $1", uid)
        assert (await client.get("/v1/runs", headers=ws)).status_code == 401  # the old token no longer works
    finally:
        await svc.pool.execute("drop schema auth cascade")
