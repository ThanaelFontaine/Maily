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


def test_keeps_safe_inline_style():
    out = sanitize_html('<p style="color:#ff0000;font-size:18px">hi</p>')
    assert "color:#ff0000" in out or "color: #ff0000" in out
    assert "font-size:18px" in out or "font-size: 18px" in out


def test_drops_dangerous_style():
    out = sanitize_html('<p style="position:fixed;color:red">x</p>')
    assert "position" not in out
    assert "color:red" in out or "color: red" in out


def test_drops_css_remote_background():
    out = sanitize_html('<div style="background:url(http://tracker.example/x.png)">y</div>')
    assert "tracker.example" not in out


def test_preserves_links_href():
    out = sanitize_html('<a href="https://ok.example">lien</a>')
    assert 'href="https://ok.example"' in out


def test_keeps_table_structure():
    out = sanitize_html('<table><tr><td style="padding:8px">c</td></tr></table>')
    assert "<td" in out and "padding:8px" in out or "padding: 8px" in out
