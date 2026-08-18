"""Point d'entree de l'application empaquetee (PyInstaller)."""
from __future__ import annotations
import multiprocessing


def main() -> None:
    from app.bootstrap import run
    run()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # necessaire sous Windows en binaire figé
    main()
