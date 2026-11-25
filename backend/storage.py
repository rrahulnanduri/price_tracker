"""SQLite persistence: every live search is kept as a price observation, plus the watchlist."""

import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY,
    query_key   TEXT NOT NULL,
    product     TEXT NOT NULL,
    country     TEXT NOT NULL,
    currency    TEXT NOT NULL,
    provider    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    lowest      REAL NOT NULL,
    lowest_store TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_key ON searches (query_key, country, fetched_at);

CREATE TABLE IF NOT EXISTS offers (
    search_id     INTEGER NOT NULL REFERENCES searches (id) ON DELETE CASCADE,
    store         TEXT NOT NULL,
    title         TEXT NOT NULL,
    price         REAL NOT NULL,
    price_text    TEXT NOT NULL,
    url           TEXT NOT NULL,
    shipping_cost REAL,
    total         REAL NOT NULL,
    in_stock      INTEGER,
    condition     TEXT NOT NULL,
    relevance     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_offers_search ON offers (search_id);

CREATE TABLE IF NOT EXISTS watchlist (
    id              INTEGER PRIMARY KEY,
    query_key       TEXT NOT NULL,
    product         TEXT NOT NULL,
    country         TEXT NOT NULL,
    target_price    REAL,
    created_at      TEXT NOT NULL,
    last_checked_at TEXT,
    last_error      TEXT,
    alerted_at      TEXT,
    UNIQUE (query_key, country)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def query_key(product: str) -> str:
    """Searches that differ only in case or spacing share one history."""
    return " ".join(product.lower().split())


class Storage:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- observations ---------------------------------------------------------

    def record_search(self, product: str, country: str, currency: str, provider: str,
                      offers: list[dict], fetched_at: str | None = None) -> str:
        """Store one observation (a ranked, non-empty result list). Returns its timestamp."""
        fetched_at = fetched_at or now_iso()
        cheapest = min(offers, key=lambda o: o["total"])
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO searches (query_key, product, country, currency, provider, fetched_at,"
                " lowest, lowest_store) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (query_key(product), product, country, currency, provider, fetched_at,
                 cheapest["total"], cheapest["store"]),
            )
            self._db.executemany(
                "INSERT INTO offers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(cursor.lastrowid, o["store"], o["title"], o["price"], o["price_text"], o["url"],
                  o["shipping_cost"], o["total"],
                  None if o["in_stock"] is None else int(o["in_stock"]),
                  o["condition"], o["relevance"]) for o in offers],
            )
        return fetched_at

    def history(self, product: str, country: str, limit: int = 120) -> list[dict]:
        """Observations oldest first: [{fetched_at, lowest, lowest_store, stores: {store: total}}]."""
        with self._lock:
            searches = self._db.execute(
                "SELECT id, fetched_at, lowest, lowest_store FROM searches"
                " WHERE query_key = ? AND country = ? ORDER BY fetched_at DESC, id DESC LIMIT ?",
                (query_key(product), country, limit),
            ).fetchall()
            if not searches:
                return []
            ids = [row["id"] for row in searches]
            offers = self._db.execute(
                f"SELECT search_id, store, total FROM offers"
                f" WHERE search_id IN ({','.join('?' * len(ids))})", ids,
            ).fetchall()

        stores: dict[int, dict[str, float]] = {}
        for row in offers:
            stores.setdefault(row["search_id"], {})[row["store"]] = row["total"]
        return [
            {"fetched_at": row["fetched_at"], "lowest": row["lowest"],
             "lowest_store": row["lowest_store"], "stores": stores.get(row["id"], {})}
            for row in reversed(searches)
        ]

    # -- watchlist ------------------------------------------------------------

    def add_watch(self, product: str, country: str, target_price: float | None) -> dict:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO watchlist (query_key, product, country, target_price, created_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (query_key, country) DO UPDATE SET"
                " target_price = COALESCE(excluded.target_price, watchlist.target_price)",
                (query_key(product), product, country, target_price, now_iso()),
            )
        return self.find_watch(product, country)

    def update_watch(self, watch_id: int, **fields) -> bool:
        if not fields:
            return self.get_watch(watch_id) is not None
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._lock, self._db:
            cursor = self._db.execute(
                f"UPDATE watchlist SET {assignments} WHERE id = ?", (*fields.values(), watch_id)
            )
        return cursor.rowcount > 0

    def delete_watch(self, watch_id: int) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM watchlist WHERE id = ?", (watch_id,)).rowcount > 0

    def get_watch(self, watch_id: int) -> dict | None:
        return self._one_watch("w.id = ?", (watch_id,))

    def find_watch(self, product: str, country: str) -> dict | None:
        return self._one_watch("w.query_key = ? AND w.country = ?", (query_key(product), country))

    def count_watches(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]

    def list_watches(self) -> list[dict]:
        return self._watches("1 = 1", ())

    def _one_watch(self, where: str, params: tuple) -> dict | None:
        rows = self._watches(where, params)
        return rows[0] if rows else None

    def _watches(self, where: str, params: tuple) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT w.* FROM watchlist w WHERE {where} ORDER BY w.created_at DESC, w.id DESC",
                params,
            ).fetchall()
            watches = []
            for row in rows:
                recent = self._db.execute(
                    "SELECT lowest, lowest_store, currency, fetched_at FROM searches"
                    " WHERE query_key = ? AND country = ? ORDER BY fetched_at DESC, id DESC LIMIT 2",
                    (row["query_key"], row["country"]),
                ).fetchall()
                floor = self._db.execute(
                    "SELECT MIN(lowest) AS lowest FROM searches WHERE query_key = ? AND country = ?",
                    (row["query_key"], row["country"]),
                ).fetchone()["lowest"]
                latest = recent[0] if recent else None
                previous = recent[1] if len(recent) > 1 else None
                target = row["target_price"]
                watches.append({
                    "id": row["id"],
                    "product": row["product"],
                    "country": row["country"],
                    "target_price": target,
                    "created_at": row["created_at"],
                    # A product searched before it was tracked has already been checked once.
                    "last_checked_at": row["last_checked_at"] or (latest["fetched_at"] if latest else None),
                    "last_error": row["last_error"],
                    "alerted_at": row["alerted_at"],
                    "currency": latest["currency"] if latest else None,
                    "latest_price": latest["lowest"] if latest else None,
                    "latest_store": latest["lowest_store"] if latest else None,
                    "latest_at": latest["fetched_at"] if latest else None,
                    "previous_price": previous["lowest"] if previous else None,
                    "lowest_ever": floor,
                    "target_hit": bool(latest and target is not None and latest["lowest"] <= target),
                })
        return watches
