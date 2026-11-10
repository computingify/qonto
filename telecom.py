"""
Justificatifs Bouygues Telecom et Free (spec 002), sur le socle `sources`.

Free     : la référence Qonto « Free HautDebit 1510870586 » porte le n° de la
           facture ; l'espace abonné liste les PDF par n° (clé exacte).
Bouygues : la référence est le n° de ligne masqué ; on associe par le montant
           et la date (facture du 27 du mois M-1, prélevée vers le 7-9 du mois M),
           et le PDF le confirme (« Montant prélevé le 9 novembre 2026 17,99 »).

F4 : les justificatifs déjà joints du mois sont contrôlés d'après leur nom
d'origine ; une erreur est signalée en orange, rien n'est modifié sur Qonto (B3).
"""

import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

import browser as chrome
import decision
import sources
from sources import day, euros, normalize, same_amount

PARIS = ZoneInfo("Europe/Paris")

FREE_HOME = "https://subscribe.free.fr/login/"
BOUYGUES_HOME = "https://www.bouyguestelecom.fr/mon-compte/mes-factures"

FREE_REFERENCE_RE = re.compile(r"^Free HautDebit (\d+)$", re.IGNORECASE)
FREE_FILE_RE = re.compile(r"^Facture_Free_(\d{6})_(\d+)_(\d+)(?:-\d+)?\.pdf$", re.IGNORECASE)
BOUYGUES_FILE_RE = re.compile(r"^Bouyguestelecom_Facture_(\d{8})(?:-\d+)?\.pdf$", re.IGNORECASE)

BOUYGUES_BILLING_DAY = 27       # jourFacturation du compte (API Bouygues)
BOUYGUES_MAX_AGE = 45           # jours entre la facture et le prélèvement, au plus
BOUYGUES_DEBIT_DELAY = 5        # une facture n'est pas prélevée moins de 5 jours après
PRELEVE_RE = re.compile(r"Montant prélevé le (\d{1,2}) (\w+) (\d{4})\s+(-?[\d  .]*\d,\d{2})")

MONTHS = {name: index for index, name in enumerate(sources.MONTHS, 1)}


# --- Lecture des PDF ----------------------------------------------------------

def parse_free_invoice(text):
    """Total TTC d'une facture Freebox (« Total 24,99€ 29,99€ » : HT puis TTC)."""
    match = re.search(r"Total\s+[\d  .]*\d,\d{2}\s*€\s+([\d  .]*\d,\d{2})\s*€", text)
    return sources.amount_fr(match.group(1)) if match else None


def parse_bouygues_invoice(text):
    """(date, montant) de la ligne « Montant prélevé le 9 novembre 2026 17,99 »."""
    match = PRELEVE_RE.search(text)
    if not match or match.group(2).lower() not in MONTHS:
        return None, None
    when = date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
    return when, abs(sources.amount_fr(match.group(4)))


def debit_date(transaction):
    return datetime.strptime(sources.transaction_date(transaction), "%Y-%m-%d").date()


def expected_bouygues_date(debit):
    """Date de la facture Bouygues prélevée à `debit` : le dernier 27 au moins 5 jours avant."""
    limit = debit - timedelta(days=BOUYGUES_DEBIT_DELAY)
    candidate = limit.replace(day=BOUYGUES_BILLING_DAY) if limit.day >= BOUYGUES_BILLING_DAY else \
        (limit.replace(day=1) - timedelta(days=1)).replace(day=BOUYGUES_BILLING_DAY)
    return candidate


def fr_date(when):
    return when.strftime("%d/%m/%Y")


# --- Sites --------------------------------------------------------------------

class FreeBrowser(chrome.SiteBrowser):
    """Espace abonné Freebox (adsl.free.fr) : la page d'accueil liste toutes les factures."""

    name = "Free"
    home_url = FREE_HOME

    def _logged_in(self):
        url = self._page.url
        return "adsl.free.fr/" in url and "idt=" in url

    def _on_login_page(self):
        return "subscribe.free.fr" in self._page.url

    def invoice_links(self):
        """{n° de facture: (mois AAAAMM, lien absolu du PDF)}."""
        if not self._logged_in():
            self.open()
        url = urlparse(self._page.url)
        if not url.path.endswith("/home.pl"):          # la connexion peut arriver sur une autre page
            query = parse_qs(url.query)
            home = "https://adsl.free.fr/home.pl?" + urlencode(
                {k: query[k][0] for k in ("id", "idt") if k in query})
            self._page.goto(home, wait_until="domcontentloaded")
        try:
            self._page.wait_for_selector('a[href*="facture_pdf.pl"]', timeout=15000)
        except Exception:
            pass                                       # aucune facture : liste vide, décision
        hrefs = self._page.evaluate(
            "() => [...document.querySelectorAll('a[href*=\"facture_pdf.pl\"]')].map(a => a.href)")
        links = {}
        for href in hrefs:
            query = parse_qs(urlparse(href).query)
            number, month = query.get("no_facture", [""])[0], query.get("mois", [""])[0]
            if number:
                links[number] = (month, urljoin(self._page.url, href))
        return links

    def download(self, url, dest):
        response = self.context.request.get(url, timeout=60000)
        body = response.body()
        if not response.ok or not body.startswith(b"%PDF"):
            raise IOError(f"téléchargement refusé ({response.status})")
        with open(dest, "wb") as handle:
            handle.write(body)


class BouyguesBrowser(chrome.SiteBrowser):
    """
    Espace client Bouygues : la page « Mes factures » reçoit la liste par une
    requête GraphQL `GetInvoices`, qu'on lit au passage. Le jeton de l'API n'est
    jamais manipulé : le PDF se récupère en cliquant sur « Télécharger ».
    """

    name = "Bouygues"
    home_url = BOUYGUES_HOME

    def __init__(self, notify=print, session=None):
        super().__init__(notify, session)
        self._response = None
        self._watched = None

    def _watch(self):
        """Écoute toute la session (pas un seul onglet) : la connexion peut changer d'onglet."""
        context = self.context
        if self._watched is context:
            return

        def on_response(response):
            try:
                post = response.request.post_data or ""
            except Exception:
                post = ""
            if response.url.startswith("https://api.bouyguestelecom.fr/graphql") and "GetInvoices" in post:
                self._response = response
                try:
                    self._page = response.frame.page
                except Exception:
                    pass
        context.on("response", on_response)
        self._watched = context

    def _goto_home(self):
        self._response = None
        self._page = self.session.page(self.name)
        self._watch()
        self._page.goto(self.home_url, wait_until="domcontentloaded")
        self._settle()

    def _settle(self):
        for _ in range(30):                 # 15 s au plus : liste reçue ou page de connexion
            if self._response is not None or self._on_login_page():
                return
            self._page.wait_for_timeout(500)

    def _logged_in(self):
        return self._response is not None

    def _wait_login(self):
        """Comme le socle, mais « Mes factures » affichée sans liste reçue est rechargée toutes les 15 s."""
        stuck = 0
        while not self._logged_in():
            self._page.wait_for_timeout(2000)
            if self._logged_in():
                break
            path = urlparse(self._page.url)
            on_invoices = path.netloc == "www.bouyguestelecom.fr" and path.path.startswith("/mon-compte/mes-factures")
            stuck = stuck + 1 if on_invoices else 0
            if (not self._on_login_page() or stuck >= 8):
                stuck = 0
                try:
                    self._page.goto(self.home_url, wait_until="domcontentloaded")
                except Exception:
                    pass

    def _on_login_page(self):
        url = urlparse(self._page.url)
        if url.netloc != "www.bouyguestelecom.fr" or not url.path.startswith("/mon-compte"):
            return True                     # oauth2, code SMS…
        return url.path.startswith("/mon-compte/mes-factures") and self._response is None

    def invoices(self):
        """[{id, date (jour de facture, heure de Paris), amount}], plus récentes d'abord."""
        if self._response is None:
            self.open()
        data = self._response.json()
        accounts = data["data"]["consulterPersonne"]["factures"]["comptesFacturation"]
        result = []
        for account in accounts:
            for invoice in account.get("factures") or []:
                issued = datetime.strptime(invoice["dateFacturation"][:19], "%Y-%m-%dT%H:%M:%S")
                issued = issued.replace(tzinfo=timezone.utc).astimezone(PARIS).date()
                result.append({"id": str(invoice["id"]), "date": issued, "amount": float(invoice["mntTotFacture"])})
        return sorted(result, key=lambda i: i["date"], reverse=True)

    def download(self, invoice_id, folder):
        page = self._page
        if "/mon-compte/mes-factures" not in page.url:
            self.open()
            page = self._page
        row = page.locator("tr").filter(has=page.locator(f'a[href*="facture-detaillee/{invoice_id}"]')).first
        with page.expect_download(timeout=60000) as event:
            row.get_by_text("Télécharger", exact=True).first.click()
        download = event.value
        path = os.path.join(folder, download.suggested_filename or f"Bouyguestelecom_Facture_{invoice_id}.pdf")
        download.save_as(path)
        with open(path, "rb") as handle:
            if not handle.read(5).startswith(b"%PDF"):
                raise IOError("le fichier téléchargé n'est pas un PDF")
        return path


_browsers = {}


def site(cls):
    """Une session par site pour toutes les sociétés, ouverte au premier besoin."""
    if cls not in _browsers:
        _browsers[cls] = cls()
        _browsers[cls].open()
    return _browsers[cls]


def close_browsers():
    _browsers.clear()
    chrome.SESSION.close()


# --- Étapes ---------------------------------------------------------------------

class TelecomStep(sources.Step):
    """Ce qui est commun à Free et Bouygues : repérage par l'émetteur, contrôle F4, liens."""

    issuer = ""
    url = ""
    partial_title = "Justificatif {source} joint malgré un montant différent"

    def __init__(self, society, year, month, attach, report, ask=decision.ask, transactions=None,
                 invoices=None, download=None, names_of=None):
        super().__init__(society, year, month, attach, report, ask=ask, transactions=transactions)
        self._invoices_source = invoices
        self._download_source = download
        self.names_of = names_of or (lambda transaction: [])
        self._cache = None
        self._tmp = tempfile.mkdtemp(prefix=f"qonto-{self.source.lower()}-")
        self.checked_ok = 0
        self.checked_bad = 0

    def belongs(self, transaction):
        return self.issuer in sources.issuer(transaction)

    def select(self, transactions):
        return sources.split_by_period(transactions, self.year, self.month, self.belongs)

    def in_period_justified(self):
        return [t for t in self.transactions if self.belongs(t) and t.get("attachment_ids")
                and t.get("amount") and sources.transaction_month(t) == (self.year, self.month)]

    def has_activity(self):
        return bool(self.inside or self.outside or self.checked_ok or self.checked_bad)

    def extra_summary(self):
        text = ""
        if self.checked_ok:
            text += f" · {self.checked_ok} déjà justifiée(s) conforme(s)"
        if self.checked_bad:
            text += f" · {self.checked_bad} justificatif(s) à corriger"
        return text

    def link(self, transaction, found):
        return self.url

    def invoice_list(self, refresh=False):
        if refresh or self._cache is None:
            self._cache = self._invoices_source()
        return self._cache

    def find(self, transaction, refresh=False):
        try:
            return self.match(transaction, refresh)
        except Exception as e:  # site injoignable ou page changée : jamais au hasard
            self.report.error(f"Factures {self.source} illisibles",
                              f"{euros(transaction['amount'])} le {day(transaction)} ({type(e).__name__}: {e})")
            return {"kind": "none"}

    def item(self, transaction, found, reference):
        kind = found["kind"]
        amount = euros(transaction["amount"])
        if kind == "partial":
            cause = found.get("cause") or (
                f"Montant différent : facture de {euros(found['total']) if found.get('total') is not None else 'montant illisible'}"
                f" pour {amount} débités.")
            choices = [decision.ATTACH, decision.LEAVE]
        elif kind == "none":
            cause = found.get("cause") or f"Aucune facture {self.source} trouvée pour ce prélèvement."
            choices = [decision.LEAVE, decision.RETRY]
        else:
            cause = (f"Transaction {self.source} non reconnue : « {normalize(transaction.get('reference')) or 'vide'} »"
                     f" ({normalize(transaction.get('label'))}, {'crédit' if transaction.get('side') == 'credit' else 'débit'})."
                     " Impossible de retrouver la facture.")
            choices = [decision.LEAVE, decision.RETRY]
        return {
            "id": transaction["id"],
            "source": self.source,
            "amount": ("+" if transaction.get("side") == "credit" else "") + amount,
            "date": day(transaction),
            "ref": reference,
            "cause": cause,
            "severity": "partial" if kind == "partial" else "missing",
            "links": [{"href": self.url, "label": f"Voir mes factures {self.source}"}],
            "choices": choices,
        }

    def check_existing(self):
        for transaction in self.in_period_justified():
            try:
                names = self.names_of(transaction)
            except Exception as e:
                self.report.warning(f"Contrôle du justificatif {self.source} impossible",
                                    f"{euros(transaction['amount'])} le {day(transaction)} ({type(e).__name__}: {e})")
                continue
            problem = self.problem(transaction, names)
            if problem:
                self.checked_bad += 1
                self.report.warning(f"Justificatif {self.source} à corriger sur Qonto",
                                    f"{euros(transaction['amount'])} le {day(transaction)} : {problem}")
                print(f"Contrôle {self.source} : {euros(transaction['amount'])} le {day(transaction)} : {problem}")
            else:
                self.checked_ok += 1

    def problem(self, transaction, names):
        """Cause en clair si le justificatif joint est faux, sinon None."""
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            return f"{duplicates[0]} est joint {names.count(duplicates[0])} fois, supprime le doublon"
        return None


class FreeStep(TelecomStep):
    source = "Free"
    issuer = "FREE TELECOM"
    url = FREE_HOME

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._invoices_source is None:
            self._invoices_source = lambda: site(FreeBrowser).invoice_links()
        if self._download_source is None:
            self._download_source = lambda url, dest: site(FreeBrowser).download(url, dest)

    @staticmethod
    def number(transaction):
        if transaction.get("side") == "credit":
            return None
        match = FREE_REFERENCE_RE.match(normalize(transaction.get("reference")))
        return match.group(1) if match else None

    def match(self, transaction, refresh=False):
        number = self.number(transaction)
        if not number:
            return {"kind": "unknown"}
        links = self.invoice_list(refresh)
        if number not in links:
            return {"kind": "none", "number": number,
                    "cause": f"Aucune facture n° {number} dans l'espace abonné Free (pas encore émise ?)."}
        month, url = links[number]
        path = os.path.join(self._tmp, f"Facture_Free_{month}_{number}.pdf")
        self._download_source(url, path)
        total = parse_free_invoice(sources.pdf_text(path))
        kind = "ok" if same_amount(total, transaction["amount"]) else "partial"
        return {"kind": kind, "number": number, "file": path, "total": total}

    def decision_item(self, transaction, found):
        number = found.get("number") or self.number(transaction)
        return self.item(transaction, found, f"Facture n° {number}" if number else "Facture inconnue")

    def problem(self, transaction, names):
        duplicate = super().problem(transaction, names)
        if duplicate:
            return duplicate
        number = self.number(transaction)
        for name in names:
            match = FREE_FILE_RE.match(name)
            if match and number and match.group(3) != number:
                return f"{name} est joint, la facture attendue est la n° {number}"
        return None


class BouyguesStep(TelecomStep):
    source = "Bouygues"
    issuer = "BOUYGUES TELECOM"
    url = BOUYGUES_HOME

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._invoices_source is None:
            self._invoices_source = lambda: site(BouyguesBrowser).invoices()
        if self._download_source is None:
            self._download_source = lambda invoice_id, folder: site(BouyguesBrowser).download(invoice_id, folder)
        self._used = None
        self._claimed = set()

    def used_dates(self):
        """Factures déjà jointes à un prélèvement Bouygues : jamais proposées une 2e fois."""
        if self._used is None:
            self._used = set()
            for transaction in self.transactions:
                if self.belongs(transaction) and transaction.get("attachment_ids"):
                    try:
                        names = self.names_of(transaction)
                    except Exception:
                        continue
                    for name in names:
                        match = BOUYGUES_FILE_RE.match(name)
                        if match:
                            self._used.add(match.group(1))
        return self._used

    def match(self, transaction, refresh=False):
        if transaction.get("side") == "credit":
            return {"kind": "unknown"}
        debit = debit_date(transaction)
        used = self.used_dates()
        candidates = [i for i in self.invoice_list(refresh)
                      if debit - timedelta(days=BOUYGUES_MAX_AGE) <= i["date"] < debit
                      and i["date"].strftime("%Y%m%d") not in used and i["id"] not in self._claimed]
        if not candidates:
            return {"kind": "none",
                    "cause": f"Aucune facture Bouygues émise dans les {BOUYGUES_MAX_AGE} jours avant ce prélèvement."}
        equal = [i for i in candidates if same_amount(i["amount"], transaction["amount"])]
        invoice = max(equal or candidates, key=lambda i: i["date"])
        path = self._download_source(invoice["id"], self._tmp)
        found = {"kind": "ok" if equal else "partial", "invoice": invoice, "file": path, "total": invoice["amount"]}
        if not equal:
            return found
        when, amount = parse_bouygues_invoice(sources.pdf_text(path))
        if amount is not None and not same_amount(amount, transaction["amount"]):
            found.update(kind="partial", total=amount)
        elif when is not None and abs((when - debit).days) > BOUYGUES_DEBIT_DELAY:
            found.update(kind="partial", cause=(
                f"La facture du {fr_date(invoice['date'])} annonce un prélèvement le {fr_date(when)},"
                f" pas le {day(transaction)}."))
        return found

    def decision_item(self, transaction, found):
        invoice = found.get("invoice")
        reference = f"Facture du {fr_date(invoice['date'])}" if invoice else \
            f"Référence Qonto {normalize(transaction.get('reference')) or 'vide'}"
        return self.item(transaction, found, reference)

    def _attach(self, transaction, found):
        done = super()._attach(transaction, found)
        if done and found.get("invoice"):
            self._claimed.add(found["invoice"]["id"])
        return done

    def problem(self, transaction, names):
        duplicate = super().problem(transaction, names)
        if duplicate:
            return duplicate
        expected = expected_bouygues_date(debit_date(transaction))
        for name in names:
            match = BOUYGUES_FILE_RE.match(name)
            if match and match.group(1) != expected.strftime("%Y%m%d"):
                return (f"{name} est joint, la facture attendue est celle du {fr_date(expected)}"
                        f" (Bouyguestelecom_Facture_{expected.strftime('%Y%m%d')}.pdf)")
        return None
