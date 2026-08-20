"""Deverrouillage par Touch ID au lancement (macOS, framework LocalAuthentication).

`require_unlock()` renvoie True si l'utilisateur s'authentifie (empreinte, avec
repli mot de passe de session), False s'il annule/echoue. Politique de securite :

- Hors macOS, si le framework est absent, ou si aucun capteur biometrique n'est
  configure  -> on N'IMPRIME PAS de porte (renvoie True) : on ne verrouille
  jamais l'app hors d'un poste equipe, pour ne pas enfermer l'utilisateur.
- Sur un Mac avec Touch ID configure -> l'authentification est REQUISE : un echec
  ou une annulation renvoie False (l'app doit se fermer).
- Variable d'environnement MAILY_NO_BIOMETRIC=1 -> desactive la porte (debug).

L'appel est bloquant et pompe la run loop du thread principal pour afficher la
feuille systeme meme avant le demarrage de la fenetre applicative.
"""
from __future__ import annotations
import os
import sys
import threading

# LAPolicyDeviceOwnerAuthentication = biometrie + repli mot de passe de session.
# (Evite un blocage si l'empreinte echoue plusieurs fois.)
_LA_POLICY = 2


def _disabled() -> bool:
    return bool(os.environ.get("MAILY_NO_BIOMETRIC"))


def require_unlock(reason: str = "Deverrouiller Maily") -> bool:
    if sys.platform != "darwin" or _disabled():
        return True
    try:
        import LocalAuthentication
        import Foundation
        import AppKit
    except Exception:
        # Framework indisponible : on ne bloque pas.
        return True

    ctx = LocalAuthentication.LAContext.alloc().init()
    can, _err = ctx.canEvaluatePolicy_error_(_LA_POLICY, None)
    if not can:
        # Aucun mecanisme d'authentification exploitable : pas de porte.
        return True

    # S'assure d'etre une app graphique active pour afficher la feuille Touch ID.
    try:
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(0)  # NSApplicationActivationPolicyRegular
        app.activateIgnoringOtherApps_(True)
    except Exception:
        pass

    result: dict = {}
    done = threading.Event()

    def _reply(success, error):
        result["ok"] = bool(success)
        done.set()

    ctx.evaluatePolicy_localizedReason_reply_(_LA_POLICY, reason, _reply)

    rl = Foundation.NSRunLoop.currentRunLoop()
    while not done.is_set():
        rl.runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode, Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.05))
    return result.get("ok", False)
