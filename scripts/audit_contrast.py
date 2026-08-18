"""Audit de lisibilité : mesure le contraste WCAG réel (texte / fond) des
éléments clés du composer et des réglages, dans chaque thème. Sort 0 si tout
est >= seuil, 1 sinon. Sert de garde-fou visuel (peu importe le mode)."""
import sys, threading, time
import uvicorn, webview
from core import paths, runtime
from core.db import Database
from core.store import Store
from core.config import load_settings
from api.app import create_app
from app.bootstrap import (make_sync_fn, make_send_fn, make_act_fn, make_labels_fn,
                           make_attachment_fns, _frontend_dir, window_kwargs,
                           set_glass_alpha, get_glass_alpha)

layout = paths.ensure_runtime_dirs(paths.runtime_dir())
store = Store(Database(layout["db"]))
token = runtime.get_or_create_api_token()
dl, inl = make_attachment_fns(store, layout["attachments"])
app = create_app(store, token, sync_fn=make_sync_fn(store, load_settings().backfill_months),
                 send_fn=make_send_fn(store), act_fn=make_act_fn(store), download_fn=dl, inline_fn=inl,
                 labels_fn=make_labels_fn(store), frontend_dir=_frontend_dir(),
                 glass_fn=set_glass_alpha, glass_get_fn=get_glass_alpha)
PORT = 8796
threading.Thread(target=uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical")).run, daemon=True).start()
time.sleep(1.0)

# Cas audites : selecteur + seuil (texte principal 4.5, secondaire 3.0).
# base = couleur de fond assumee derriere les panneaux translucides du theme.
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
  var bases={aero:{r:190,g:225,b:245},glass:{r:22,g:24,b:30},dedsec:{r:10,g:11,b:14}};
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
]

RESULTS = {}


def probe(w):
    time.sleep(2.0)
    ok = True
    for theme in ("aero", "glass", "dedsec"):
        w.evaluate_js("setTheme('%s'); window.__cases=%s;" % (theme, __import__("json").dumps(CASES)))
        w.evaluate_js("document.getElementById('compose').click(); document.getElementById('settingsbtn') && document.getElementById('settingsbtn').click();")
        time.sleep(0.6)
        res = __import__("json").loads(w.evaluate_js(JS))
        for r in res:
            status = "OK" if r["ratio"] >= r["min"] else "FAIL"
            if r["ratio"] < r["min"]:
                ok = False
            print(f"[{theme:6}] {r['sel']:35} ratio={r['ratio']:5}  min={r['min']}  {status}", flush=True)
        w.evaluate_js("document.getElementById('c-close').click(); document.getElementById('settings-close') && document.getElementById('settings-close').click();")
    print("AUDIT_RESULT:", "PASS" if ok else "FAIL", flush=True)
    import os
    os._exit(0 if ok else 1)


win = webview.create_window("Maily", f"http://127.0.0.1:{PORT}/", **window_kwargs("darwin"))
webview.start(probe, win)
