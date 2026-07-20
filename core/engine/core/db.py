# engine/core/db.py
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from surrealdb import AsyncSurreal as AsyncSurrealDB

from core.engine.core.config import settings
from core.engine.core.log_context import get_correlation_id


class DBUnreachable(Exception):
    """Raised when the connect/signin/use handshake doesn't finish within CONNECT_TIMEOUT.

    Covers the "reachable but silent" failure mode — a host that accepts the TCP/WS
    connection but never completes the handshake (a VPN, a firewall, a port that isn't
    actually SurrealDB). Without a bound, that hangs `_create_connection` forever, which
    is exactly the outcome this exists to prevent. Carries the (redacted) URL so a caller
    like the API lifespan can build an actionable message without reaching back into
    settings itself.

    The OTHER failure mode — a closed port — already fails fast with a plain
    ConnectionRefusedError/OSError and is left alone; wrapping it here would add nothing.
    """

    def __init__(self, url: str, timeout: float) -> None:
        self.url = url
        self.timeout = timeout
        super().__init__(f"SurrealDB connect timed out after {timeout}s at {url}")


class SurrealPool:
    """Self-healing async connection pool for SurrealDB.

    Features:
    - Timeout on acquire (never block forever)
    - Health check on release (dead connections replaced)
    - Checkout tracking with lease expiry (leaked connections reclaimed)
    - Background watchdog replenishes pool every 30s
    - Observable: pool.stats() returns current state
    """

    ACQUIRE_TIMEOUT = 5.0  # seconds to wait for a free connection
    CONNECT_TIMEOUT = 5.0  # seconds to wait for the connect/signin/use handshake to finish.
    # A healthy local SurrealDB connects in <100ms, so 5s is comfortably above the real
    # path even on a cold store applying schema — this bound exists to catch the
    # UNhealthy path (a reachable host that never answers) instead of hanging forever.
    LEASE_TTL = 120.0  # seconds before a checked-out connection is considered leaked
    WATCHDOG_INTERVAL = 30.0  # seconds between watchdog sweeps

    def __init__(self, max_connections: int = 10) -> None:
        self._pool: asyncio.Queue | None = None
        self._max = max_connections
        self._initialized = False
        self._checkouts: dict[int, float] = {}  # conn id -> checkout timestamp
        self._watchdog_task: asyncio.Task | None = None
        self._total_created = 0
        self._total_recycled = 0
        self._total_leaked = 0
        self._logger = __import__("logging").getLogger(__name__)

    @staticmethod
    def _redact_url(url: str) -> str:
        """Strip credentials from a connection URL for safe logging.

        ws://user:pass@host:port/path  →  ws://***@host:port/path
        """
        import re

        return re.sub(r"(wss?://)([^@]+@)", r"\1***@", url)

    #: The loop a connection was born on, stamped onto the connection object.
    #:
    #: A SurrealDB WebSocket connection is bound to the event loop that created it — its
    #: pending futures live there. Hand it to a task on another loop and you get
    #: "RuntimeError: got Future attached to a different loop", raised inside whatever
    #: code happened to run the query, describing nothing that code did.
    _LOOP_ATTR = "_ace_pool_loop"

    async def _create_connection(self) -> AsyncSurrealDB:
        """Create and authenticate a new SurrealDB connection.

        The handshake is bounded by CONNECT_TIMEOUT (see class docstring on that
        constant). A closed port fails on its own, fast, via ConnectionRefusedError —
        that path is unaffected. A host that accepts the connection but never answers
        (VPN, firewall, wrong service on the port) would otherwise hang here forever;
        wait_for turns that into a DBUnreachable within CONNECT_TIMEOUT.
        """

        async def _handshake() -> AsyncSurrealDB:
            conn = AsyncSurrealDB(settings.surreal_url)
            await conn.connect()
            await conn.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
            await conn.use(settings.surreal_ns, settings.surreal_db)
            return conn

        try:
            conn = await asyncio.wait_for(_handshake(), timeout=self.CONNECT_TIMEOUT)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise DBUnreachable(self._redact_url(settings.surreal_url), self.CONNECT_TIMEOUT) from exc
        setattr(conn, self._LOOP_ATTR, asyncio.get_running_loop())
        self._total_created += 1
        return conn

    def _is_own_loop(self, conn: AsyncSurrealDB) -> bool:
        """Was this connection created on the loop we are running on right now?"""
        try:
            return getattr(conn, self._LOOP_ATTR, None) is asyncio.get_running_loop()
        except RuntimeError:  # no running loop — nothing can safely use it
            return False

    async def _discard(self, conn: AsyncSurrealDB) -> None:
        """Drop a connection we must not use. Best-effort: closing touches the transport
        on ITS loop, which may already be closed, so every failure here is expected and
        none of them is worth propagating."""
        self._total_recycled += 1
        try:
            await conn.close()
        except Exception:  # noqa: BLE001 — a dead loop cannot close its own socket
            pass

    async def init(self) -> None:
        if self._initialized:
            return
        # Build the queue LOCALLY and publish it only once it is actually usable.
        #
        # Publishing `self._pool` before filling it poisons the pool on any failed
        # init (the DB is down, credentials are wrong, the port is closed): the
        # attribute is left non-None but permanently EMPTY with _initialized still
        # False, so every later acquire() sees `self._pool is not None`, SKIPS init(),
        # and blocks on `self._pool.get()` for the full ACQUIRE_TIMEOUT (5s) waiting
        # for a connection that can never arrive. "The database is down" — an instant,
        # honest ECONNREFUSED — silently became a 5-SECOND TAX ON EVERY CALL, forever:
        # the process never re-inits, so it does not recover even after the DB comes
        # back. Measured: 1st acquire 0.01s, every subsequent one exactly 5.00s.
        # Leaving _pool unset on failure keeps the failure fast AND lets the next
        # acquire() retry init(), so the pool self-heals when the DB returns.
        pool: asyncio.Queue = asyncio.Queue(maxsize=self._max)
        try:
            for _ in range(self._max):
                conn = await self._create_connection()
                await pool.put(conn)
        except BaseException:
            while not pool.empty():
                await self._discard(pool.get_nowait())
            raise
        self._pool = pool
        self._initialized = True
        self._logger.info(
            "SurrealDB pool ready: %d connections → %s [%s/%s]",
            self._max,
            self._redact_url(settings.surreal_url),
            settings.surreal_ns,
            settings.surreal_db,
        )
        # Start background watchdog
        self._watchdog_task = asyncio.create_task(self._watchdog())

    async def _watchdog(self) -> None:
        """Background task: reclaim leaked connections and replenish pool."""
        while True:
            try:
                await asyncio.sleep(self.WATCHDOG_INTERVAL)
                now = asyncio.get_event_loop().time()

                # Find leaked connections (checked out longer than LEASE_TTL)
                leaked_ids = [
                    cid
                    for cid, checkout_time in list(self._checkouts.items())
                    if (now - checkout_time) > self.LEASE_TTL
                ]
                for cid in leaked_ids:
                    del self._checkouts[cid]
                    self._total_leaked += 1
                    self._logger.warning(
                        "Leaked connection %d reclaimed (checked out > %.0fs) [%s]",
                        cid,
                        self.LEASE_TTL,
                        get_correlation_id(),
                    )

                # Replenish pool if below target
                available = self._pool.qsize()
                checked_out = len(self._checkouts)
                target = self._max - checked_out
                deficit = target - available

                if deficit > 0:
                    replenished = 0
                    for _ in range(min(deficit, 3)):  # max 3 per sweep to avoid thundering herd
                        try:
                            conn = await asyncio.wait_for(self._create_connection(), timeout=5.0)
                            await self._pool.put(conn)
                            replenished += 1
                        except Exception:
                            break
                    if replenished > 0:
                        self._logger.info(
                            "Pool replenished: +%d connections (available: %d, checked_out: %d)",
                            replenished,
                            self._pool.qsize(),
                            checked_out,
                        )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self._logger.warning("Watchdog error: %s", exc)

    async def acquire(self) -> AsyncSurrealDB:
        if self._pool is None:
            await self.init()
        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=self.ACQUIRE_TIMEOUT)
        except (TimeoutError, asyncio.TimeoutError):
            self._logger.warning(
                "Pool exhausted (waited %.0fs, %d checked out) — creating fresh connection [%s]",
                self.ACQUIRE_TIMEOUT,
                len(self._checkouts),
                get_correlation_id(),
            )
            conn = await self._create_connection()
        except RuntimeError:
            # asyncio.Queue binds to a loop the moment it has to WAIT. An empty pool
            # reached from a second loop raises here rather than blocking. Serve the
            # caller from a fresh connection instead of failing.
            conn = await self._create_connection()

        # THE LOOP CHECK, AND IT HAS TO BE HERE.
        #
        # release() health-checks with `await conn.query("RETURN true")` — on the loop it
        # is LEAVING, where the connection is by definition fine. That check can never
        # catch a cross-loop hand-off, so a connection went back into the pool still bound
        # to a loop that was about to close, and the next acquirer on a new loop blew up
        # on first use — inside the caller, with a message about futures that named
        # nothing the caller had done.
        #
        # Acquire is the only moment we know BOTH which loop the connection belongs to and
        # which loop is about to use it.
        if not self._is_own_loop(conn):
            self._logger.debug("Connection belongs to another event loop — replacing [%s]", get_correlation_id())
            await self._discard(conn)
            conn = await self._create_connection()

        self._checkouts[id(conn)] = asyncio.get_event_loop().time()
        return conn

    async def release(self, conn: AsyncSurrealDB) -> None:
        # Remove from checkout tracking
        self._checkouts.pop(id(conn), None)

        # A connection from another loop must not go back into the pool — it would just be
        # handed to the next caller and fail there. Drop it, and top the pool back up so it
        # does not silently shrink toward zero.
        if not self._is_own_loop(conn):
            await self._discard(conn)
            try:
                await self._pool.put(await self._create_connection())
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Failed to replace a foreign-loop connection: %s [%s]",
                    exc,
                    get_correlation_id(),
                )
            return

        try:
            # Health check: verify connection is still alive
            await asyncio.wait_for(conn.query("RETURN true"), timeout=2.0)
            await self._pool.put(conn)
        except Exception:
            self._total_recycled += 1
            self._logger.warning("Dead connection recycled — replacing [%s]", get_correlation_id())
            try:
                await conn.close()
            except Exception:
                pass
            try:
                fresh = await self._create_connection()
                await self._pool.put(fresh)
            except Exception as exc:
                self._logger.error("Failed to create replacement: %s [%s]", exc, get_correlation_id())

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncSurrealDB]:
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)

    def stats(self) -> dict:
        """Observable pool state for monitoring/debugging."""
        return {
            "available": self._pool.qsize() if self._pool else 0,
            "checked_out": len(self._checkouts),
            "max": self._max,
            "total_created": self._total_created,
            "total_recycled": self._total_recycled,
            "total_leaked": self._total_leaked,
            "initialized": self._initialized,
        }

    async def close(self) -> None:
        """Drain the pool and close all connections."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        while self._pool and not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.close()
            except Exception:
                pass
        self._checkouts.clear()
        self._initialized = False


pool = SurrealPool()


def parse_record_id(s: str):
    """Convert a string like 'product:default' to a SurrealDB RecordID object.

    Required because SurrealDB v3 does not auto-coerce strings to record
    references when querying record<T> fields.
    """
    from surrealdb import RecordID

    if ":" in s:
        table, _, record = s.partition(":")
        return RecordID(table, record)
    return s


def parse_record_ids(ids: list):
    """Convert a list of id strings to RecordIDs for SurrealDB v3 `IN $list` queries.

    SurrealDB v3 does not coerce strings to record references in `WHERE col IN $list`
    against record<T> columns — a string-bound list matches ZERO rows. Maps
    parse_record_id over the list; elements that are already RecordIDs (or have no
    ':') pass through unchanged, so it's safe on mixed / untyped-array inputs.
    """
    return [parse_record_id(i) if isinstance(i, str) else i for i in ids]


def serialize_record(obj):
    """Recursively convert SurrealDB RecordID objects to strings for JSON serialization."""
    if hasattr(obj, "table_name"):
        return f"{obj.table_name}:{obj.id}" if hasattr(obj, "id") else str(obj)
    if isinstance(obj, dict):
        return {k: serialize_record(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_record(v) for v in obj]
    return obj


def parse_rows(result) -> list[dict]:
    """Safely parse SurrealDB query result into a list of dicts.

    SurrealDB v3 returns flat lists: [row1, row2, ...].
    Also handles: single dicts (ONLY queries), error strings, None, and
    legacy nested [[row1, ...]] format (v2 compat).

    RecordID objects are converted to strings so rows are always JSON-serializable.
    """
    if not result:
        return []
    if isinstance(result, str):
        return []  # error message
    if isinstance(result, dict):
        return [serialize_record(result)]  # ONLY queries return a single dict
    if isinstance(result, list):
        # v3 flat list of dicts: [row1, row2, ...]
        # v2 nested list: [[row1, row2, ...]]
        # Filter to only dict entries (skip error strings, None, etc.)
        if result and isinstance(result[0], list):
            # v2 nested format — unwrap
            return [serialize_record(r) for r in result[0] if isinstance(r, dict)]
        return [serialize_record(r) for r in result if isinstance(r, dict)]
    return []


def parse_one(result) -> dict | None:
    """Parse a SurrealDB query result expecting a single record.

    Use for: SELECT ... LIMIT 1, SELECT ... FROM ONLY, CREATE, UPDATE.
    Returns the first dict or None.

    RecordID objects are converted to strings so the result is always JSON-serializable.
    """
    rows = parse_rows(result)
    return rows[0] if rows else None
