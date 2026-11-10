"""
Décisions demandées à l'utilisateur pendant le traitement (spec 001, F3/F5).

Sur le modèle de status.py : le script écrit une ligne structurée sur sa sortie
standard, l'interface web (gui_launcher.py) l'intercepte et affiche une carte de
décision, puis renvoie la réponse sur l'entrée standard du script.

    @@DECISION|{"id": "...", "society": "adn-dev", "period": "octobre 2026", "items": [...]}
    @@ANSWER|{"id": "...", "answers": {"<item id>": "<choix>"}}

Le mode automatique de l'interface envoie des lignes vides à chaque log : la
lecture de la réponse les ignore et n'accepte qu'une ligne @@ANSWER| portant le
même identifiant. Il n'y a pas de délai (arbitrage A4 : attendre sans limite).
"""

import json
import sys
import uuid

DECISION_PREFIX = "@@DECISION|"
ANSWER_PREFIX = "@@ANSWER|"
AMAZON_PREFIX = "@@AMAZON|"

# Choix possibles, identifiants stables échangés avec l'interface.
ATTACH = "attach"
LEAVE = "leave"
RETRY = "retry"

LABELS = {
    ATTACH: "Joindre la facture trouvée",
    LEAVE: "Laisser sans justificatif",
    RETRY: "Réessayer",
}


def ask(society, period, items, stdin=None, stdout=None):
    """
    Publie une décision et attend la réponse.

    `items` : liste de dicts avec au moins `id` et `choices` (identifiants
    ci-dessus). Renvoie {item_id: choix}. Une réponse absente ou invalide pour
    un élément vaut LEAVE : on ne joint jamais rien sans accord explicite.
    Si l'entrée standard se ferme (interface arrêtée), tout vaut LEAVE.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    decision_id = uuid.uuid4().hex
    payload = {
        "id": decision_id,
        "society": getattr(society, "value", society),
        "period": period,
        "items": items,
        "labels": LABELS,
    }
    stdout.write(DECISION_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n")
    stdout.flush()

    answers = {}
    while True:
        line = stdin.readline()
        if not line:
            break  # EOF
        line = line.strip()
        if not line.startswith(ANSWER_PREFIX):
            continue
        try:
            data = json.loads(line[len(ANSWER_PREFIX):])
        except ValueError:
            continue
        if data.get("id") != decision_id:
            continue
        answers = data.get("answers") or {}
        break

    result = {}
    for item in items:
        choice = answers.get(item["id"])
        result[item["id"]] = choice if choice in item["choices"] else LEAVE
    return result


def answer_line(decision_id, answers):
    """Ligne à écrire sur l'entrée standard du script pour répondre."""
    return ANSWER_PREFIX + json.dumps({"id": decision_id, "answers": answers}, ensure_ascii=False)


def summary(society, text, stdout=None, source="Amazon"):
    """Ligne « <source> » d'une société (Amazon, Free, Bouygues), affichée sous les pastilles."""
    stdout = stdout or sys.stdout
    payload = {"society": getattr(society, "value", society), "source": source, "text": text}
    stdout.write(AMAZON_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n")
    stdout.flush()
