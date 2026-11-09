"""
Justificatifs Amazon (spec 001).

Retrouve la facture Amazon de chaque transaction Qonto sans justificatif et la
joint par l'API. L'association se fait par la « référence de paiement » : la fin
de la référence Qonto (« 406-5893060-4448314 AMZN Mktp FR 5SC0HUQNCTU0ODQ4 »)
figure dans le PDF de la facture.

- F1 : repérer les transactions Amazon sans justificatif, dans la période
  (mois généré) ou hors période (signalées seulement, arbitrage A1).
- F2 : facture trouvée et montant identique → jointe sans rien demander.
- F3 : sinon → décision regroupée par société (A3), sans délai (A4).
- F4 : amazon.fr dans Google Chrome installé, profil réservé à l'application.
"""

import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime

import requests

import decision

ORDER_RE = r"[A-Z0-9]{3}-\d{7}-\d{7}"
REFERENCE_RE = re.compile(r"^(" + ORDER_RE + r") (AMZN Mktp FR|Amazon\.fr|Amazon Prime FR) (\S+)$", re.IGNORECASE)

ORDERS_URL = "https://www.amazon.fr/gp/css/order-history"
ORDER_URL = "https://www.amazon.fr/gp/your-account/order-details?orderID={}"
ASK_INVOICE_URL = "https://www.amazon.fr/gp/help/contact/contact.html?orderID={}"

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amazon-profile")

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]


# --- F1 : reconnaître et trier --------------------------------------------

def normalize(text):
    """Espaces ramenés à un seul : Qonto écrit « AMAZON PAYMENTS EUROPE S  C  A »."""
    return " ".join((text or "").split())


def parse_reference(reference):
    """(n° de commande, canal, référence de paiement) ou None."""
    match = REFERENCE_RE.match(normalize(reference))
    if not match:
        return None
    return match.group(1).upper(), match.group(2), match.group(3)


def is_amazon(transaction):
    issuer = (normalize(transaction.get("label")) + " "
              + normalize(transaction.get("clean_counterparty_name"))).upper()
    reference = normalize(transaction.get("reference")).upper()
    return ("AMAZON" in issuer or "AMZN" in reference
            or parse_reference(transaction.get("reference")) is not None)


def transaction_month(transaction):
    """(année, mois) de la transaction, comme le zip : date de règlement d'abord."""
    date = transaction.get("settled_at") or transaction.get("emitted_at") or ""
    return int(date[:4]), int(date[5:7])


def split_by_period(transactions, year, month):
    """Transactions Amazon sans justificatif : (dans la période, hors période)."""
    inside, outside = [], []
    for transaction in transactions:
        if transaction.get("attachment_ids") or not is_amazon(transaction):
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


def day(transaction):
    date = transaction.get("settled_at") or transaction.get("emitted_at") or ""
    return f"{date[8:10]}/{date[5:7]}/{date[:4]}"


# --- Lecture des PDF (PDFKit, intégré à macOS) -----------------------------

_PDF_SCRIPT = 'ObjC.import("PDFKit"); function run(a){ var d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(a[0])); return d ? d.string.js : ""; }'


def pdf_text(path):
    result = subprocess.run(["osascript", "-l", "JavaScript", "-e", _PDF_SCRIPT, path],
                            capture_output=True, text=True, timeout=60)
    return result.stdout


def _amount(text):
    return float(text.replace(" ", "").replace(" ", "").replace(".", "").replace(",", "."))


def parse_invoice(text):
    """(référence de paiement, total) lus dans le texte d'une facture ou d'un avoir."""
    reference = re.search(r"R[ée]f[ée]rence de paiement\s*:?\s*([A-Za-z0-9]{8,})", text)
    total = (re.search(r"(?:Facture|Avoir)\s+Total\s+(-?[\d  .]*\d,\d{2})\s*€", text)
             or re.search(r"Total à payer\s+(-?[\d  .]*\d,\d{2})\s*€", text))
    return (reference.group(1) if reference else None,
            abs(_amount(total.group(1))) if total else None)


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


# --- F4 : amazon.fr ---------------------------------------------------------

class AmazonLoginRequired(Exception):
    pass


class AmazonBrowser:
    """
    amazon.fr dans Google Chrome installé (channel « chrome »), avec un profil
    réservé à QontoUpdate : la session reste mémorisée d'une fois sur l'autre.
    Démarre sans fenêtre ; si Amazon demande une connexion, rouvre une fenêtre
    visible et attend que l'utilisateur se soit connecté.
    """

    def __init__(self, notify=print):
        self.notify = notify
        self._playwright = None
        self._context = None
        self._page = None
        self._headless = True

    def _launch(self, headless):
        from playwright.sync_api import sync_playwright
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._context is not None:
            self._context.close()
        self._context = self._playwright.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chrome", headless=headless, accept_downloads=True)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._headless = headless

    def _logged_in(self):
        url = self._page.url
        return "/ap/" not in url and ("order-history" in url or "/your-orders" in url)

    def _wait_login(self):
        """Attend la connexion ; hors des pages /ap/ (connexion, 2FA), on revient sur « Vos commandes »."""
        while not self._logged_in():
            self._page.wait_for_timeout(2000)
            if "/ap/" not in self._page.url and not self._logged_in():
                try:
                    self._page.goto(ORDERS_URL, wait_until="domcontentloaded")
                except Exception:
                    pass

    def open(self):
        if self._page is None:
            self._launch(headless=True)
        self._page.goto(ORDERS_URL, wait_until="domcontentloaded")
        if self._logged_in():
            return
        # Connexion nécessaire : fenêtre visible, on attend sans limite (A4).
        self._launch(headless=False)
        self._page.goto(ORDERS_URL, wait_until="domcontentloaded")
        self.notify("Amazon : connecte-toi à Amazon dans la fenêtre Chrome ouverte, l'application attend.")
        self._wait_login()
        self.notify("Amazon : connexion détectée, reprise.")

    def invoice_links(self, order_id):
        links = self._page.evaluate("""async (order) => {
            const r = await fetch('/your-orders/invoice/popover?orderId=' + order, { credentials: 'include' });
            if (r.url.includes('/ap/signin')) return null;
            const d = new DOMParser().parseFromString(await r.text(), 'text/html');
            return [...d.querySelectorAll('a')].map(a => a.getAttribute('href'))
                .filter(h => h && h.includes('/documents/download/'));
        }""", order_id)
        if links is None:
            raise AmazonLoginRequired()
        return ["https://www.amazon.fr" + h if h.startswith("/") else h for h in links]

    def download(self, url, dest):
        response = self._context.request.get(url, timeout=60000)
        body = response.body()
        if not response.ok or not body.startswith(b"%PDF"):
            raise IOError(f"téléchargement refusé ({response.status})")
        with open(dest, "wb") as handle:
            handle.write(body)

    def close(self):
        try:
            if self._context is not None:
                self._context.close()
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            self._context = self._playwright = self._page = None


_browser = None


def browser():
    """Une seule session Amazon pour toutes les sociétés."""
    global _browser
    if _browser is None:
        _browser = AmazonBrowser()
        _browser.open()
    return _browser


def close_browser():
    global _browser
    if _browser is not None:
        _browser.close()
        _browser = None


# --- F2 / F3 : associer, joindre, décider ------------------------------------

def find_invoice(transaction, invoices_for_order):
    """
    Cherche la facture d'une transaction. Renvoie un dict :
    kind = ok | partial | none | noref | unknown, plus `file`, `total`, `order`.
    `invoices_for_order(order)` renvoie [(chemin, référence, total), ...].
    """
    parsed = parse_reference(transaction.get("reference"))
    if not parsed:
        return {"kind": "unknown", "order": None}
    order, _, payment_ref = parsed
    invoices = invoices_for_order(order)
    if not invoices:
        return {"kind": "none", "order": order}
    for path, reference, total in invoices:
        if reference and reference.upper() == payment_ref.upper():
            if total is not None and abs(total - abs(float(transaction["amount"]))) < 0.005:
                return {"kind": "ok", "order": order, "file": path, "total": total}
            return {"kind": "partial", "order": order, "file": path, "total": total}
    return {"kind": "noref", "order": order}


def decision_item(transaction, found):
    amount = euros(transaction["amount"])
    order = found.get("order")
    refund = transaction.get("side") == "credit"
    kind = found["kind"]
    if kind == "partial":
        what = "avoir" if refund else "facture"
        if found.get("total") is not None and found["total"] < abs(float(transaction["amount"])):
            cause = f"{what.capitalize()} partielle : {euros(found['total'])} sur {amount} {'remboursés' if refund else 'débités'}. Un autre article n'a pas encore de {what}."
        else:
            cause = f"Montant différent : {what} de {euros(found['total']) if found.get('total') is not None else 'montant illisible'} pour {amount} {'remboursés' if refund else 'débités'}. Le reste a peut-être été payé par chèque-cadeau."
        choices = [decision.ATTACH, decision.LEAVE]
    elif kind == "none":
        cause = "Aucun avoir pour cette commande sur Amazon." if refund else "Aucune facture pour cette commande sur Amazon."
        choices = [decision.LEAVE, decision.RETRY]
    elif kind == "noref":
        cause = "Des factures existent pour cette commande, mais aucune ne porte la référence de paiement de cette transaction."
        choices = [decision.LEAVE, decision.RETRY]
    else:
        cause = f"Référence Qonto non reconnue : « {normalize(transaction.get('reference')) or 'vide'} » ({normalize(transaction.get('label'))}). Impossible de retrouver la commande."
        choices = [decision.LEAVE, decision.RETRY]
    return {
        "id": transaction["id"],
        "amount": ("+" if refund else "") + amount,
        "date": day(transaction),
        "order": order,
        "cause": cause,
        "severity": "partial" if kind == "partial" else "missing",
        "orderUrl": ORDER_URL.format(order) if order else ORDERS_URL,
        "askUrl": ASK_INVOICE_URL.format(order) if order and kind == "none" else None,
        "choices": choices,
    }


class AmazonStep:
    """Étape « Justificatifs Amazon » d'une société."""

    def __init__(self, society, year, month, attach, report, invoices_for_order=None,
                 ask=decision.ask, transactions=None):
        self.society = getattr(society, "value", society)
        self.year, self.month = year, month
        self.attach = attach            # attach(transaction, chemin, nom) -> bool
        self.report = report
        self.ask = ask
        self.transactions = transactions or []
        self._invoices_for_order = invoices_for_order or self._download_invoices
        self._cache = {}
        self._tmp = tempfile.mkdtemp(prefix="qonto-amazon-")
        self.left_ids = set()           # restées sans justificatif : signalées ici

    def _download_invoices(self, order):
        amazon = browser()
        try:
            links = amazon.invoice_links(order)
        except AmazonLoginRequired:
            amazon.open()
            links = amazon.invoice_links(order)
        invoices = []
        for index, url in enumerate(links, 1):
            path = os.path.join(self._tmp, f"Amazon_{order}_{index}.pdf")
            amazon.download(url, path)
            reference, total = parse_invoice(pdf_text(path))
            invoices.append((path, reference, total))
        return invoices

    def invoices(self, order, refresh=False):
        if refresh or order not in self._cache:
            self._cache[order] = self._invoices_for_order(order)
        return self._cache[order]

    def run(self):
        period = month_label(self.year, self.month)
        inside, outside = split_by_period(self.transactions, self.year, self.month)
        print(f"Amazon : {len(inside)} transaction(s) de {period} sans justificatif, {len(outside)} hors période")

        joined, partial = 0, 0
        pending = []
        for transaction in inside:
            found = self._find(transaction)
            if found["kind"] == "ok" and self._attach(transaction, found):
                joined += 1
            else:
                pending.append((transaction, found))

        # F3 : une décision regroupée par société, répétée tant qu'on « Réessaie ».
        while pending:
            decision.summary(self.society, f"{joined} jointe(s) · {len(pending)} décision(s) en attente")
            items = [decision_item(t, f) for t, f in pending]
            answers = self.ask(self.society, period, items)
            retry = []
            for transaction, found in pending:
                choice = answers.get(transaction["id"], decision.LEAVE)
                if choice == decision.ATTACH and found.get("file") and self._attach(transaction, found):
                    joined += 1
                    partial += 1
                    self.report.warning(
                        "Justificatif Amazon partiel joint",
                        f"{euros(transaction['amount'])} le {day(transaction)} — {ORDER_URL.format(found['order'])}")
                elif choice == decision.RETRY:
                    retry.append(transaction)
                else:
                    self.left_ids.add(transaction["id"])
                    self.report.warning(
                        "Transaction Amazon sans justificatif",
                        f"{euros(transaction['amount'])} le {day(transaction)} — "
                        + (ORDER_URL.format(found["order"]) if found.get("order") else normalize(transaction.get("label"))))
            pending = []
            for transaction in retry:
                found = self._find(transaction, refresh=True)
                if found["kind"] == "ok" and self._attach(transaction, found):
                    joined += 1
                else:
                    pending.append((transaction, found))

        if outside:
            months = sorted({transaction_month(t) for t in outside})
            self.report.warning(
                f"{len(outside)} transaction(s) Amazon sans justificatif hors période",
                "à traiter avec la génération de " + ", ".join(month_label(y, m) for y, m in months))

        text = f"{joined} jointe(s)"
        if partial:
            text += f" dont {partial} partielle(s)"
        text += f" · {len(self.left_ids)} sans justificatif · {len(outside)} hors période"
        decision.summary(self.society, text)
        print(f"Amazon : {text}")
        return joined

    def _find(self, transaction, refresh=False):
        parsed = parse_reference(transaction.get("reference"))
        if parsed and refresh:
            self.invoices(parsed[0], refresh=True)
        try:
            return find_invoice(transaction, self.invoices)
        except Exception as e:  # Amazon injoignable ou page changée : jamais au hasard
            self.report.error("Factures Amazon illisibles",
                              f"{euros(transaction['amount'])} le {day(transaction)} ({type(e).__name__}: {e})")
            return {"kind": "none", "order": parsed[0] if parsed else None}

    def _attach(self, transaction, found):
        name = os.path.basename(found["file"])
        return bool(self.attach(transaction, found["file"], name))
