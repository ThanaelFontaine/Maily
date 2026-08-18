from core.sanitize import sanitize_html


def test_removes_script():
    out = sanitize_html("<p>hi</p><script>alert(1)</script>")
    assert "<script" not in out
    assert "hi" in out


def test_blocks_remote_image_by_default():
    out = sanitize_html('<img src="http://tracker.example/pixel.png">')
    assert "tracker.example" not in out


def test_allows_remote_when_opted_in():
    out = sanitize_html('<img src="https://ok.example/i.png">', allow_remote=True)
    assert "ok.example" in out


def test_keeps_cid_image():
    out = sanitize_html('<img src="cid:logo123">')
    assert "cid:logo123" in out
