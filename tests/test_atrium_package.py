"""Checkout-free Atrium package and CLI contract."""

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from core.engine.atrium import static_dir
from core.engine.cli.commands import atrium as atrium_module

# Vite content-hash filenames look like `<name>-<hash>.<ext>`; the hash length
# and characters are a Vite implementation detail. Every pattern below matches
# on SHAPE (a reference to something under assets/) and never hardcodes a hash,
# so a future `npm run build:package` re-hashing every file cannot break these.
GENERATED_ASSET_SUFFIXES = (".js", ".css", ".woff2", ".woff", ".ttf", ".otf")
ASSET_HREF_PATTERN = re.compile(r'(?:src|href)="/assets/([^"]+)"')
# Any site-absolute src/href — /assets/* entrypoints, but also favicon and
# apple-touch-icon links under /brand/*, and anything similar added later.
# Excludes protocol-relative refs ("//host/...") via the negative lookahead,
# since those name an external origin rather than the packaged static tree.
LOCAL_ABS_REF_PATTERN = re.compile(r'(?:src|href)="(/(?!/)[^"]+)"')
# An /assets/<file> reference embedded inside a JS or CSS file — how Vite
# links a CSS @font-face to its hashed font file, and (defensively) how it
# WOULD link one JS/CSS chunk to another if it ever used absolute chunk urls.
ASSET_NAME_PATTERN = re.compile(r"assets/([A-Za-z0-9._-]+\.(?:js|css|woff2?|ttf|otf|png|jpe?g|svg))")
# How Vite ACTUALLY links a lazily-loaded chunk from its importer: a relative
# dynamic import, e.g. `import("./CodeIntelligenceOS-B0GKXQJt.js")` — both
# chunks land flat in the same assets/ directory.
REL_CHUNK_IMPORT_PATTERN = re.compile(r'import\(\s*["\']\./([A-Za-z0-9._-]+\.(?:js|css))["\']')

# The packaged Code Intelligence solution's own hashed chunk (see
# src/app/solutions/code/register.tsx's React.lazy). Matched by shape, never
# by a hardcoded hash, so a future rebuild's re-hashing cannot break this.
CODE_INTELLIGENCE_CHUNK_PATTERN = re.compile(r"^CodeIntelligenceOS-[A-Za-z0-9_-]+\.js$")

# The exact nested contract literals src/api/codeIntelligenceApi.ts's response
# validator checks every shape against (core/engine/code_intelligence/contracts.py).
# A package built before the validator existed ships none of these, in this
# chunk or anywhere else.
CODE_INTELLIGENCE_CONTRACT_LITERALS = (
    "ace.code-intelligence.atrium-journey-response/v1alpha1",
    "ace.code-intelligence.atrium-code-lens/v1alpha1",
    "ace.code-intelligence.context-manifest/v1alpha1",
    "ace.code-intelligence.coding-agent-handoff/v1alpha1",
    "ace.code-intelligence.repository-index/v1alpha1",
    "ace.code-intelligence.source-anchor/v1alpha1",
)
# The validator's Web Crypto anchor-identity check: subtle.digest("SHA-256", ...)
# over each anchor's canonical JSON (codeIntelligenceApi.ts's sha256Hex). Scoped
# to the Code Intelligence chunk specifically — "SHA-256" alone also appears
# unrelated to this feature elsewhere in the bundled app (e.g. an ECDSA verify
# call pulled in by a dependency), so the check must anchor on the digest() call
# shape, not the bare substring.
WEB_CRYPTO_DIGEST_PATTERN = re.compile(r"""\.digest\(\s*["']SHA-256["']""")
# The anchor id prefix (ANCHOR_ID_PREFIX) every derived evidence id is built from.
ANCHOR_ID_PREFIX_LITERAL_PATTERN = re.compile(r"""["']code_anchor["']""")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve_local_ref(root: Path, ref: str) -> Path:
    """Resolve one site-absolute src/href value against the packaged static
    root, exactly as a browser would resolve it from the served root. A
    reference that attempts to traverse outside the root is rejected
    outright, before it is ever joined against the filesystem; the caller is
    still responsible for checking that the resolved path names a real file.
    """
    if ".." in Path(ref).parts:
        raise ValueError(f"local reference attempts traversal: {ref}")
    resolved = (root / ref.lstrip("/")).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"local reference escapes the packaged static tree: {ref}")
    return resolved


def _referenced_asset_names(asset_path: Path) -> set[str]:
    if asset_path.suffix not in (".js", ".css"):
        return set()
    text = _read(asset_path)
    names = set(ASSET_NAME_PATTERN.findall(text))
    if asset_path.suffix == ".js":
        names |= set(REL_CHUNK_IMPORT_PATTERN.findall(text))
    return names


def test_packaged_atrium_has_an_entrypoint_and_hashed_assets() -> None:
    assets = static_dir()

    assert (assets / "index.html").is_file()
    assert any((assets / "assets").glob("*.js"))
    assert any((assets / "assets").glob("*.css"))


def test_packaged_index_references_resolve_and_leave_no_orphan_assets() -> None:
    """Walk index.html's direct JS/CSS refs, then recursively follow every
    asset THOSE reference (font urls, lazy-chunk imports) — every reference
    must resolve to a real file, and every generated JS/CSS/font file under
    static/assets must be reachable from that walk (no stale/orphan output
    left behind by a prior build)."""

    assets = static_dir()
    assets_dir = assets / "assets"
    index_html = _read(assets / "index.html")

    direct_refs = set(ASSET_HREF_PATTERN.findall(index_html))
    assert direct_refs, "packaged index.html references no /assets/* file"

    reachable: set[str] = set()
    frontier = list(direct_refs)
    while frontier:
        name = frontier.pop()
        if name in reachable:
            continue
        reachable.add(name)
        asset_path = assets_dir / name
        assert asset_path.is_file(), f"packaged asset reference resolves to a missing file: assets/{name}"
        frontier.extend(_referenced_asset_names(asset_path) - reachable)

    generated = {p.name for p in assets_dir.iterdir() if p.is_file() and p.suffix in GENERATED_ASSET_SUFFIXES}
    orphans = generated - reachable
    assert not orphans, (
        "generated JS/CSS/font file(s) under static/assets are unreachable from "
        f"index.html — stale output from a prior build: {sorted(orphans)}"
    )


def test_packaged_index_local_references_resolve_inside_static_tree() -> None:
    """Beyond the /assets/* entrypoint closure above, index.html also links
    favicons and an apple-touch-icon under /brand/* by a site-absolute href.
    Every src/href beginning with "/" is a same-origin reference into the
    packaged static tree and must resolve to a real file strictly inside it,
    with no traversal component silently accepted."""

    assets = static_dir().resolve()
    index_html = _read(assets / "index.html")

    local_refs = set(LOCAL_ABS_REF_PATTERN.findall(index_html))
    assert local_refs, "packaged index.html references no local (site-absolute) asset"
    assert any(ref.startswith("/brand/") for ref in local_refs), (
        "packaged index.html no longer references any /brand/* icon"
    )

    for ref in local_refs:
        resolved = _resolve_local_ref(assets, ref)
        assert resolved.is_file(), f"packaged index.html reference resolves to a missing file: {ref}"


def test_local_ref_resolution_rejects_traversal_and_missing_files(tmp_path: Path) -> None:
    """Regression for _resolve_local_ref against a disposable static tree: a
    well-formed reference resolves to the exact expected file, a traversal
    attempt is rejected before it ever touches the filesystem, and a
    reference that resolves inside the tree but names nothing is left for
    the caller's own is_file() check to catch (as the test above relies on).
    """

    root = tmp_path / "static"
    (root / "brand").mkdir(parents=True)
    (root / "brand" / "icon.png").write_bytes(b"\x89PNG\r\n")

    assert _resolve_local_ref(root, "/brand/icon.png") == root / "brand" / "icon.png"

    for hostile_ref in ("/../outside.png", "/brand/../../outside.png", "/../../../etc/passwd"):
        with pytest.raises(ValueError, match="traversal"):
            _resolve_local_ref(root, hostile_ref)

    broken = _resolve_local_ref(root, "/brand/missing.png")
    assert not broken.is_file()


def test_generated_bundle_registers_the_installed_code_solution() -> None:
    assets = static_dir()
    bundle_text = "".join(_read(p) for p in (assets / "assets").glob("*.js"))
    assert "/atrium/code" in bundle_text, (
        "the packaged JS bundle does not register the installed Code Intelligence solution's route (/atrium/code)"
    )


def _code_intelligence_chunk(assets_dir: Path) -> Path:
    chunks = [p for p in assets_dir.glob("CodeIntelligenceOS-*.js") if CODE_INTELLIGENCE_CHUNK_PATTERN.match(p.name)]
    assert len(chunks) == 1, (
        "expected exactly one packaged CodeIntelligenceOS-<hash>.js chunk under static/assets, "
        f"found {sorted(p.name for p in chunks)} — a stale package predating the Code "
        "Intelligence solution ships none"
    )
    return chunks[0]


def test_packaged_bundle_splits_a_dedicated_code_intelligence_chunk() -> None:
    """The installed Code Intelligence solution is lazy-loaded (see
    src/app/solutions/code/register.tsx's React.lazy), so a fresh package must
    emit it as its own hashed chunk reachable by dynamic import from the app
    shell's entrypoint — not inlined into the main bundle, and not absent."""

    assets = static_dir()
    assets_dir = assets / "assets"
    chunk = _code_intelligence_chunk(assets_dir)

    index_html = _read(assets / "index.html")
    entry_names = set(ASSET_HREF_PATTERN.findall(index_html)) & {p.name for p in assets_dir.glob("index-*.js")}
    assert entry_names, "packaged index.html references no index-*.js entrypoint"

    imported_by_entry: set[str] = set()
    for name in entry_names:
        imported_by_entry |= _referenced_asset_names(assets_dir / name)
    assert chunk.name in imported_by_entry, (
        f"the packaged entrypoint does not dynamically import {chunk.name} — the Code "
        "Intelligence chunk is unreachable from the app shell"
    )


def test_code_intelligence_chunk_ships_the_response_validator() -> None:
    """Behavioral fingerprint for the response validator in
    src/api/codeIntelligenceApi.ts (isValidJourneyResponse and friends): the
    exact nested contract literals every shape is checked against, and the Web
    Crypto SHA-256 anchor-identity check that binds each evidence id to the
    anchor content it was derived from. Scoped to the CodeIntelligenceOS chunk
    itself rather than the whole bundle, both because that is where this
    solution's code actually lands (see the split test above) and because a
    bare "SHA-256" substring also occurs unrelated to this feature elsewhere
    in the app."""

    assets_dir = static_dir() / "assets"
    chunk_text = _read(_code_intelligence_chunk(assets_dir))

    missing = [literal for literal in CODE_INTELLIGENCE_CONTRACT_LITERALS if literal not in chunk_text]
    assert not missing, f"packaged Code Intelligence chunk is missing contract literal(s): {missing}"

    assert WEB_CRYPTO_DIGEST_PATTERN.search(chunk_text) is not None, (
        'packaged Code Intelligence chunk does not call .digest("SHA-256", ...) — the '
        "anchor-identity Web Crypto check appears to be missing or stripped"
    )
    assert ANCHOR_ID_PREFIX_LITERAL_PATTERN.search(chunk_text) is not None, (
        'packaged Code Intelligence chunk is missing the "code_anchor" evidence-id prefix literal'
    )


def test_packaged_brand_and_live_brain_remain() -> None:
    assets = static_dir()
    brand_dir = assets / "brand"

    assert brand_dir.is_dir()
    assert any(brand_dir.glob("*.png"))
    assert (assets / "live-brain.json").is_file()


def test_atrium_command_serves_packaged_assets_and_the_configured_api(monkeypatch) -> None:
    launched: dict[str, object] = {}

    def run(app, **kwargs):
        launched.update({"app": app, **kwargs})

    monkeypatch.setattr(atrium_module.uvicorn, "run", run)
    result = CliRunner().invoke(
        atrium_module.atrium,
        ["--no-open", "--port", "6123"],
        obj={"url": "http://127.0.0.1:3000", "token": "test-token"},
    )

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:6123/atrium" in result.output
    assert launched["host"] == "127.0.0.1"
    assert launched["port"] == 6123
    assert launched["app"].state.dist == static_dir()
    assert launched["app"].state.core_api_url == "http://127.0.0.1:3000"


def test_atrium_command_refuses_to_serve_without_a_login() -> None:
    result = CliRunner().invoke(
        atrium_module.atrium,
        ["--no-open"],
        obj={"url": "http://127.0.0.1:3000", "token": None},
    )

    assert result.exit_code != 0
    assert "ace setup" in result.output


def test_pyproject_declares_atrium_package_data() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()

    assert '"core.engine.atrium"' in pyproject
    assert '"static/index.html"' in pyproject
