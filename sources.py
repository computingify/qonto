"""
Socle commun des sources de justificatifs (spec 002, B1).

Une source (Amazon, Free, Bouygues) repère ses transactions sans justificatif,
retrouve la facture et la joint par l'API Qonto. Ce qui ne peut pas être
justifié automatiquement part dans UNE carte de décision par société, toutes
sources confondues (A3 de la spec 001).

Une étape (`Step`) fournit :
  - `select(transactions)` → (dans la période, hors période) ;
  - `find(transaction, refresh)` → dict `kind` = ok | partial | none | noref | unknown,
    avec `file` (PDF à joindre) quand il y en a un ;
  - `decision_item(transaction, found)` → élément de la carte de décision ;
  - `link(transaction, found)` → lien ou libellé rappelé dans les avertissements.

Le reste (jointure, décisions, réessais, avertissements, ligne de récapitulatif)
est commun et produit les mêmes messages pour toutes les sources.
"""

import json
import os
import subprocess

import requests

import decision

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]


# --- Outils ------------------------------------------------------------------

def normalize(text):
    """Espaces ramenés à un seul : Qonto écrit « AMAZON PAYMENTS EUROPE S  C  A »."""
    return " ".join((text or "").split())


def issuer(transaction):
    """Libellé et contrepartie normalisés, en majuscules."""
    return (normalize(transaction.get("label")) + " "
            + normalize(transaction.get("clean_counterparty_name"))).upper()


def transaction_month(transaction):
    """(année, mois) de la transaction, comme le zip : date de règlement d'abord."""
    date = transaction.get("settled_at") or transaction.get("emitted_at") or ""
    return int(date[:4]), int(date[5:7])


def transaction_date(transaction):
    return (transaction.get("settled_at") or transaction.get("emitted_at") or "")[:10]


def split_by_period(transactions, year, month, belongs):
    """Transactions de la source sans justificatif : (dans la période, hors période)."""
    inside, outside = [], []
    for transaction in transactions:
        if transaction.get("attachment_ids") or not belongs(transaction):
            continue
        if not transaction.get("amount"):
            continue
        if transaction_month(transaction) == (year, month):
            inside.append(transaction)
        else:
            outside.append(transaction)
    return inside, outside


def month_label(year, month):
    return f"{MONTHS[month - 1]} {year}"


def euros(amount):
    return f"{abs(float(amount)):.2f}".replace(".", ",") + " €"


def amount_fr(text):
    """« 1 371,00 » → 1371.0"""
    return float(text.replace(" ", "").replace(" ", "").replace("\xa0", "").replace(".", "").replace(",", "."))


def same_amount(a, b):
    return a is not None and b is not None and abs(abs(float(a)) - abs(float(b))) < 0.005


def day(transaction):
    date = transaction_date(transaction)
    return f"{date[8:10]}/{date[5:7]}/{date[:4]}"


# --- Lecture des PDF (PDFKit, intégré à macOS) -----------------------------

_PDF_SCRIPT = 'ObjC.import("PDFKit"); function run(a){ var d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(a[0])); return d ? d.string.js : ""; }'


def pdf_text(path):
    result = subprocess.run(["osascript", "-l", "JavaScript", "-e", _PDF_SCRIPT, path],
                            capture_output=True, text=True, timeout=60)
    return result.stdout


# --- Qonto ------------------------------------------------------------------

def fetch_transactions(base_url, headers, since):
    """Toutes les transactions depuis `since` (ISO), tous comptes, toutes pages."""
    organization = requests.get(base_url + "organization", headers=headers, timeout=30)
    organization.raise_for_status()
    transactions = []
    for account in organization.json()["organization"]["bank_accounts"]:
        page = 1
        while page:
            response = requests.get(base_url + "transactions", headers=headers, timeout=60, params={
                "bank_account_id": account["id"], "emitted_at_from": since,
                "status[]": ["completed"], "per_page": 100, "current_page": page})
            response.raise_for_status()
            data = response.json()
            transactions += data["transactions"]
            page = data["meta"].get("next_page")
    return transactions


def attachment_names(base_url, headers, transaction):
    """Noms des justificatifs déjà joints à une transaction."""
    names = []
    for attachment_id in transaction.get("attachment_ids") or []:
        response = requests.get(base_url + "attachments/" + attachment_id, headers=headers, timeout=30)
        response.raise_for_status()
        names.append(response.json()["attachment"].get("file_name") or "")
    return names


# --- Étape d'une source ------------------------------------------------------

class Step:
    """Étape « Justificatifs <source> » d'une société."""

    source = ""
    partial_title = "Justificatif {source} partiel joint"

    def __init__(self, society, year, month, attach, report, ask=decision.ask, transactions=None):
        self.society = getattr(society, "value", society)
        self.year, self.month = year, month
        self.attach = attach            # attach(transaction, chemin, nom) -> bool
        self.report = report
        self.ask = ask
        self.transactions = transactions or []
        self.left_ids = set()           # restées sans justificatif : signalées ici
        self.joined = 0
        self.partial = 0
        self.outside = []
        self.inside = []

    # À fournir par la source.
    def select(self, transactions):
        raise NotImplementedError

    def find(self, transaction, refresh=False):
        raise NotImplementedError

    def decision_item(self, transaction, found):
        raise NotImplementedError

    def link(self, transaction, found):
        raise NotImplementedError

    # Points d'extension facultatifs.
    def has_activity(self):
        """Faut-il publier une ligne de récapitulatif ? (Amazon : toujours.)"""
        return True

    def extra_summary(self):
        return ""

    def check_existing(self):
        """Contrôle des justificatifs déjà joints (spec 002, F4)."""

    # Déroulé commun.
    @property
    def period(self):
        return month_label(self.year, self.month)

    def prepare(self):
        """Joint ce qui est sûr ; renvoie [(transaction, found)] à décider."""
        self.inside, self.outside = self.select(self.transactions)
        print(f"{self.source} : {len(self.inside)} transaction(s) de {self.period} sans justificatif, "
              f"{len(self.outside)} hors période")
        pending = []
        for transaction in self.inside:
            found = self.find(transaction)
            if found["kind"] == "ok" and self._attach(transaction, found):
                self.joined += 1
            else:
                pending.append((transaction, found))
        return pending

    def resolve(self, transaction, found, choice):
        """Applique un choix ; renvoie True s'il faut réessayer."""
        if choice == decision.ATTACH and found.get("file") and self._attach(transaction, found):
            self.joined += 1
            self.partial += 1
            self.report.warning(self.partial_title.format(source=self.source),
                                f"{euros(transaction['amount'])} le {day(transaction)} — {self.link(transaction, found)}")
            return False
        if choice == decision.RETRY:
            return True
        self.left_ids.add(transaction["id"])
        self.report.warning(f"Transaction {self.source} sans justificatif",
                            f"{euros(transaction['amount'])} le {day(transaction)} — {self.link(transaction, found)}")
        return False

    def retry(self, transaction):
        found = self.find(transaction, refresh=True)
        if found["kind"] == "ok" and self._attach(transaction, found):
            self.joined += 1
            return None
        return found

    def pending_summary(self, pending_count):
        decision.summary(self.society, f"{self.joined} jointe(s) · {pending_count} décision(s) en attente",
                         source=self.source)

    def finish(self):
        if self.outside:
            months = sorted({transaction_month(t) for t in self.outside})
            self.report.warning(
                f"{len(self.outside)} transaction(s) {self.source} sans justificatif hors période",
                "à traiter avec la génération de " + ", ".join(month_label(y, m) for y, m in months))
        self.check_existing()
        text = f"{self.joined} jointe(s)"
        if self.partial:
            text += f" dont {self.partial} partielle(s)"
        text += f" · {len(self.left_ids)} sans justificatif · {len(self.outside)} hors période"
        text += self.extra_summary()
        if self.has_activity():
            decision.summary(self.society, text, source=self.source)
        print(f"{self.source} : {text}")
        return self.joined

    def run(self):
        """L'étape seule (une carte de décision pour elle)."""
        run_steps(self.society, self.period, [self], self.ask)
        return self.joined

    def _attach(self, transaction, found):
        name = os.path.basename(found["file"])
        return bool(self.attach(transaction, found["file"], name))


def run_steps(society, period, steps, ask=decision.ask):
    """
    Déroule plusieurs étapes pour une société : jointures automatiques, puis
    UNE carte de décision pour toutes les sources, répétée tant qu'on « Réessaie ».
    """
    pending = []                                    # [(step, transaction, found)]
    for step in steps:
        pending += [(step, t, f) for t, f in step.prepare()]

    while pending:
        for step in steps:
            count = sum(1 for s, _, _ in pending if s is step)
            if count:
                step.pending_summary(count)
        items = []
        for step, transaction, found in pending:
            item = step.decision_item(transaction, found)
            item.setdefault("source", step.source)
            items.append(item)
        answers = ask(society, period, items)
        retry = []
        for step, transaction, found in pending:
            if step.resolve(transaction, found, answers.get(transaction["id"], decision.LEAVE)):
                retry.append((step, transaction))
        pending = []
        for step, transaction in retry:
            found = step.retry(transaction)
            if found is not None:
                pending.append((step, transaction, found))

    for step in steps:
        step.finish()
    return steps
