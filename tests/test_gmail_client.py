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


def _http_error(status, content=b"err"):
    return HttpError(httplib2.Response({"status": status}), content)


_QUOTA = b'{"error": {"errors": [{"domain": "usageLimits", "reason": "rateLimitExceeded"}], "code": 403}}'


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


def test_modify_and_trash_build_requests():
    captured = {}

    class FakeMessages:
        def modify(self, userId, id, body):
            captured["modify"] = (id, body)
            return FakeReq(result={"id": id})

        def trash(self, userId, id):
            captured["trash"] = id
            return FakeReq(result={"id": id})

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    client = GmailClient(service=FakeService())
    client.modify("g1", add=["A"], remove=["UNREAD"])
    assert captured["modify"] == ("g1", {"addLabelIds": ["A"], "removeLabelIds": ["UNREAD"]})
    client.trash("g2")
    assert captured["trash"] == "g2"


def test_execute_retries_gmail_quota_403_with_minute_scale_backoff():
    client = GmailClient(service=object())
    attentes = []
    req = FakeReq(result={"ok": 1}, errors=[_http_error(403, _QUOTA)] * 5)
    assert client._execute(req, _sleep=attentes.append) == {"ok": 1}
    assert sum(attentes) >= 60, "l'attente couvre la minute du quota"


def test_execute_does_not_retry_forbidden_403():
    client = GmailClient(service=object())
    req = FakeReq(errors=[_http_error(403, b'{"error": {"errors": [{"reason": "insufficientPermissions"}]}}'), _http_error(403)])
    with pytest.raises(HttpError):
        client._execute(req, _sleep=lambda s: None)
    assert len(req._errors) == 1, "un seul essai"
