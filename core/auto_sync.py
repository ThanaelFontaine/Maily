"""Automatic sync of every mailbox, while the app is open.

Maily used to sync only on click: `poll_interval_seconds` existed in the
settings but nothing read it. This background thread visits every account at a
regular interval. One sync at a time (the lock is shared with the "Sync" button
of the interface and the API), a failing account does not stop the others, and
each pass leaves its trace in `sync_state` (`last_sync_at`, `last_sync_error`)
for whoever reads the database.
"""
from __future__ import annotations
import datetime
import logging
import threading

log = logging.getLogger("maily.auto_sync")

# Floor: below it, the Gmail quota would be used up for nothing.
MIN_INTERVAL_SECONDS = 60


def serialized(sync_fn, lock=None):
    """Wraps `sync_fn` in a lock: two syncs never overlap."""
    lock = lock or threading.Lock()

    def _sync(account_id):
        with lock:
            return sync_fn(account_id)

    return _sync


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sync_all_once(store, sync_fn) -> dict:
    """One pass over every account; returns {account_id: count or error message}."""
    results = {}
    for acc in store.list_accounts():
        aid = acc["id"]
        try:
            results[aid] = sync_fn(aid)
            store.set_sync_state(aid, "last_sync_at", _now_iso())
            store.set_sync_state(aid, "last_sync_error", "")
        except Exception as e:  # a failing account does not block the others
            message = f"{type(e).__name__}: {e}"[:500]
            results[aid] = message
            log.warning("automatic sync of account %s failed: %s", aid, message)
            try:
                store.set_sync_state(aid, "last_sync_error", message)
            except Exception:
                pass
    return results


class AutoSync:
    """Background thread: one pass at startup, then one every `interval` seconds."""

    def __init__(self, store, sync_fn, interval_seconds, initial_delay_seconds=5.0):
        self.store = store
        self.sync_fn = sync_fn
        self.interval = max(MIN_INTERVAL_SECONDS, int(interval_seconds))
        self.initial_delay = max(0.0, float(initial_delay_seconds))
        self._stop = threading.Event()
        self._thread = None

    def run_forever(self):
        if self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            try:
                sync_all_once(self.store, self.sync_fn)
            except Exception as e:  # listing the accounts itself failed
                log.warning("automatic sync impossible: %s", e)
            if self._stop.wait(self.interval):
                return

    def start(self):
        self._thread = threading.Thread(target=self.run_forever, name="maily-auto-sync", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout=None):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
