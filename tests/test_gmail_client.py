import httplib2
import pytest
from googleapiclient.errors import HttpError
from core.gmail import GmailClient, HistoryExpired


class FakeReq:
    def __init__(self, result=None, errors=None):
        self._result = result or {}
        self._errors = list(errors or [])

    def execute(self):
        if self._errors:
            raise self._errors.pop(0)
        return self._result


def _http_error(status):
    return HttpError(httplib2.Response({"status": status}), b"err")


def test_execute_retries_then_succeeds():
    client = GmailClient(service=object())
    req = FakeReq(result={"ok": 1}, errors=[_http_error(503), _http_error(429)])
    assert client._execute(req, _sleep=lambda s: None) == {"ok": 1}


def test_execute_reraises_non_retryable():
    client = GmailClient(service=object())
    req = FakeReq(errors=[_http_error(400)])
    with pytest.raises(HttpError):
        client._execute(req, _sleep=lambda s: None)


def test_list_history_raises_on_404():
    class FakeHistory:
        def list(self, **kw):
            return FakeReq(errors=[_http_error(404)])

    class FakeUsers:
        def history(self):
            return FakeHistory()

    class FakeService:
        def users(self):
            return FakeUsers()

    client = GmailClient(service=FakeService())
    with pytest.raises(HistoryExpired):
        client.list_history("999")
