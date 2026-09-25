"""Synchronisation automatique de toutes les boites, tant que l'app est ouverte.

Jusqu'ici Maily ne synchronisait qu'au clic : `poll_interval_seconds` existait
dans les reglages sans que rien ne le lise. Ce fil de fond passe sur chaque
compte a intervalle regulier. Une seule synchro a la fois (le verrou est partage
avec le bouton « Synchroniser » de l'interface et l'API), un compte en echec
n'arrete pas les autres, et chaque passage laisse sa trace dans `sync_state`
(`last_sync_at`, `last_sync_error`) pour qui lit la base.
"""
from __future__ import annotations
import datetime
import logging
import threading

log = logging.getLogger("maily.auto_sync")

# Plancher : en dessous, on userait le quota Gmail pour rien.
MIN_INTERVAL_SECONDS = 60


def serialized(sync_fn, lock=None):
    """Enveloppe `sync_fn` d'un verrou : deux synchros ne se croisent jamais."""
    lock = lock or threading.Lock()

    def _sync(account_id):
        with lock:
            return sync_fn(account_id)

    return _sync


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sync_all_once(store, sync_fn) -> dict:
    """Un passage sur tous les comptes ; rend {account_id: nombre ou message d'erreur}."""
    results = {}
    for acc in store.list_accounts():
        aid = acc["id"]
        try:
            results[aid] = sync_fn(aid)
            store.set_sync_state(aid, "last_sync_at", _now_iso())
            store.set_sync_state(aid, "last_sync_error", "")
        except Exception as e:  # un compte en panne ne bloque pas les autres
            message = f"{type(e).__name__}: {e}"[:500]
            results[aid] = message
            log.warning("synchro automatique du compte %s en echec : %s", aid, message)
            try:
                store.set_sync_state(aid, "last_sync_error", message)
            except Exception:
                pass
    return results


class AutoSync:
    """Fil de fond : un passage au demarrage, puis un toutes les `interval` secondes."""

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
            except Exception as e:  # la liste des comptes elle-meme a echoue
                log.warning("synchro automatique impossible : %s", e)
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
