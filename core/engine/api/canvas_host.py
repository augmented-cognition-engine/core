"""The ACE canvas host — serves the built canvas, and the extension proxy seam in PRODUCTION.

WHY THIS EXISTS
---------------
The canvas reaches an extension's data plane through a SAME-ORIGIN relative path (`/api/v2/...`).
In development, vite's dev server forwards those paths — it reads each extension's
`ui/canvas/canvas_proxy.json` and installs a proxy. That is the whole reason an extension's
canvas works today.

It is also the whole reason it worked ONLY under `npm run dev`. A production build has no dev
server, so `/api/v2/state` would hit the canvas's own origin and 404. The obvious escape —
point the canvas at the data plane's origin with a VITE_*_DATA_URL — is worse: the browser
then makes a cross-origin request, and the data plane sends no CORS headers. Opening CORS to
fix that is wrong twice over. It puts a ZERO-AUTH data service on any page in any tab,
and it hides the failure everywhere a permissive middleware happens to be installed, so the
request only breaks in a real browser against the real plane — the one environment nobody
tests in.

So production does what development does: the page fetches a same-origin path and THE SERVER
forwards it. This is that server.

WHY NOT SERVE THE CANVAS FROM THE DATA PLANE
--------------------------------------------
Because it inverts the dependency. A data plane is one extension's data source; making it host
the ACE kernel's UI would mean an extension-specific service serves the canvas that every other
extension also uses, and ACE's releases would ride on that service's deploys. An extension that
has no data plane of its own could not be served that way at all. The kernel does not live
inside an extension, in either direction — the same rule that stops the kernel naming an
extension (which is why this paragraph names none).

THE KERNEL STILL NAMES NO EXTENSION
-----------------------------------
This module discovers `extensions/*/ui/canvas/canvas_proxy.json` and merges what it finds. It
never learns what any of it is for. Identical to `vite.config.ts`, deliberately: ONE manifest,
read by two servers.

Which is also the danger. Two implementations of a fail-closed merge is exactly the bug that
ships — dev refuses a collision, prod silently allows it, and one extension's traffic is routed
into another extension's data plane while both services answer 200 and the numbers are simply
someone else's. So the RULES are data (`core/ui/canvas_proxy_cases.json`) and BOTH
implementations are tested against them. Change the behaviour in one language and the other
language's test goes red.

    make canvas-host      # build the canvas, then serve it here
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

REPO = Path(__file__).resolve().parents[3]
CANVAS_DIST = REPO / "core" / "ui" / "canvas" / "dist"
EXTENSIONS = REPO / "extensions"

#: Prefixes the HOST itself routes. An extension may not shadow one.
#: Deliberately tiny — this server exists to serve the canvas and forward, nothing else.
KERNEL_PREFIXES: tuple[str, ...] = ("/__host_health",)


class ProxyCollisionError(Exception):
    """A declared proxy would shadow a kernel route, or two extensions want one prefix.

    This is raised at STARTUP, not per-request. A misconfigured seam must refuse to boot: a
    canvas host that comes up and quietly routes one extension's traffic into another's data
    plane is worse than one that does not come up, because it looks like it is working.
    """


def discover_extension_proxies(root: Path = EXTENSIONS) -> list[dict[str, Any]]:
    """Every `extensions/<name>/ui/canvas/canvas_proxy.json`, in a stable order.

    Sorted so that a collision names the same offender every time. A merge whose error message
    depends on filesystem iteration order is a merge nobody can debug.
    """
    if not root.is_dir():
        return []

    found: list[dict[str, Any]] = []
    for ext_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = ext_dir / "ui" / "canvas" / "canvas_proxy.json"
        if not manifest.is_file():
            continue
        try:
            declared = json.loads(manifest.read_text())
        except json.JSONDecodeError as exc:
            # FAIL CLOSED. A manifest we cannot parse is a manifest whose routes we cannot
            # honour, and booting without them serves a canvas whose every data call 404s.
            raise ProxyCollisionError(f"extension {ext_dir.name!r} has an unreadable canvas_proxy.json: {exc}") from exc
        for prefix, entry in declared.items():
            found.append({"extension": ext_dir.name, "prefix": prefix, "entry": entry})
    return found


def merge_extension_proxies(
    kernel_prefixes: tuple[str, ...] | list[str],
    declared: list[dict[str, Any]],
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge declared proxies, refusing anything ambiguous. Returns {prefix: target}.

    The Python half of the seam. Its TypeScript twin is `mergeExtensionProxies` in
    core/ui/canvas/src/design/devProxy.ts, and the two are held together by
    core/ui/canvas_proxy_cases.json — see the module docstring.
    """
    env = {} if env is None else env
    merged: dict[str, str] = {}
    claimed_by: dict[str, str] = {}

    for d in declared:
        extension, prefix, entry = d["extension"], d["prefix"], d["entry"]

        if not prefix.startswith("/"):
            raise ProxyCollisionError(f"extension {extension!r} declared proxy prefix {prefix!r}, which is not a path")

        if prefix in kernel_prefixes:
            raise ProxyCollisionError(
                f"extension {extension!r} tried to claim {prefix!r}, which the kernel already "
                f"routes. An extension cannot shadow a kernel route — pick a prefix the kernel "
                f"does not own."
            )

        incumbent = claimed_by.get(prefix)
        if incumbent is not None:
            raise ProxyCollisionError(
                f"extensions {incumbent!r} and {extension!r} both claim proxy prefix {prefix!r}. "
                f"Two data planes behind one path route each other's traffic silently — refusing."
            )
        claimed_by[prefix] = extension

        # An operator repoints a data plane without a commit. An EMPTY value is an unset
        # variable, not an instruction to proxy to nowhere.
        override = env.get(entry["targetEnv"]) if entry.get("targetEnv") else None
        merged[prefix] = override if override else entry["target"]

    return merged


#: Headers that must NOT be copied from the upstream response.
#:
#: CONTENT-ENCODING IS THE ONE THAT BITES, and it only bites in a real browser.
#:
#: A browser sends `Accept-Encoding: gzip`, so the data plane gzips its reply. httpx then
#: TRANSPARENTLY DECOMPRESSES it — `upstream.content` is already plain bytes. Copy the upstream
#: `content-encoding: gzip` header onto that plaintext and the browser dutifully tries to gunzip
#: it and dies: ERR_CONTENT_DECODING_FAILED, every request, blank page.
#:
#: curl does not send Accept-Encoding by default, so nothing is gzipped and it all looks
#: perfect: 200, application/json, correct body. The proxy passed every command-line check and
#: failed in the only client that matters. Same lesson as CORS — a proxy is not verified until a
#: browser has loaded a page through it.
#:
#: content-length goes for the same reason (it describes the compressed body) and the rest are
#: hop-by-hop: they describe THIS connection, not the payload.
_DROP = {
    "host",
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
    "te",
    "trailers",
    "proxy-authorization",
}


def create_app(
    *,
    dist: Path = CANVAS_DIST,
    extensions_root: Path = EXTENSIONS,
    env: dict[str, str] | None = None,
) -> FastAPI:
    env = dict(os.environ) if env is None else env

    # The merge happens HERE — at import/startup, before a single request is served. A seam
    # error must stop the boot, not surface as a mystery 502 an hour into a session.
    proxies = merge_extension_proxies(KERNEL_PREFIXES, discover_extension_proxies(extensions_root), env)

    app = FastAPI(title="ACE Canvas Host", docs_url=None, redoc_url=None)
    app.state.proxies = proxies
    app.state.dist = dist

    @app.get("/__host_health")
    async def host_health() -> dict[str, Any]:
        """The host's own health. Named with a `__` prefix precisely so it cannot collide with
        anything an extension would plausibly declare — and if one ever does, the merge above
        refuses to boot rather than letting a data plane answer for the host."""
        return {
            "ok": True,
            "canvas_built": dist.is_dir(),
            "proxies": proxies,
        }

    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False)

    @app.on_event("shutdown")
    async def _close() -> None:
        await client.aclose()

    def _install(prefix: str, target: str) -> None:
        @app.api_route(
            f"{prefix}/{{path:path}}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
            include_in_schema=False,
        )
        async def _proxy(request: Request, path: str, _t: str = target, _p: str = prefix) -> Response:
            url = httpx.URL(f"{_t}{_p}/{path}").copy_with(query=request.url.query.encode())
            headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
            try:
                upstream = await client.request(request.method, url, headers=headers, content=await request.body())
            except httpx.RequestError as exc:
                # A 502 the operator can actually read. The alternative — an empty body with a
                # 500 — is how "the data plane is down" gets misdiagnosed as "the canvas is
                # broken", which is the entire reason the proxy exists rather than CORS.
                return Response(
                    content=json.dumps({"error": "data plane unreachable", "target": _t, "detail": str(exc)}),
                    status_code=502,
                    media_type="application/json",
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                headers={k: v for k, v in upstream.headers.items() if k.lower() not in _DROP},
            )

    for prefix, target in proxies.items():
        _install(prefix, target)

    # ── the canvas itself ────────────────────────────────────────────────────────
    #
    # Registered LAST. The SPA fallback below is a catch-all, and a catch-all registered before
    # the proxies would swallow every data call and answer it with index.html — with a 200,
    # which the fetch would then fail to parse as JSON. That is the exact failure an extension
    # hit once (a data route left unproxied: SPA fallback, 200, an empty-state string over real
    # records). Order is load-bearing.
    if dist.is_dir():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="canvas-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> Response:
            """Serve a real file if it exists; otherwise index.html, so an extension's client-side
            routes work on a hard refresh. StaticFiles(html=True) 404s on those — it has
            no idea the router owns them."""
            candidate = dist / full_path
            if full_path and candidate.is_file() and dist in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
