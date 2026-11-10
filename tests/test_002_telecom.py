"""Spec 002 — justificatifs Bouygues Telecom et Free. Sites et Qonto simulés, données réelles d'adn dev."""

import io
import json
import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import amazon  # noqa: E402
import browser  # noqa: E402
import decision  # noqa: E402
import sources  # noqa: E402
import status  # noqa: E402
import telecom  # noqa: E402


def tx(id, amount, reference, label, day_, side="debit", attachments=None):
    return {"id": id, "amount": amount, "reference": reference, "label": label, "side": side,
            "clean_counterparty_name": label,
            "settled_at": day_ + "T10:00:00.000Z", "emitted_at": day_ + "T06:00:00.000Z",
            "attachment_ids": attachments or []}


def bt(id, amount, day_, attachments=None):
    return tx(id, amount, "06xxxxx055", "Bouygues  Telecom", day_, attachments=attachments)


def free(id, number, day_, amount=29.99, attachments=None):
    return tx(id, amount, f"Free HautDebit {number}", "Free  Telecom", day_, attachments=attachments)


# Les 13 factures Bouygues réelles (jour de facture, montant) et les 13 prélèvements.
BT_INVOICES = [("20251027", 17.99), ("20251127", 17.99), ("20251227", 17.99), ("20260127", 18.10),
               ("20260227", 17.99), ("20260327", 18.07), ("20260427", 17.99), ("20260527", 19.47),
               ("20260627", 17.99), ("20260727", 18.74), ("20260827", 17.99), ("20260927", 17.99),
               ("20261027", 17.99)]
BT_DEBITS = [("2025-11-10", 17.99, "20251027"), ("2025-12-08", 17.99, "20251127"), ("2026-01-08", 17.99, "20251227"),
             ("2026-02-09", 18.10, "20260127"), ("2026-03-09", 17.99, "20260227"), ("2026-04-09", 18.07, "20260327"),
             ("2026-05-07", 17.99, "20260427"), ("2026-06-09", 19.47, "20260527"), ("2026-07-09", 17.99, "20260627"),
             ("2026-08-07", 18.74, "20260727"), ("2026-09-09", 17.99, "20260827"), ("2026-10-09", 17.99, "20260927"),
             ("2026-11-09", 17.99, "20261027")]
MOIS = {m: i for i, m in enumerate(sources.MONTHS, 1)}


def invoice(day_, amount):
    return {"id": "ID" + day_, "date": date(int(day_[:4]), int(day_[4:6]), int(day_[6:])), "amount": amount}


def bouygues_pdf(when, amount):
    return (f"Date de facture …\nBonjour, voici votre facture\nMontant prélevé le {when.day} "
            f"{sources.MONTHS[when.month - 1]} {when.year} {amount:.2f}".replace(".", ",")
            + "\nTout est bien rangé\nMontant prélevé le 23 avril 2021 11,49")


FREE_PDF = "Facture Freebox\nServices de Free 24,99€\nHT TTC\n29,99€\nTotal 24,99€ 29,99€\nDont TVA 20%: 5,00€"


class FakeAsk:
    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.asked = []

    def __call__(self, society, period, items):
        self.asked.append(items)
        return self.rounds.pop(0) if self.rounds else {}


class Base(unittest.TestCase):
    def setUp(self):
        self.attached = []
        self.report = status.Report("adn-dev")
        self.pdf = {}

    def attach(self, transaction, path, name):
        self.attached.append((transaction["id"], name))
        return True

    def fake_pdf_text(self, path):
        return self.pdf.get(os.path.basename(path), "")

    def run_steps(self, steps, ask=None):
        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sources.pdf_text", self.fake_pdf_text):
            sources.run_steps("adn-dev", "test", steps, ask or FakeAsk())
        self.output = out.getvalue()
        return steps

    def bouygues(self, transactions, year, month, invoices=None, ask=None, names=None, pdf_dates=None):
        invoices = invoices if invoices is not None else [invoice(d, a) for d, a in BT_INVOICES]

        def download(invoice_id, folder):
            name = f"Bouyguestelecom_Facture_{invoice_id[2:]}.pdf"
            inv = next(i for i in invoices if i["id"] == invoice_id)
            when = (pdf_dates or {}).get(invoice_id[2:])
            if when is None:
                debit = next((d for d, _, f in BT_DEBITS if f == invoice_id[2:]), None)
                when = date.fromisoformat(debit) if debit else inv["date"]
            self.pdf[name] = bouygues_pdf(when, inv["amount"])
            return os.path.join(folder, name)
        step = telecom.BouyguesStep("adn-dev", year, month, self.attach, self.report, ask=ask or FakeAsk(),
                                    transactions=transactions, invoices=lambda: invoices, download=download,
                                    names_of=lambda t: (names or {}).get(t["id"], []))
        return step

    def free(self, transactions, year, month, links=None, ask=None, names=None, pdf=FREE_PDF):
        links = links if links is not None else {"1510870586": ("202611", "u1"), "1503236843": ("202610", "u2")}

        def download(url, dest):
            self.pdf[os.path.basename(dest)] = pdf
        return telecom.FreeStep("adn-dev", year, month, self.attach, self.report, ask=ask or FakeAsk(),
                                transactions=transactions, invoices=lambda: links, download=download,
                                names_of=lambda t: (names or {}).get(t["id"], []))


class F1Reperage(Base):
    def test_libelles_reels_avec_espaces_doubles(self):
        step = self.free([], 2026, 11)
        self.assertTrue(step.belongs(free("f", "1", "2026-11-05")))
        self.assertTrue(self.bouygues([], 2026, 11).belongs(bt("b", 17.99, "2026-11-09")))
        self.assertFalse(step.belongs(tx("m", 9.99, "x", "FREE MOBILE", "2026-11-05")))
        self.assertFalse(step.belongs(tx("a", 9.99, "x", "AMAZON PAYMENTS", "2026-11-05")))

    def test_forme_inconnue_part_en_decision_jamais_ignoree(self):
        ask = FakeAsk({})
        odd = tx("x", 29.99, "Free Option 42", "Free Telecom", "2026-11-05")
        refund = tx("r", 5.0, "Free HautDebit 1510870586", "Free Telecom", "2026-11-06", side="credit")
        step = self.free([odd, refund], 2026, 11, ask=ask)
        self.run_steps([step], ask)
        items = {i["id"]: i for i in ask.asked[0]}
        self.assertIn("non reconnue", items["x"]["cause"])
        self.assertIn("crédit", items["r"]["cause"])
        self.assertEqual(items["x"]["choices"], [decision.LEAVE, decision.RETRY])
        self.assertEqual(step.left_ids, {"x", "r"})

    def test_hors_periode_signale_et_justifiee_ignoree(self):
        ask = FakeAsk()
        step = self.free([free("o", "1503236843", "2026-10-06"),
                          free("j", "1510870586", "2026-11-05", attachments=["a"])], 2026, 11, ask=ask)
        self.run_steps([step], ask)
        self.assertEqual(self.attached, [])
        self.assertEqual(ask.asked, [])
        self.assertTrue(any("hors période" in w and "octobre 2026" in w for w in self.report.warnings))


class F2Free(Base):
    def test_numero_trouve_et_montant_egal_joint_sans_rien_demander(self):
        ask = FakeAsk()
        self.run_steps([self.free([free("f", "1510870586", "2026-11-05")], 2026, 11, ask=ask)], ask)
        self.assertEqual(self.attached, [("f", "Facture_Free_202611_1510870586.pdf")])
        self.assertEqual(ask.asked, [])

    def test_numero_absent_decision_laisser_ou_reessayer(self):
        ask = FakeAsk({})
        self.run_steps([self.free([free("f", "999", "2026-11-05")], 2026, 11, ask=ask)], ask)
        item = ask.asked[0][0]
        self.assertEqual(item["source"], "Free")
        self.assertIn("n° 999", item["cause"])
        self.assertEqual(item["choices"], [decision.LEAVE, decision.RETRY])
        self.assertEqual(item["links"][0]["href"], telecom.FREE_HOME)
        self.assertTrue(any("Transaction Free sans justificatif" in w for w in self.report.warnings))

    def test_montant_different_demande_B4(self):
        ask = FakeAsk({"f": decision.ATTACH})
        pdf = FREE_PDF.replace("Total 24,99€ 29,99€", "Total 29,99€ 35,99€")
        self.run_steps([self.free([free("f", "1510870586", "2026-11-05")], 2026, 11, ask=ask, pdf=pdf)], ask)
        item = ask.asked[0][0]
        self.assertIn("35,99 €", item["cause"])
        self.assertEqual(item["choices"], [decision.ATTACH, decision.LEAVE])
        self.assertEqual(len(self.attached), 1)
        self.assertTrue(any("joint malgré un montant différent" in w for w in self.report.warnings))

    def test_reessayer_relance_la_liste(self):
        calls = {"n": 0}

        def links():
            calls["n"] += 1
            return {} if calls["n"] == 1 else {"1510870586": ("202611", "u")}
        ask = FakeAsk({"f": decision.RETRY})
        step = self.free([free("f", "1510870586", "2026-11-05")], 2026, 11, ask=ask)
        step._invoices_source = links
        self.run_steps([step], ask)
        self.assertEqual(len(self.attached), 1)

    def test_site_illisible_rouge_sans_joindre(self):
        def broken():
            raise IOError("page changée")
        ask = FakeAsk({})
        step = self.free([free("f", "1510870586", "2026-11-05")], 2026, 11, ask=ask)
        step._invoices_source = broken
        self.run_steps([step], ask)
        self.assertEqual(self.attached, [])
        self.assertEqual(self.report.level, status.Level.ERROR)


class F2Bouygues(Base):
    def test_les_13_prelevements_reels_trouvent_leur_facture(self):
        for debit, amount, expected in BT_DEBITS:
            with self.subTest(debit=debit):
                self.attached = []
                ask = FakeAsk()
                y, m = int(debit[:4]), int(debit[5:7])
                self.run_steps([self.bouygues([bt("b", amount, debit)], y, m, ask=ask)], ask)
                self.assertEqual(self.attached, [("b", f"Bouyguestelecom_Facture_{expected}.pdf")])
                self.assertEqual(ask.asked, [])

    def test_mai_2026_jamais_la_facture_de_mai(self):
        """L'erreur commise à la main : le 07/05 porte la facture du 27/04, pas du 27/05."""
        self.run_steps([self.bouygues([bt("b", 17.99, "2026-05-07")], 2026, 5)])
        self.assertEqual(self.attached, [("b", "Bouyguestelecom_Facture_20260427.pdf")])

    def test_facture_deja_jointe_jamais_reproposee(self):
        other = bt("avril", 18.07, "2026-04-09", attachments=["x"])
        ask = FakeAsk({})
        step = self.bouygues([other, bt("b", 17.99, "2026-05-07")], 2026, 5, ask=ask,
                             names={"avril": ["Bouyguestelecom_Facture_20260427.pdf"]})
        self.run_steps([step], ask)
        self.assertEqual(self.attached, [])
        self.assertNotIn("27/04/2026", ask.asked[0][0]["ref"])

    def test_meme_facture_jamais_jointe_deux_fois_dans_un_traitement(self):
        ask = FakeAsk({})
        twice = [bt("b1", 17.99, "2026-11-09"), bt("b2", 17.99, "2026-11-10")]
        self.run_steps([self.bouygues(twice, 2026, 11, ask=ask)], ask)
        self.assertEqual([a[1] for a in self.attached], ["Bouyguestelecom_Facture_20261027.pdf"])
        self.assertEqual(len(ask.asked[0]), 1)

    def test_montant_sans_facture_decision(self):
        ask = FakeAsk({"b": decision.LEAVE})
        self.run_steps([self.bouygues([bt("b", 23.49, "2026-11-09")], 2026, 11, ask=ask)], ask)
        item = ask.asked[0][0]
        self.assertEqual(item["source"], "Bouygues")
        self.assertEqual(item["ref"], "Facture du 27/10/2026")
        self.assertIn("17,99 €", item["cause"])
        self.assertEqual(item["choices"], [decision.ATTACH, decision.LEAVE])
        self.assertEqual(self.attached, [])

    def test_aucune_facture_avant_le_prelevement(self):
        ask = FakeAsk({})
        self.run_steps([self.bouygues([bt("b", 17.99, "2026-11-09")], 2026, 11, invoices=[], ask=ask)], ask)
        self.assertEqual(ask.asked[0][0]["choices"], [decision.LEAVE, decision.RETRY])

    def test_pdf_annonce_une_autre_date_de_prelevement(self):
        ask = FakeAsk({})
        step = self.bouygues([bt("b", 17.99, "2026-11-09")], 2026, 11, ask=ask,
                             pdf_dates={"20261027": date(2026, 12, 9)})
        self.run_steps([step], ask)
        self.assertIn("annonce un prélèvement le 09/12/2026", ask.asked[0][0]["cause"])

    def test_lecture_des_pdf_reels(self):
        when, amount = telecom.parse_bouygues_invoice(bouygues_pdf(date(2026, 11, 9), 17.99))
        self.assertEqual((when, amount), (date(2026, 11, 9), 17.99))
        self.assertEqual(telecom.parse_free_invoice(FREE_PDF), 29.99)
        self.assertEqual(telecom.parse_bouygues_invoice("rien"), (None, None))
        self.assertIsNone(telecom.parse_free_invoice("rien"))


class F4Controle(Base):
    def control(self, step_factory, transactions, names, year, month):
        step = step_factory(transactions, year, month, names=names)
        self.run_steps([step])
        return step

    def test_mai_2026_mauvaise_facture_signalee(self):
        step = self.control(self.bouygues, [bt("b", 17.99, "2026-05-07", attachments=["x"])],
                            {"b": ["Bouyguestelecom_Facture_20260527.pdf"]}, 2026, 5)
        self.assertEqual(step.checked_bad, 1)
        self.assertTrue(any("Bouyguestelecom_Facture_20260527.pdf est joint" in w and "27/04/2026" in w
                            for w in self.report.warnings))
        self.assertEqual(self.report.level, status.Level.WARN)

    def test_avril_2026_doublon_signale(self):
        self.control(self.bouygues, [bt("b", 18.07, "2026-04-09", attachments=["x", "y"])],
                     {"b": ["Bouyguestelecom_Facture_20260327.pdf"] * 2}, 2026, 4)
        self.assertTrue(any("joint 2 fois" in w for w in self.report.warnings))

    def test_nom_renomme_non_verifiable_et_octobre_conforme(self):
        step = self.control(self.free, [free("f", "1450073852", "2026-03-05", attachments=["x"])],
                            {"f": ["Mars_2026.pdf"]}, 2026, 3)
        self.assertEqual(self.report.warnings, [])
        self.assertEqual(step.checked_ok, 1)
        step = self.control(self.bouygues, [bt("b", 17.99, "2026-10-09", attachments=["x"])],
                            {"b": ["Bouyguestelecom_Facture_20260927.pdf"]}, 2026, 10)
        self.assertEqual(self.report.warnings, [])
        self.assertIn("1 déjà justifiée(s) conforme(s)", self.output)

    def test_free_mauvais_numero_et_copie_suffixee(self):
        self.control(self.free, [free("f", "1427300238", "2025-12-05", attachments=["x"])],
                     {"f": ["Facture_Free_202512_24442322_1427300238-2.pdf"]}, 2025, 12)
        self.assertEqual(self.report.warnings, [])
        self.control(self.free, [free("g", "1503236843", "2026-10-06", attachments=["x"])],
                     {"g": ["Facture_Free_202609_24442322_1495635414.pdf"]}, 2026, 10)
        self.assertTrue(any("la facture attendue est la n° 1503236843" in w for w in self.report.warnings))

    def test_controle_ne_modifie_rien(self):
        self.control(self.bouygues, [bt("b", 17.99, "2026-05-07", attachments=["x"])],
                     {"b": ["Bouyguestelecom_Facture_20260527.pdf"]}, 2026, 5)
        self.assertEqual(self.attached, [])

    def test_date_attendue_des_douze_prelevements(self):
        for debit, _, expected in BT_DEBITS:
            self.assertEqual(telecom.expected_bouygues_date(date.fromisoformat(debit)).strftime("%Y%m%d"),
                             expected, debit)


class F5Sessions(Base):
    def test_aucun_navigateur_si_rien_a_traiter(self):
        transactions = [bt("b", 17.99, "2026-10-09", attachments=["x"]),
                        free("f", "1503236843", "2026-10-06", attachments=["y"])]
        with mock.patch("telecom.site", side_effect=AssertionError("navigateur ouvert")):
            steps = [telecom.BouyguesStep("adn-dev", 2026, 10, self.attach, self.report, transactions=transactions),
                     telecom.FreeStep("adn-dev", 2026, 10, self.attach, self.report, transactions=transactions)]
            self.run_steps(steps)
        self.assertEqual(self.report.errors, [])

    def test_profil_amazon_renomme_une_fois(self):
        import tempfile
        root = tempfile.mkdtemp()
        legacy, profile = os.path.join(root, "amazon-profile"), os.path.join(root, "browser-profile")
        os.mkdir(legacy)
        open(os.path.join(legacy, "Cookies"), "w").close()
        browser.migrate_profile(profile, legacy)
        self.assertTrue(os.path.exists(os.path.join(profile, "Cookies")))
        self.assertFalse(os.path.exists(legacy))
        browser.migrate_profile(profile, legacy)    # deuxième fois : rien ne bouge
        self.assertTrue(os.path.isdir(profile))

    def test_detection_de_connexion(self):
        class Page:
            url = ""
        free_site = telecom.FreeBrowser(notify=lambda *_: None)
        free_site._page = Page()
        for url, logged, login in [("https://subscribe.free.fr/login/", False, True),
                                   ("https://adsl.free.fr/home.pl?idt=abc&id=1", True, False)]:
            free_site._page.url = url
            self.assertEqual((free_site._logged_in(), free_site._on_login_page()), (logged, login), url)
        bouygues = telecom.BouyguesBrowser(notify=lambda *_: None)
        bouygues._page = Page()
        bouygues._page.url = "https://oauth2.bouyguestelecom.fr/connexion"
        self.assertTrue(bouygues._on_login_page())
        bouygues._page.url = "https://www.bouyguestelecom.fr/mon-compte/dashboard"
        self.assertFalse(bouygues._on_login_page())
        bouygues._response = object()
        bouygues._page.url = "https://www.bouyguestelecom.fr/mon-compte/mes-factures"
        self.assertTrue(bouygues._logged_in())
        self.assertFalse(bouygues._on_login_page())

    def test_free_lit_la_liste_depuis_l_accueil_une_fois_chargee(self):
        """Connexion arrivée sur une autre page : on ouvre home.pl et on attend les liens."""
        link = "https://adsl.free.fr/facture_pdf.pl?id=1&idt=abc&mois=202611&no_facture=1510870586"

        class Page:
            url = "https://adsl.free.fr/compte.pl?id=1&idt=abc"
            visited, waited = [], []

            def goto(self, url, **_):
                self.visited.append(url)
                self.url = url

            def wait_for_selector(self, selector, **_):
                self.waited.append(selector)

            def evaluate(self, _script):
                return [link] if self.url.endswith("home.pl?id=1&idt=abc") and self.waited else []

        site_ = telecom.FreeBrowser(notify=lambda *_: None)
        site_._page = Page()
        self.assertEqual(site_.invoice_links(), {"1510870586": ("202611", link)})
        self.assertEqual(site_._page.visited, ["https://adsl.free.fr/home.pl?id=1&idt=abc"])

    def test_bouygues_ecoute_toute_la_session_et_recharge_si_bloque(self):
        class Request:
            post_data = '{"operationName":"GetInvoices"}'

        class Response:
            url = "https://api.bouyguestelecom.fr/graphql"
            request = Request()

        class Page:
            url = "https://www.bouyguestelecom.fr/mon-compte/mes-factures"

            def __init__(self):
                self.reloads = 0

            def wait_for_timeout(self, _ms):
                if self.reloads == 1:                 # la liste n'arrive qu'après un rechargement
                    other = Page()
                    Response.frame = type("Frame", (), {"page": other})()
                    context.handlers[0](Response())

            def goto(self, url, **_):
                self.reloads += 1

        class Context:
            handlers = []

            def on(self, event, handler):
                self.handlers.append(handler)

        context = Context()
        session = type("Session", (), {"context": context})()
        bouygues = telecom.BouyguesBrowser(notify=lambda *_: None, session=session)
        first = bouygues._page = Page()
        bouygues._watch()
        bouygues._watch()                             # une seule écoute par session
        self.assertEqual(len(context.handlers), 1)
        bouygues._wait_login()
        self.assertEqual(first.reloads, 1)            # « Mes factures » sans liste : rechargée
        self.assertTrue(bouygues._logged_in())
        self.assertIsNot(bouygues._page, first)
        self.assertEqual(bouygues._page.reloads, 0)   # l'onglet retenu est celui qui a reçu la liste


class F6Interface(Base):
    def test_une_seule_carte_pour_amazon_et_bouygues(self):
        ask = FakeAsk({})
        amz = amazon.AmazonStep("adn-dev", 2026, 11, self.attach, self.report, ask=ask,
                                invoices_for_order=lambda order: [],
                                transactions=[tx("a", 8.99, "406-5893060-4448314 AMZN Mktp FR 5SC0HUQNCTU0ODQ4",
                                                 "AMAZON PAYMENTS", "2026-11-03")])
        bouy = self.bouygues([bt("b", 23.49, "2026-11-09")], 2026, 11, ask=ask)
        self.run_steps([amz, bouy], ask)
        self.assertEqual(len(ask.asked), 1)
        self.assertEqual({i["source"] for i in ask.asked[0]}, {"Amazon", "Bouygues"})
        lines = [json.loads(l[len(decision.AMAZON_PREFIX):]) for l in self.output.splitlines()
                 if l.startswith(decision.AMAZON_PREFIX)]
        self.assertEqual({l["source"] for l in lines}, {"Amazon", "Bouygues"})
        self.assertEqual(amz.left_ids, {"a"})
        self.assertEqual(bouy.left_ids, {"b"})
        # L'information Amazon reste entière : lien de commande et avertissement.
        self.assertTrue(any("Transaction Amazon sans justificatif" in w and "orderID=406-5893060-4448314" in w
                            for w in self.report.warnings))

    def test_source_sans_transaction_ne_publie_pas_de_ligne(self):
        self.run_steps([self.free([], 2026, 11)])
        self.assertNotIn(decision.AMAZON_PREFIX, self.output)

    def test_lanceur_garde_la_ligne_amazon_et_ajoute_les_sources(self):
        import gui_launcher
        manager = gui_launcher.ScriptManager()
        manager._consume(decision.AMAZON_PREFIX + json.dumps({"society": "adn-dev", "text": "2 jointe(s)"}))
        manager._consume(decision.AMAZON_PREFIX + json.dumps({"society": "adn-dev", "source": "Free", "text": "1 jointe(s)"}))
        self.assertEqual(manager.get_amazon(), {"adn-dev": "2 jointe(s)"})
        self.assertEqual(manager.get_sources(), {"adn-dev": {"Amazon": "2 jointe(s)", "Free": "1 jointe(s)"}})
        self.assertEqual(gui_launcher._describe([{"source": "Amazon"}] * 2), "2 transaction(s) Amazon")
        self.assertEqual(gui_launcher._describe([{"source": "Amazon"}, {"source": "Bouygues"}]),
                         "2 transaction(s) (1 Amazon, 1 Bouygues)")
        self.assertEqual(gui_launcher._describe([{"id": "x"}]), "1 transaction(s) Amazon")


if __name__ == "__main__":
    unittest.main()
