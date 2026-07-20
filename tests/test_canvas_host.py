"""The canvas host: the extension proxy seam, in production.

WHY THE SHARED CASE FILE
------------------------
`extensions/<name>/ui/canvas/canvas_proxy.json` is read TWICE — by vite.config.ts in dev, and
by core/engine/api/canvas_host.py in production. One manifest, two servers, two languages.

Two implementations of a FAIL-CLOSED merge is precisely the bug that ships. Dev refuses a
collision; prod silently allows it; one extension's traffic is routed into another extension's
data plane; both services answer 200; the numbers are simply someone else's, and nothing
anywhere says so.

So the rules live in core/ui/canvas_proxy_cases.json as DATA, and both implementations are
tested against that file. Change the behaviour in one language and the other language's test
goes red. The TypeScript half is devProxySeam.test.ts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.engine.api.canvas_host import (
    ProxyCollisionError,
    create_app,
    discover_extension_proxies,
    merge_extension_proxies,
)

REPO = Path(__file__).resolve().parents[1]
CASES = json.loads((REPO / "core" / "ui" / "canvas_proxy_cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_the_merge_obeys_the_shared_rules(case):
    """The SAME cases the TypeScript seam is tested against. If these two ever disagree, one of
    the two servers is routing traffic the other would have refused."""
    kernel = tuple(case["kernel"])
    declared = case["declared"]
    env = case["env"]

    if "error" in case["expect"]:
        with pytest.raises(ProxyCollisionError):
            merge_extension_proxies(kernel, declared, env)
        return

    assert merge_extension_proxies(kernel, declared, env) == case["expect"]["merged"]


class TestDiscovery:
    def test_it_finds_every_extension_manifest_without_naming_one(self, tmp_path):
        """The host globs extensions/*/ui/canvas/canvas_proxy.json. It never learns what any of
        it is for — the same rule that keeps the kernel from naming an extension.

        Hermetic ON PURPOSE. This test used to scan the REAL extensions/ dir and assert a
        private extension's prefixes were present — so the kernel's own test suite
        could only pass on a machine that had a private extension installed, and it failed in
        the public export tree, where `reference` is the only extension that ships. A kernel
        test that requires a specific extension to exist is exactly the coupling the module
        docstring forbids. Two synthetic extensions prove the real contract — discovery is a
        GLOB over whatever happens to be there — without depending on any of them. Each
        extension's own manifest regression guard lives with that extension, in its own repo.
        """
        for name, prefix in (("alpha", "/api/one"), ("beta", "/api/two")):
            d = tmp_path / name / "ui" / "canvas"
            d.mkdir(parents=True)
            (d / "canvas_proxy.json").write_text(json.dumps({prefix: {"target": "http://127.0.0.1:9000"}}))

        found = discover_extension_proxies(tmp_path)

        assert {d["prefix"] for d in found} == {"/api/one", "/api/two"}
        # Stable order — a collision must name the same offender every time.
        assert [d["extension"] for d in found] == ["alpha", "beta"]

    def test_an_unparseable_manifest_refuses_to_boot(self, tmp_path):
        """FAIL CLOSED. A manifest we cannot read is a set of routes we cannot honour, and
        booting without them serves a canvas whose every data call 404s — silently."""
        ext = tmp_path / "broken" / "ui" / "canvas"
        ext.mkdir(parents=True)
        (ext / "canvas_proxy.json").write_text("{ this is not json")

        with pytest.raises(ProxyCollisionError):
            discover_extension_proxies(tmp_path)

    def test_no_extensions_is_not_an_error(self, tmp_path):
        assert discover_extension_proxies(tmp_path) == []


class TestTheSeamRefusesToBootOnCollision:
    """A misconfigured seam must not come up. A host that boots and quietly routes one
    extension's traffic into another's data plane is worse than one that does not boot, because
    it looks like it is working."""

    def test_a_kernel_shadow_kills_the_boot(self, tmp_path):
        ext = tmp_path / "rogue" / "ui" / "canvas"
        ext.mkdir(parents=True)
        (ext / "canvas_proxy.json").write_text(json.dumps({"/__host_health": {"target": "http://127.0.0.1:9999"}}))
        with pytest.raises(ProxyCollisionError):
            create_app(extensions_root=tmp_path, env={})

    def test_two_extensions_on_one_prefix_kills_the_boot(self, tmp_path):
        for name in ("alpha", "beta"):
            d = tmp_path / name / "ui" / "canvas"
            d.mkdir(parents=True)
            (d / "canvas_proxy.json").write_text(
                json.dumps({"/api/v2": {"target": f"http://127.0.0.1:{9000 if name == 'alpha' else 9001}"}})
            )
        with pytest.raises(ProxyCollisionError):
            create_app(extensions_root=tmp_path, env={})


class TestTheHostServesTheCanvas:
    def _app(self, tmp_path, *, with_dist=True):
        dist = tmp_path / "dist"
        if with_dist:
            (dist / "assets").mkdir(parents=True)
            (dist / "index.html").write_text("<html>canvas</html>")
            (dist / "assets" / "app.js").write_text("// built")
        return create_app(dist=dist, extensions_root=tmp_path / "none", env={})

    def test_a_client_side_route_serves_index_html(self, tmp_path):
        """/app/read is a REACT-ROUTER route — there is no such file. StaticFiles(html=True)
        404s on it, which turns a hard refresh into a broken page."""
        c = TestClient(self._app(tmp_path))
        r = c.get("/app/read")
        assert r.status_code == 200
        assert "canvas" in r.text

    def test_a_real_asset_is_served_as_itself(self, tmp_path):
        c = TestClient(self._app(tmp_path))
        assert c.get("/assets/app.js").status_code == 200

    def test_the_host_health_route_is_not_swallowed_by_the_spa(self, tmp_path):
        """The catch-all is registered LAST for exactly this reason. If it were not, every route
        on this server would answer with index.html and a 200."""
        r = TestClient(self._app(tmp_path)).get("/__host_health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestTheProxyForwards:
    def test_a_declared_prefix_reaches_the_data_plane(self, tmp_path):
        """The whole point, end to end: a same-origin relative path on the canvas becomes a
        server-side call to the extension's data plane. No CORS, no exposed origin."""
        import threading

        import uvicorn
        from fastapi import FastAPI

        plane = FastAPI()

        @plane.get("/api/v2/state")
        async def state(item: str = "a"):
            return {"item": item, "value": 712.62}

        cfg = uvicorn.Config(plane, host="127.0.0.1", port=8799, log_level="error")
        server = uvicorn.Server(cfg)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        for _ in range(100):
            if server.started:
                break
            import time

            time.sleep(0.05)

        try:
            ext = tmp_path / "metrics" / "ui" / "canvas"
            ext.mkdir(parents=True)
            (ext / "canvas_proxy.json").write_text(json.dumps({"/api/v2": {"target": "http://127.0.0.1:8799"}}))
            dist = tmp_path / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<html>canvas</html>")

            app = create_app(dist=dist, extensions_root=tmp_path, env={})
            r = TestClient(app).get("/api/v2/state?item=b")

            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("application/json"), (
                "the proxy returned HTML — the SPA catch-all swallowed the data call. That is "
                "the 200-with-index.html failure an extension already shipped once."
            )
            assert r.json() == {"item": "b", "value": 712.62}
        finally:
            server.should_exit = True
            t.join(timeout=5)

    def test_an_unreachable_plane_is_a_READABLE_502(self, tmp_path):
        """Not an empty 500. 'The data plane is down' must not be diagnosable only as 'the canvas
        is broken' — that confusion is the whole reason this proxy exists instead of CORS."""
        ext = tmp_path / "metrics" / "ui" / "canvas"
        ext.mkdir(parents=True)
        (ext / "canvas_proxy.json").write_text(
            json.dumps({"/api/v2": {"target": "http://127.0.0.1:1"}})  # nothing listens on :1
        )
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>canvas</html>")

        r = TestClient(create_app(dist=dist, extensions_root=tmp_path, env={})).get("/api/v2/state")
        assert r.status_code == 502
        assert "data plane unreachable" in r.json()["error"]
        assert "127.0.0.1:1" in r.json()["target"]


class TestTheProxyDoesNotCorruptTheBODY:
    """THE BUG A BROWSER FOUND AND CURL COULD NOT.

    A browser sends `Accept-Encoding: gzip`, so the data plane gzips its reply. httpx then
    TRANSPARENTLY DECOMPRESSES it — upstream.content is already plain bytes. Copying the
    upstream `content-encoding: gzip` header onto that plaintext makes the browser try to gunzip
    plaintext: ERR_CONTENT_DECODING_FAILED, every request, blank page.

    curl does not send Accept-Encoding by default, so nothing was gzipped and every command-line
    check passed — 200, application/json, correct body. The proxy was completely broken in the
    only client that matters, and looked perfect everywhere else.
    """

    def test_a_gzipping_upstream_does_not_produce_a_mislabelled_body(self, tmp_path):
        import gzip
        import threading
        import time

        import uvicorn
        from fastapi import FastAPI
        from fastapi.responses import Response as FResponse

        plane = FastAPI()

        @plane.get("/api/v2/state")
        async def state():
            body = gzip.compress(json.dumps({"value": 712.62}).encode())
            # Exactly what a real plane does when the client says it accepts gzip.
            return FResponse(
                content=body,
                media_type="application/json",
                headers={"content-encoding": "gzip"},
            )

        cfg = uvicorn.Config(plane, host="127.0.0.1", port=8801, log_level="error")
        server = uvicorn.Server(cfg)
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)

        try:
            ext = tmp_path / "metrics" / "ui" / "canvas"
            ext.mkdir(parents=True)
            (ext / "canvas_proxy.json").write_text(json.dumps({"/api/v2": {"target": "http://127.0.0.1:8801"}}))
            dist = tmp_path / "dist"
            dist.mkdir()
            (dist / "index.html").write_text("<html>canvas</html>")

            app = create_app(dist=dist, extensions_root=tmp_path, env={})
            r = TestClient(app).get("/api/v2/state", headers={"Accept-Encoding": "gzip"})

            assert r.status_code == 200
            # The body httpx handed us is DECOMPRESSED. Saying otherwise is the bug.
            assert "content-encoding" not in {k.lower() for k in r.headers}, (
                "the proxy forwarded content-encoding over a body httpx already decompressed. "
                "A browser will try to gunzip plaintext and fail with "
                "ERR_CONTENT_DECODING_FAILED — while curl, which sends no Accept-Encoding, "
                "reports everything is fine."
            )
            assert r.json() == {"value": 712.62}
        finally:
            server.should_exit = True
            t.join(timeout=5)
