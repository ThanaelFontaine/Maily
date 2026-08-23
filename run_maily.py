"""Point d'entree de l'application empaquetee (PyInstaller)."""
from __future__ import annotations
import multiprocessing
import sys


def _tls_selftest() -> int:
    """Verifie que TLS marche dans le binaire fige (certifi + requests).

    Reproduit exactement le chemin qui echouait a l'ajout d'un compte Google
    (echange de token OAuth via requests). Usage : `Maily --tls-selftest`.
    """
    import certifi
    import os
    where = certifi.where()
    print(f"certifi.where() = {where} (exists={os.path.exists(where)})")
    import requests
    try:
        r = requests.get("https://oauth2.googleapis.com/", timeout=8)
        print(f"TLS OK -> HTTP {r.status_code}")
        return 0
    except Exception as e:
        print(f"TLS FAIL -> {type(e).__name__}: {e}")
        return 1


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--tls-selftest":
        raise SystemExit(_tls_selftest())
    from app.bootstrap import run
    run()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # necessaire sous Windows en binaire figé
    main()
