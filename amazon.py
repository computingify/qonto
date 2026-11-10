"""
Justificatifs Amazon (spec 001), sur le socle commun `sources` (spec 002, B1).

Retrouve la facture Amazon de chaque transaction Qonto sans justificatif et la
joint par l'API. L'association se fait par la « référence de paiement » : la fin
de la référence Qonto (« 406-5893060-4448314 AMZN Mktp FR 5SC0HUQNCTU0ODQ4 »)
figure dans le PDF de la facture.

- F1 : repérer les transactions Amazon sans justificatif, dans la période
  (mois généré) ou hors période (signalées seulement, arbitrage A1).
- F2 : facture trouvée et montant identique → jointe sans rien demander.
- F3 : sinon → décision regroupée par société (A3), sans délai (A4).
- F4 : amazon.fr dans Google Chrome installé, profil réservé à l'application
  (commun aux sites de justificatifs depuis la spec 002, B2).
"""

import os
import re
import tempfile

import browser as chrome
import decision
import sources
from sources import (day, euros, fetch_transactions, month_label, normalize,  # noqa: F401 (API publique)
                     pdf_text, transaction_month)

ORDER_RE = r"[A-Z0-9]{3}-\d{7}-\d{7}"
REFERENCE_RE = re.compile(r"^(" + ORDER_RE + r") (AMZN Mktp FR|Amazon\.fr|Amazon Prime FR) (\S+)$", re.IGNORECASE)

ORDERS_URL = "https://www.amazon.fr/gp/css/order-history"
ORDER_URL = "https://www.amazon.fr/gp/your-account/order-details?orderID={}"
ASK_INVOICE_URL = "https://www.amazon.fr/gp/help/contact/contact.html?orderID={}"

PROFILE_DIR = chrome.PROFILE_DIR


# --- F1 : reconnaître et trier --------------------------------------------

def parse_reference(reference):
    """(n° de commande, canal, référence de paiement) ou None."""
    match = REFERENCE_RE.match(normalize(reference))
    if not match:
        return None
    return match.group(1).upper(), match.group(2), match.group(3)


def is_amazon(transaction):
    reference = normalize(transaction.get("reference")).upper()
    return ("AMAZON" in sources.issuer(transaction) or "AMZN" in reference
            or parse_reference(transaction.get("reference")) is not None)


def split_by_period(transactions, year, month):
    """Transactions Amazon sans justificatif : (dans la période, hors période)."""
    return sources.split_by_period(transactions, year, month, is_amazon)


# --- Lecture des PDF ----------------------------------------------------------

def _amount(text):
    return sources.amount_fr(text)


def parse_invoice(text):
    """(référence de paiement, total) lus dans le texte d'une facture ou d'un avoir."""
    reference = re.search(r"R[ée]f[ée]rence de paiement\s*:?\s*([A-Za-z0-9]{8,})", text)
    total = (re.search(r"(?:Facture|Avoir)\s+Total\s+(-?[\d  .]*\d,\d{2})\s*€", text)
             or re.search(r"Total à payer\s+(-?[\d  .]*\d,\d{2})\s*€", text))
    return (reference.group(1) if reference else None,
            abs(_amount(total.group(1))) if total else None)


# --- F4 : amazon.fr ---------------------------------------------------------

class AmazonLoginRequired(Exception):
    pass


class AmazonBrowser(chrome.SiteBrowser):
    """amazon.fr dans la session Chrome commune."""

    name = "Amazon"
    home_url = ORDERS_URL

    def _logged_in(self):
        url = self._page.url
        return "/ap/" not in url and ("order-history" in url or "/your-orders" in url)

    def _on_login_page(self):
        return "/ap/" in self._page.url

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
        response = self.context.request.get(url, timeout=60000)
        body = response.body()
        if not response.ok or not body.startswith(b"%PDF"):
            raise IOError(f"téléchargement refusé ({response.status})")
        with open(dest, "wb") as handle:
            handle.write(body)


_browser = None


def browser():
    """Une seule session Amazon pour toutes les sociétés."""
    global _browser
    if _browser is None:
        _browser = AmazonBrowser()
        _browser.open()
    return _browser


def close_browser():
    """Ferme la session Chrome commune (fin du traitement)."""
    global _browser
    _browser = None
    chrome.SESSION.close()


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
        "source": "Amazon",
        "amount": ("+" if refund else "") + amount,
        "date": day(transaction),
        "order": order,
        "cause": cause,
        "severity": "partial" if kind == "partial" else "missing",
        "orderUrl": ORDER_URL.format(order) if order else ORDERS_URL,
        "askUrl": ASK_INVOICE_URL.format(order) if order and kind == "none" else None,
        "choices": choices,
    }


class AmazonStep(sources.Step):
    """Étape « Justificatifs Amazon » d'une société."""

    source = "Amazon"

    def __init__(self, society, year, month, attach, report, invoices_for_order=None,
                 ask=decision.ask, transactions=None):
        super().__init__(society, year, month, attach, report, ask=ask, transactions=transactions)
        self._invoices_for_order = invoices_for_order or self._download_invoices
        self._cache = {}
        self._tmp = tempfile.mkdtemp(prefix="qonto-amazon-")

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

    # --- Contrat du socle ---
    def select(self, transactions):
        return split_by_period(transactions, self.year, self.month)

    def find(self, transaction, refresh=False):
        parsed = parse_reference(transaction.get("reference"))
        if parsed and refresh:
            self.invoices(parsed[0], refresh=True)
        try:
            return find_invoice(transaction, self.invoices)
        except Exception as e:  # Amazon injoignable ou page changée : jamais au hasard
            self.report.error("Factures Amazon illisibles",
                              f"{euros(transaction['amount'])} le {day(transaction)} ({type(e).__name__}: {e})")
            return {"kind": "none", "order": parsed[0] if parsed else None}

    def decision_item(self, transaction, found):
        return decision_item(transaction, found)

    def link(self, transaction, found):
        return ORDER_URL.format(found["order"]) if found.get("order") else normalize(transaction.get("label"))
