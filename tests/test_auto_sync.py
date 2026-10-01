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


def test_sync_all_once_goes_on_after_a_failure():
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


def test_serialized_prevents_two_simultaneous_syncs():
    running = []
    peaks = []
    gate = threading.Event()

    def slow(aid):
        running.append(aid)
        peaks.append(len(running))
        gate.wait(0.05)
        running.remove(aid)
        return 0

    fn = auto_sync.serialized(slow)
    threads = [threading.Thread(target=fn, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(peaks) == 1


def test_auto_sync_runs_at_startup_then_stops():
    store = FakeStore([7])
    passes = []
    done = threading.Event()

    def fn(aid):
        passes.append(aid)
        done.set()
        return 0

    a = auto_sync.AutoSync(store, fn, interval_seconds=3600, initial_delay_seconds=0).start()
    assert done.wait(2)
    a.stop(timeout=2)
    assert passes == [7]
    assert not a._thread.is_alive()


def test_interval_floor():
    a = auto_sync.AutoSync(FakeStore([]), lambda aid: 0, interval_seconds=5)
    assert a.interval == auto_sync.MIN_INTERVAL_SECONDS


def test_failing_account_listing_does_not_kill_the_thread():
    class Broken(FakeStore):
        def list_accounts(self):
            raise RuntimeError("database locked")

    a = auto_sync.AutoSync(Broken([]), lambda aid: 0, interval_seconds=3600, initial_delay_seconds=0).start()
    a._stop.wait(0.2)
    assert a._thread.is_alive()
    a.stop(timeout=2)
