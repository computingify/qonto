"""
Rapport d'état par société.

Le script d'extraction tourne dans un sous-processus dont la sortie standard est
lue par l'interface web (gui_launcher.py). Pour que l'interface puisse colorer
la pastille de chaque société et afficher la cause exacte d'un problème, le
script émet des lignes de statut structurées en plus des logs habituels :

    @@STATUS|{"society": "solio", "level": "error", "messages": [...]}

Ces lignes sont interceptées par l'interface et ne sont pas affichées telles
quelles dans les logs.
"""

import json
import sys

STATUS_PREFIX = "@@STATUS|"

# Société fictive utilisée pour les problèmes qui ne concernent aucune société
# en particulier (authentification Gmail, date invalide, etc.).
GLOBAL = "_global_"


class Level:
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


def _name(society):
    """Identifiant stable d'une société (la valeur, pas le nom du membre d'enum)."""
    return getattr(society, "value", society)


class Report:
    """Accumule les problèmes rencontrés pendant le traitement d'une société."""

    def __init__(self, society):
        self.society = _name(society)
        self.errors = []
        self.warnings = []

    def error(self, message, detail=""):
        """Problème bloquant : le zip produit est incomplet ou absent."""
        text = _format(message, detail)
        print(f"[ERREUR] {self.society}: {text}", flush=True)
        # Une même cause peut être détectée à plusieurs endroits du traitement
        # (l'API est interrogée deux fois) : inutile de l'afficher en double.
        if text not in self.errors:
            self.errors.append(text)

    def warning(self, message, detail=""):
        """Anomalie non bloquante : le zip est produit mais mérite un coup d'œil."""
        text = _format(message, detail)
        print(f"[ATTENTION] {self.society}: {text}", flush=True)
        if text not in self.warnings:
            self.warnings.append(text)

    def absorb(self, other):
        """Récupère les problèmes d'un autre rapport (celui de Qonto par ex.)."""
        for message in other.errors:
            if message not in self.errors:
                self.errors.append(message)
        for message in other.warnings:
            if message not in self.warnings:
                self.warnings.append(message)

    @property
    def level(self):
        if self.errors:
            return Level.ERROR
        if self.warnings:
            return Level.WARN
        return Level.OK

    @property
    def messages(self):
        return self.errors + self.warnings

    def emit(self):
        """Publie l'état final de la société vers l'interface."""
        emit(self.society, self.level, self.messages)


def _format(message, detail):
    return f"{message} — {detail}" if detail else str(message)


def emit(society, level, messages=None):
    """Écrit une ligne de statut sur la sortie standard."""
    payload = {
        "society": _name(society),
        "level": level,
        "messages": list(messages or []),
    }
    print(STATUS_PREFIX + json.dumps(payload, ensure_ascii=False), flush=True)
    sys.stdout.flush()


def running(society):
    emit(society, Level.RUNNING)
