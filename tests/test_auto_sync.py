import threading

from core import auto_sync


class FakeStore:
    def __init__(self, ids):
        self.ids = ids
        self.state = {}

    def list_accounts(self):
        return [{"id": i} for i in self.ids]

    def set_sync_state(self, aid, key, value):
        self.state[(aid, key)] = value


def test_sync_all_once_continue_apres_un_echec():
    store = FakeStore([1, 2, 3])

    def fn(aid):
        if aid == 2:
            raise RuntimeError("quota")
        return aid * 10

    res = auto_sync.sync_all_once(store, fn)
    assert res[1] == 10 and res[3] == 30
    assert "quota" in res[2]
    assert store.state[(2, "last_sync_error")].startswith("RuntimeError")
    assert store.state[(1, "last_sync_error")] == ""
    assert store.state[(1, "last_sync_at")]
    assert (2, "last_sync_at") not in store.state


def test_serialized_empeche_deux_synchros_simultanees():
    actives = []
    maxi = []
    gate = threading.Event()

    def lent(aid):
        actives.append(aid)
        maxi.append(len(actives))
        gate.wait(0.05)
        actives.remove(aid)
        return 0

    fn = auto_sync.serialized(lent)
    threads = [threading.Thread(target=fn, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(maxi) == 1


def test_auto_sync_passe_au_demarrage_puis_s_arrete():
    store = FakeStore([7])
    passages = []
    done = threading.Event()

    def fn(aid):
        passages.append(aid)
        done.set()
        return 0

    a = auto_sync.AutoSync(store, fn, interval_seconds=3600, initial_delay_seconds=0).start()
    assert done.wait(2)
    a.stop(timeout=2)
    assert passages == [7]
    assert not a._thread.is_alive()


def test_intervalle_plancher():
    a = auto_sync.AutoSync(FakeStore([]), lambda aid: 0, interval_seconds=5)
    assert a.interval == auto_sync.MIN_INTERVAL_SECONDS


def test_liste_des_comptes_en_panne_ne_tue_pas_le_fil():
    class Cassee(FakeStore):
        def list_accounts(self):
            raise RuntimeError("base verrouillee")

    a = auto_sync.AutoSync(Cassee([]), lambda aid: 0, interval_seconds=3600, initial_delay_seconds=0).start()
    a._stop.wait(0.2)
    assert a._thread.is_alive()
    a.stop(timeout=2)
