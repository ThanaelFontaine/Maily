"""Legibility audit: measures the real WCAG contrast (text / background) of
the key elements of the composer and the settings, in every theme. Exits with
0 if everything is >= the threshold, 1 otherwise. A visual safeguard
(whatever the mode).

Runs on a demo database in a temporary folder: never on the real data or the
real secrets (the API token is generated in memory). Needs macOS and a screen
(pywebview). Run it with:
  MAILY_GUI_TESTS=1 uv run pytest tests/test_contrast.py
"""
import os, pathlib, secrets, sys, tempfile, threading, time
os.environ["MAILY_DATA_DIR"] = tempfile.mkdtemp(prefix="maily-audit-")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import uvicorn, webview
from core import paths
from core.db import Database
from core.store import Store
from api.app import create_app
from app.bootstrap import _frontend_dir, window_kwargs
import demo

layout = paths.ensure_runtime_dirs(paths.runtime_dir())
store = Store(Database(layout["db"]))
demo.seed(store)
token = secrets.token_urlsafe(24)
app = create_app(store, token, frontend_dir=_frontend_dir())
PORT = 8796
threading.Thread(target=uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical")).run, daemon=True).start()
time.sleep(1.0)

# Audited cases: selector + threshold (main text 4.5, secondary 3.0).
# base = background color assumed behind the translucent panels of the theme.
JS = r"""
(function(){
  function parse(c){var m=c.match(/[\d.]+/g)||[];return {r:+m[0]||0,g:+m[1]||0,b:+m[2]||0,a:m[3]==null?1:+m[3]};}
  function over(f,b){var a=f.a;return {r:f.r*a+b.r*(1-a),g:f.g*a+b.g*(1-a),b:f.b*a+b.b*(1-a),a:1};}
  function lin(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
  function lum(c){return 0.2126*lin(c.r)+0.7152*lin(c.g)+0.0722*lin(c.b);}
  function ratio(a,b){var L1=lum(a),L2=lum(b);var hi=Math.max(L1,L2),lo=Math.min(L1,L2);return (hi+0.05)/(lo+0.05);}
  function bgOf(el,base){
    var stack=[];var n=el;
    while(n){var bc=parse(getComputedStyle(n).backgroundColor); if(bc.a>0) stack.push(bc); n=n.parentElement;}
    var acc={r:base.r,g:base.g,b:base.b,a:1};
    for(var i=stack.length-1;i>=0;i--) acc=over(stack[i],acc);
    return acc;
  }
  var theme=document.documentElement.dataset.theme;
  var bases={classic:{r:255,g:255,b:255},aero:{r:190,g:225,b:245},glass:{r:22,g:24,b:30},zeroday:{r:10,g:11,b:14}};
  var base=bases[theme]||{r:20,g:20,b:24};
  var cases=window.__cases||[];
  var out=[];
  cases.forEach(function(c){
    var el=document.querySelector(c.sel); if(!el) return;
    var bg=bgOf(el,base);
    var fg=over(parse(getComputedStyle(el).color),bg);
    out.push({sel:c.sel,min:c.min,ratio:Math.round(ratio(fg,bg)*100)/100});
  });
  return JSON.stringify(out);
})();
"""

CASES = [
    {"sel": "#composer-title", "min": 4.5},
    {"sel": ".composer .c-lbl", "min": 3.0},
    {"sel": "#c-to", "min": 4.5},
    {"sel": ".settingsmenu .composer-head span", "min": 4.5},
    {"sel": ".settings-name", "min": 4.5},
    {"sel": ".settings-email", "min": 3.0},
    {"sel": ".settings-tab.on", "min": 4.5},
    {"sel": ".settings-help", "min": 4.5},
]

RESULTS = {}


def probe(w):
    time.sleep(2.0)
    ok = True
    for theme in ("classic", "aero", "glass", "zeroday"):
        w.evaluate_js("setTheme('%s'); window.__cases=%s;" % (theme, __import__("json").dumps(CASES)))
        w.evaluate_js("document.getElementById('compose').click(); openSettings('accounts');")
        time.sleep(0.6)
        res = __import__("json").loads(w.evaluate_js(JS))
        for r in res:
            status = "OK" if r["ratio"] >= r["min"] else "FAIL"
            if r["ratio"] < r["min"]:
                ok = False
            print(f"[{theme:7}] {r['sel']:35} ratio={r['ratio']:5}  min={r['min']}  {status}", flush=True)
        w.evaluate_js("document.getElementById('c-close').click(); closeSettings();")
    print("AUDIT_RESULT:", "PASS" if ok else "FAIL", flush=True)
    import os
    os._exit(0 if ok else 1)


win = webview.create_window("Maily", f"http://127.0.0.1:{PORT}/", **window_kwargs("darwin"))
webview.start(probe, win)
