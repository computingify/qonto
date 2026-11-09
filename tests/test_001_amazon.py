"""Spec 001 — justificatifs Amazon et choix du mois. Amazon et Qonto sont simulés."""

import io
import json
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import amazon  # noqa: E402
import decision  # noqa: E402
import status  # noqa: E402


def tx(id, amount, reference, label="AMAZON PAYMENTS EUROPE S  C  A", date="2026-10-13", side="debit", attachments=None):
    return {"id": id, "amount": amount, "reference": reference, "label": label, "side": side,
            "settled_at": date + "T10:00:00.000Z", "emitted_at": date + "T09:00:00.000Z",
            "attachment_ids": attachments or []}


# Formes réelles relevées sur 12 mois (3 sociétés).
MKTP = tx("m", 8.99, "406-5893060-4448314 AMZN Mktp FR 5SC0HUQNCTU0ODQ4")
MKTP_DOUBLE = tx("md", 8.09, "406-3032937-4053111 AMZN Mktp FR 140LN3T8H06WZ9XT",
                 label="AMAZON PAYMENTS EUROPE S  C  A AMAZON PAYMENTS EUROPE S C A")
AMAZON_FR = tx("fr", 18.17, "406-2555871-1764332 Amazon.fr 3IQFCNC1C4IMRRNW",
               label="AMAZON EU SARL, SUCCURSALE FRANCAIS AMAZON EU SARL, SUCCURSALE F")
PRIME = tx("pr", 69.9, "D01-6046630-7538252 Amazon Prime FR 2B4XQ9WZ1L0P",
           label="AMAZON EU SARL, SUCCURSALE FRANCAIS AMAZON EU SARL, SUCCURSALE F")
NO_REF = tx("nr", 31.73, "", label="AMAZON PAYMENTS")
REFUND = tx("rf", 371.0, "406-1111111-2222222 AMZN Mktp FR 7ABCDEFGHIJKLMNO", side="credit")
OTHER = tx("o", 12.0, "FACT-2026-10", label="Google Cloud France SARL")


class F1Filtrage(unittest.TestCase):
    def test_les_cinq_formes_sont_reconnues(self):
        for transaction in (MKTP, MKTP_DOUBLE, AMAZON_FR, PRIME, NO_REF, REFUND):
            self.assertTrue(amazon.is_amazon(transaction), transaction["id"])
        self.assertFalse(amazon.is_amazon(OTHER))

    def test_reconnue_par_la_reference_meme_sans_libelle_amazon(self):
        self.assertTrue(amazon.is_amazon(tx("x", 5, "406-5893060-4448314 AMZN Mktp FR ABCDEFGHIJ12", label="CB")))

    def test_analyse_de_la_reference(self):
        self.assertEqual(amazon.parse_reference(MKTP["reference"]),
                         ("406-5893060-4448314", "AMZN Mktp FR", "5SC0HUQNCTU0ODQ4"))
        self.assertEqual(amazon.parse_reference("406-2555871-1764332  Amazon.fr   3IQFCNC1C4IMRRNW")[1], "Amazon.fr")
        self.assertEqual(amazon.parse_reference(PRIME["reference"])[0], "D01-6046630-7538252")
        self.assertIsNone(amazon.parse_reference(""))
        self.assertIsNone(amazon.parse_reference("AMZN Digital 12345"))

    def test_tri_dans_et_hors_periode_et_deja_justifiee_ignoree(self):
        nov = tx("n", 33.45, "406-8138195-3514724 AMZN Mktp FR 38F0UUP92G71BSC5", date="2026-11-09")
        done = tx("d", 7.99, "406-3588962-5232324 AMZN Mktp FR 6V5BPGK9F3XDBR4Y", attachments=["a1"])
        inside, outside = amazon.split_by_period([MKTP, nov, done, OTHER], 2026, 10)
        self.assertEqual([t["id"] for t in inside], ["m"])
        self.assertEqual([t["id"] for t in outside], ["n"])

    def test_la_date_de_reglement_fait_foi_comme_pour_le_zip(self):
        t = tx("b", 5, MKTP["reference"], date="2026-11-01")
        t["emitted_at"] = "2026-10-31T23:00:00.000Z"
        self.assertEqual(amazon.transaction_month(t), (2026, 11))


INVOICE_TEXT = """Facture
Payé
Référence de paiement 1JTXNXF887QYEJWP
Numéro de la facture FR64031GBAEUD
Total à payer 8,99 €
1 7,49 € 20 % 8,99 € 8,99 €
Facture Total 8,99 €
"""


class LecturePdf(unittest.TestCase):
    def test_reference_et_total_dune_facture(self):
        self.assertEqual(amazon.parse_invoice(INVOICE_TEXT), ("1JTXNXF887QYEJWP", 8.99))

    def test_avoir_et_milliers(self):
        text = "Avoir\nRéférence de paiement 7ABCDEFGHIJKLMNO\nAvoir Total -1 371,00 €\n"
        self.assertEqual(amazon.parse_invoice(text), ("7ABCDEFGHIJKLMNO", 1371.0))

    def test_texte_illisible(self):
        self.assertEqual(amazon.parse_invoice("rien"), (None, None))


# Commande réelle 406-8138195-3514724 : 5 débits, 5 factures.
ORDER = "406-8138195-3514724"
INVOICES = {ORDER: [("f1.pdf", "1JTXNXF887QYEJWP", 8.99), ("f2.pdf", "5DZKZQZ3BPJ8RQ11", 17.31),
                    ("f3.pdf", "38F0UUP92G71BSC5", 15.98), ("f4.pdf", "6GQ39QNGM0UMRIZ5", 8.89),
                    ("f5.pdf", "5N586SQDH5569M8T", 6.99)]}


def debit(id, amount, payref, date="2026-10-13"):
    return tx(id, amount, f"{ORDER} AMZN Mktp FR {payref}", date=date)


class F2Association(unittest.TestCase):
    def find(self, transaction, invoices=INVOICES):
        return amazon.find_invoice(transaction, lambda order: invoices.get(order, []))

    def test_plusieurs_factures_et_debits_dune_meme_commande(self):
        self.assertEqual(self.find(debit("a", 17.31, "5DZKZQZ3BPJ8RQ11"))["file"], "f2.pdf")
        self.assertEqual(self.find(debit("b", 8.89, "6GQ39QNGM0UMRIZ5"))["file"], "f4.pdf")

    def test_montant_identique_donne_ok(self):
        self.assertEqual(self.find(debit("a", 17.31, "5DZKZQZ3BPJ8RQ11"))["kind"], "ok")

    def test_montant_different_donne_partielle(self):
        found = self.find(debit("c", 74.03, "1JTXNXF887QYEJWP"))
        self.assertEqual((found["kind"], found["file"], found["total"]), ("partial", "f1.pdf", 8.99))

    def test_reference_insensible_a_la_casse(self):
        self.assertEqual(self.find(debit("a", 17.31, "5dzkzqz3bpj8rq11"))["kind"], "ok")

    def test_aucune_facture_reference_absente_reference_inconnue(self):
        self.assertEqual(self.find(tx("z", 28.49, "406-3534079-4184350 AMZN Mktp FR AAAABBBBCCCC"))["kind"], "none")
        self.assertEqual(self.find(debit("y", 5, "ZZZZZZZZZZZZ"))["kind"], "noref")
        self.assertEqual(self.find(NO_REF)["kind"], "unknown")


class FakeAsk:
    """Répond aux décisions selon un scénario et garde ce qui a été demandé."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.asked = []

    def __call__(self, society, period, items):
        self.asked.append(items)
        return self.rounds.pop(0) if self.rounds else {}


class F3Etape(unittest.TestCase):
    def step(self, transactions, ask, invoices=INVOICES, attach_ok=True):
        self.attached = []

        def attach(transaction, path, name):
            self.attached.append((transaction["id"], path))
            return attach_ok
        self.report = status.Report("adn-dev")
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            step = amazon.AmazonStep("adn-dev", 2026, 10, attach, self.report,
                                     invoices_for_order=lambda order: invoices.get(order, []),
                                     ask=ask, transactions=transactions)
            step.run()
        self.output = out.getvalue()
        return step

    def test_montant_identique_joint_sans_rien_demander(self):
        ask = FakeAsk()
        self.step([debit("a", 17.31, "5DZKZQZ3BPJ8RQ11")], ask)
        self.assertEqual(self.attached, [("a", "f2.pdf")])
        self.assertEqual(ask.asked, [])

    def test_decision_regroupee_avec_date_montant_cause_et_liens(self):
        ask = FakeAsk({"c": decision.ATTACH, "z": decision.LEAVE})
        transactions = [debit("c", 74.03, "1JTXNXF887QYEJWP"),
                        tx("z", 28.49, "406-3534079-4184350 AMZN Mktp FR AAAABBBBCCCC", date="2026-10-23")]
        step = self.step(transactions, ask)
        self.assertEqual(len(ask.asked), 1)
        items = {i["id"]: i for i in ask.asked[0]}
        self.assertEqual(items["c"]["amount"], "74,03 €")
        self.assertEqual(items["c"]["date"], "13/10/2026")
        self.assertIn("8,99 €", items["c"]["cause"])
        self.assertEqual(items["c"]["choices"], [decision.ATTACH, decision.LEAVE])
        self.assertIn("order-details?orderID=" + ORDER, items["c"]["orderUrl"])
        self.assertIn("contact.html?orderID=406-3534079-4184350", items["z"]["askUrl"])
        self.assertEqual(items["z"]["choices"], [decision.LEAVE, decision.RETRY])
        self.assertEqual(self.attached, [("c", "f1.pdf")])
        self.assertEqual(step.left_ids, {"z"})
        self.assertTrue(any("partiel" in w for w in self.report.warnings))
        self.assertTrue(any("sans justificatif" in w and "406-3534079-4184350" in w for w in self.report.warnings))

    def test_ecart_cheque_cadeau_demande_quand_meme(self):
        invoices = {"406-2555871-1764332": [("g.pdf", "3IQFCNC1C4IMRRNW", 28.71)]}
        ask = FakeAsk({"fr": decision.LEAVE})
        t = dict(AMAZON_FR, settled_at="2026-10-16T10:00:00.000Z")
        self.step([t], ask, invoices=invoices)
        self.assertEqual(len(ask.asked), 1)
        self.assertIn("chèque-cadeau", ask.asked[0][0]["cause"])
        self.assertEqual(self.attached, [])

    def test_reessayer_relance_la_recherche(self):
        state = {"calls": 0}

        def invoices_for_order(order):
            state["calls"] += 1
            return [] if state["calls"] == 1 else [("new.pdf", "AAAABBBBCCCC", 28.49)]
        ask = FakeAsk({"z": decision.RETRY})
        self.attached = []
        report = status.Report("adn-dev")
        with mock.patch("sys.stdout", io.StringIO()):
            amazon.AmazonStep("adn-dev", 2026, 10, lambda t, p, n: self.attached.append((t["id"], p)) or True,
                              report, invoices_for_order=invoices_for_order, ask=ask,
                              transactions=[tx("z", 28.49, "406-3534079-4184350 AMZN Mktp FR AAAABBBBCCCC")]).run()
        self.assertEqual(self.attached, [("z", "new.pdf")])
        self.assertEqual(len(ask.asked), 1)

    def test_reponse_absente_ne_joint_rien(self):
        ask = FakeAsk({})
        step = self.step([debit("c", 74.03, "1JTXNXF887QYEJWP")], ask)
        self.assertEqual(self.attached, [])
        self.assertEqual(step.left_ids, {"c"})

    def test_hors_periode_signale_seulement(self):
        ask = FakeAsk()
        nov = debit("n", 33.45, "38F0UUP92G71BSC5", date="2026-11-09")
        self.step([nov], ask)
        self.assertEqual(self.attached, [])
        self.assertEqual(ask.asked, [])
        self.assertTrue(any("hors période" in w and "novembre 2026" in w for w in self.report.warnings))

    def test_deja_justifiee_jamais_touchee(self):
        ask = FakeAsk()
        self.step([dict(debit("a", 17.31, "5DZKZQZ3BPJ8RQ11"), attachment_ids=["x"])], ask)
        self.assertEqual(self.attached, [])

    def test_remboursement_traite_comme_une_facture(self):
        invoices = {"406-1111111-2222222": [("avoir.pdf", "7ABCDEFGHIJKLMNO", 371.0)]}
        self.step([dict(REFUND, settled_at="2026-10-05T10:00:00.000Z")], FakeAsk(), invoices=invoices)
        self.assertEqual(self.attached, [("rf", "avoir.pdf")])

    def test_amazon_illisible_passe_en_rouge_sans_joindre(self):
        def broken(order):
            raise IOError("page changée")
        ask = FakeAsk({})
        self.attached = []
        report = status.Report("adn-dev")
        with mock.patch("sys.stdout", io.StringIO()):
            amazon.AmazonStep("adn-dev", 2026, 10, lambda *a: self.attached.append(a) or True, report,
                              invoices_for_order=broken, ask=ask,
                              transactions=[debit("a", 17.31, "5DZKZQZ3BPJ8RQ11")]).run()
        self.assertEqual(self.attached, [])
        self.assertEqual(report.level, status.Level.ERROR)

    def test_ligne_amazon_publiee_pour_linterface(self):
        self.step([debit("a", 17.31, "5DZKZQZ3BPJ8RQ11")], FakeAsk())
        lines = [l for l in self.output.splitlines() if l.startswith(decision.AMAZON_PREFIX)]
        self.assertIn("1 jointe(s)", json.loads(lines[-1][len(decision.AMAZON_PREFIX):])["text"])


class ProtocoleDecision(unittest.TestCase):
    ITEMS = [{"id": "a", "choices": [decision.ATTACH, decision.LEAVE]},
             {"id": "b", "choices": [decision.LEAVE, decision.RETRY]}]

    def run_ask(self, answer_for):
        out = io.StringIO()

        class In:
            def __init__(self):
                self.lines = None

            def readline(self):
                if self.lines is None:
                    published = json.loads(out.getvalue().strip()[len(decision.DECISION_PREFIX):])
                    self.lines = answer_for(published["id"])
                return self.lines.pop(0) if self.lines else ""
        return decision.ask("adn-dev", "octobre 2026", self.ITEMS, stdin=In(), stdout=out)

    def test_ignore_les_lignes_vides_du_mode_auto_et_les_autres_ids(self):
        result = self.run_ask(lambda id: ["\n", "\n", decision.answer_line("autre", {"a": decision.ATTACH}) + "\n",
                                          decision.answer_line(id, {"a": decision.ATTACH, "b": decision.RETRY}) + "\n"])
        self.assertEqual(result, {"a": decision.ATTACH, "b": decision.RETRY})

    def test_choix_invalide_ou_fin_de_flux_vaut_laisser(self):
        self.assertEqual(self.run_ask(lambda id: [decision.answer_line(id, {"a": decision.RETRY}) + "\n"]),
                         {"a": decision.LEAVE, "b": decision.LEAVE})
        self.assertEqual(self.run_ask(lambda id: []), {"a": decision.LEAVE, "b": decision.LEAVE})


class F6Mois(unittest.TestCase):
    def setUp(self):
        import getTransactionAttachments
        self.parse = getTransactionAttachments.parseMonthArg
        self.today = datetime(2026, 11, 9)

    def test_sans_option(self):
        self.assertEqual(self.parse(["--noGui"], self.today), (None, None))

    def test_mois_passe_donne_le_dernier_jour(self):
        date, error = self.parse(["--noGui", "--month", "2026_09"], self.today)
        self.assertIsNone(error)
        self.assertEqual((date.year, date.month, date.day), (2026, 9, 30))

    def test_mois_en_cours_et_futur_refuses(self):
        for value in ("2026_11", "2027_01"):
            date, error = self.parse(["--month", value], self.today)
            self.assertIsNone(date)
            self.assertIn("relevé Qonto", error)

    def test_format_invalide(self):
        self.assertIn("format attendu", self.parse(["--month", "09-2026"], self.today)[1])
        self.assertIn("format attendu", self.parse(["--month"], self.today)[1])


class F5Interface(unittest.TestCase):
    def setUp(self):
        import gui_launcher
        self.gui = gui_launcher
        self.manager = gui_launcher.ScriptManager()
        self.client = gui_launcher.app.test_client()

    def test_ligne_de_decision_interceptee_et_jamais_auto_repondue(self):
        line = decision.DECISION_PREFIX + json.dumps({"id": "d1", "society": "adn-dev", "period": "octobre 2026",
                                                       "items": [{"id": "a", "choices": ["attach", "leave"]}]})
        self.assertTrue(self.manager._consume(line))
        self.assertEqual(self.manager.get_decision()["id"], "d1")
        self.assertFalse(self.manager._consume("log normal"))

    def test_valider_refuse_une_reponse_incomplete_puis_transmet(self):
        process = mock.Mock()
        with mock.patch.object(self.gui, "manager", self.manager):
            self.manager.process, self.manager.running = process, True
            self.manager.decision = {"id": "d1", "items": [{"id": "a", "choices": ["attach", "leave"]},
                                                           {"id": "b", "choices": ["leave", "retry"]}]}
            refused = self.client.post("/api/decision", json={"id": "d1", "answers": {"a": "attach"}})
            self.assertEqual(refused.status_code, 400)
            self.assertEqual(refused.get_json()["missing"], ["b"])
            process.stdin.write.assert_not_called()
            ok = self.client.post("/api/decision", json={"id": "d1", "answers": {"a": "attach", "b": "leave"}})
            self.assertEqual(ok.status_code, 200)
            written = process.stdin.write.call_args[0][0]
            self.assertTrue(written.startswith(decision.ANSWER_PREFIX))
            self.assertIsNone(self.manager.get_decision())

    def test_demarrer_transmet_le_mois_et_refuse_un_format_invalide(self):
        with mock.patch.object(self.gui, "manager", self.manager), \
                mock.patch.object(self.manager, "start") as start:
            self.assertEqual(self.client.post("/api/start", json={"auto": True, "month": "oct"}).status_code, 400)
            start.assert_not_called()
            self.assertEqual(self.client.post("/api/start", json={"auto": True, "month": "2026_10"}).status_code, 200)
            start.assert_called_once_with(auto_mode=True, month="2026_10")


if __name__ == "__main__":
    unittest.main()


# F4 — détection de la connexion Amazon (retour sur /your-orders après connexion)
def test_f4_login_detected_on_new_orders_url():
    b = amazon.AmazonBrowser(notify=lambda *_: None)

    class Page:
        url = ""
    b._page = Page()
    for url, expected in [
        ("https://www.amazon.fr/ap/signin?openid=x", False),
        ("https://www.amazon.fr/ap/mfa?arb=x", False),
        ("https://www.amazon.fr/", False),
        ("https://www.amazon.fr/gp/css/order-history", True),
        ("https://www.amazon.fr/your-orders/orders?ref=x", True),
    ]:
        b._page.url = url
        assert b._logged_in() is expected, url
