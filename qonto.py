import os
import copy
import requests
import datetime
from pathlib import Path
import googleInvoiceInMail
import shutil
import extInfoAccess
import status
from datetime import datetime, date

class Qonto:
    listManageable = ["Google Cloud France SARL", "CDVI-HI"]
    baseUrl = ""
    genericHeaders = {
        "Authorization": "",
    }
    tmpDir = ""

    def __init__(self, baseUrl, tmpDir, requestedDate, society):
        Qonto.baseUrl = baseUrl
        Qonto.genericHeaders["Authorization"] = f'{extInfoAccess.getOrganisation(society)}:{extInfoAccess.getSecretKey(society)}'
        Qonto.tmpDir = tmpDir
        Qonto.requestedDate = requestedDate
        Qonto.society = society
        # Tous les problèmes rencontrés sont accumulés ici pour être remontés à
        # l'interface au lieu de se perdre dans les logs.
        self.report = status.Report(society)

    def run(self):
        print(">>>>> Get all transaction from Qonto")
        self.addMissingAttachment()
        self.receiveTransactionAttachment()
        return self.report

    def downloadStatement(self, destDir):
        """
        Télécharge le relevé de compte du mois demandé directement depuis
        l'API Qonto, sans passer par le mail ni le dossier de téléchargement.

        Renvoie (listeDesFichiers, messageDErreur). En cas d'échec la liste est
        vide et le message décrit la cause ; c'est l'appelant qui décide s'il
        s'agit d'une erreur (il peut se rabattre sur le dossier Téléchargements).
        """
        period = Qonto.requestedDate.strftime("%m-%Y")
        params = {"period_from": period, "period_to": period}

        # Un compte secondaire produit lui aussi un relevé : on se limite à
        # l'IBAN configuré quand il est renseigné.
        iban = extInfoAccess.getIban(Qonto.society)
        if iban:
            params["ibans[]"] = iban

        try:
            response = requests.get(
                Qonto.baseUrl + "statements",
                headers=Qonto.genericHeaders,
                params=params,
                timeout=60,
            )
        except requests.RequestException as e:
            return [], f"connexion à l'API impossible ({type(e).__name__}: {e})"

        if not response.ok:
            if response.status_code in (401, 403):
                return [], "clé secrète ou organisation invalide (HTTP %d)" % response.status_code
            return [], f"l'API a répondu {response.status_code} — {response.text[:150]}"

        try:
            statements = response.json().get("statements", [])
        except ValueError as e:
            return [], f"réponse illisible de l'API ({e})"

        if not statements:
            return [], f"aucun relevé publié par Qonto pour la période {period}"

        downloaded = []
        for statement in statements:
            fileInfo = statement.get("file") or {}
            fileName = fileInfo.get("file_name")
            fileUrl = fileInfo.get("file_url")
            if not fileName or not fileUrl:
                return downloaded, f"relevé {statement.get('id')} sans fichier téléchargeable"

            try:
                # L'URL est déjà signée et expire au bout de 30 minutes : il ne
                # faut surtout pas y joindre l'en-tête d'authentification Qonto.
                pdf = requests.get(fileUrl, timeout=120)
                pdf.raise_for_status()
            except requests.RequestException as e:
                return downloaded, f"téléchargement de {fileName} impossible ({type(e).__name__}: {e})"

            self.writeAttachmentFile(destDir, fileName, pdf)
            downloaded.append(fileName)

        return downloaded, ""

    def receiveTransactionAttachment(self):
        organisationUrl = Qonto.baseUrl + f'organizations/{extInfoAccess.getOrganisation(Qonto.society)}'
        
        transactions = self.getTransaction()

        print("List of transactions:")
        if transactions:
            downloaded = 0
            for transaction in transactions:
                amount = transaction["amount"]
                if amount != 0:
                    label = transaction["label"]
                    ref = transaction["reference"]
                    date = transaction["settled_at"]
                    note = transaction["note"]
                    transactionId = transaction["transaction_id"]

                    # Get id of transaction
                    id = transactionId.split('-')[-1]

                    # Remove / from ref
                    ref = str(ref).replace('/', '_')
                    label = str(label).replace('/', '_')

                    transactionDate = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    if (
                        transactionDate.year == self.requestedDate.year
                        and transactionDate.month == Qonto.requestedDate.month
                    ):
                        # print("\t label: ", label, " | ref: ", ref, " | id: ", id)
                        if len(transaction["attachment_ids"]) != 0:
                            attachmentsIds = transaction["attachment_ids"]
                            attachmentNbr = 0
                            for attachmentId in attachmentsIds:
                                # print("Attachment id = ", attachmentId)
                                try:
                                    url, extension = self.getTransactionAttachment(attachmentId)
                                    attachmentFile = requests.get(url)
                                    attachmentFile.raise_for_status()
                                except Exception as e:
                                    self.report.error(
                                        "Téléchargement d'un justificatif impossible",
                                        f'{label} du {date.split("T")[0]} ({type(e).__name__}: {e})',
                                    )
                                    continue

                                name = self.getFileName(label, id, date, attachmentNbr, extension, note)

                                self.writeAttachmentFile(Qonto.tmpDir, name, attachmentFile)
                                attachmentNbr =+ 1
                                downloaded += 1
                                print("\t\t", "==> Successful downloaded:", name)
                        else:
                            print("==> FAILLURE No Attachment:", label, ref, "Amount:", transaction["side"], transaction["amount"], transaction["currency"], "Date:", date)
                            self.report.warning(
                                "Transaction sans justificatif, à ajouter à la main sur Qonto",
                                f'{label} — {transaction["amount"]} {transaction["currency"]} le {date.split("T")[0]}',
                            )
                else:
                    print(" >>>>>>>>>>>>>>>>>>>>>>>>>> DROP this transac <<<<<<<<<<<<<<<<<<<")
                    print("----- ", transaction["label"])
            if downloaded == 0:
                self.report.warning(
                    "Aucun justificatif téléchargé",
                    f"aucune transaction sur {Qonto.requestedDate.strftime('%m/%Y')}",
                )
        else:
            print(f"ERROR no transaction find for {Qonto.requestedDate.year}/{Qonto.requestedDate.month}")
            self.report.error(
                "Aucune transaction récupérée depuis Qonto",
                f"période {Qonto.requestedDate.strftime('%m/%Y')}",
            )

    def getTransaction(self):
        transactionsUrl = Qonto.baseUrl + "transactions/"

        headers = copy.deepcopy(Qonto.genericHeaders)
        headers["Content-Type"] = "application/json"

        data = {
            "slug": extInfoAccess.getSlug(Qonto.society),
            "iban": extInfoAccess.getIban(Qonto.society),
            "status": "completed",
        }

        try:
            response = requests.get(transactionsUrl, headers=headers, json=data, timeout=60)
        except requests.RequestException as e:
            self.report.error(
                "Connexion à l'API Qonto impossible",
                f"{type(e).__name__}: {e}",
            )
            return ""

        if not response.ok:
            hint = "clé secrète ou organisation invalide" if response.status_code in (401, 403) else response.text[:200]
            self.report.error(
                f"L'API Qonto a répondu {response.status_code}",
                hint,
            )
            return ""

        try:
            return response.json()["transactions"] or ""
        except (ValueError, KeyError) as e:
            self.report.error("Réponse inattendue de l'API Qonto", f"{type(e).__name__}: {e}")
            return ""

    def addMissingAttachment(self):
        transactions = self.getTransaction()

        if transactions:
            for transaction in transactions:
                amount = transaction["amount"]
                date = transaction["emitted_at"]
                timestamp_date = datetime.strptime(date[:10], "%Y-%m-%d").date()
                if amount > 0.06 and ((timestamp_date.year, timestamp_date.month) == (Qonto.requestedDate.year, Qonto.requestedDate.month)):
                    label = transaction["label"]
                    transactionId = transaction["id"]
                    if not transaction["attachment_ids"] and label in Qonto.listManageable:
                        print("Not transaction found on Qonto for:", label)
                        attachmentPaths, fileNames = "", ""
                        deleteFileAtEnd = False
                        try:
                            if label == "Google Cloud France SARL":
                                attachmentPaths, fileNames = self.getGoogleWorkspaceInvoice()
                                deleteFileAtEnd = True

                            if label == "CDVI-HI":
                                attachmentPaths, fileNames = self.getCdviInvoice()
                                deleteFileAtEnd = True
                        except Exception as e:
                            self.report.error(
                                "Facture introuvable dans les mails",
                                f"{label} ({type(e).__name__}: {e})",
                            )

                        if attachmentPaths and fileNames:
                            for attachment, fileName in zip(attachmentPaths, fileNames):
                                self.addAttachment(transactionId, attachment, fileName, label)
                                if deleteFileAtEnd == True:
                                    shutil.rmtree(os.path.dirname(attachment))
                        else:
                            print("ERROR: Don't fine the bill for:", attachmentPaths, fileNames)
                            self.report.error(
                                "Facture non retrouvée, justificatif non ajouté",
                                f"{label} le {date[:10]}",
                            )
                    elif not transaction["attachment_ids"]:
                        # Signalé une seule fois, par receiveTransactionAttachment,
                        # qui balaie les mêmes transactions avec plus de détail.
                        print("Not transaction found on Qonto for:", label, date, amount, " => need to be added manually")

    def addAttachment(self, transactionId, filePath, fileName, label):
        url = Qonto.baseUrl + 'transactions/' + transactionId + '/attachments/'

        files = [('file', (fileName, open(filePath, 'rb'), 'application/pdf'))]

        response = requests.post(url, headers=Qonto.genericHeaders, files=files)
        
        if response.ok:
            print(f'\t {label} ==> Successfully updated')
        else:
            print(f'\t {label} ==> Error on sending attachment file: ', response.text)
            self.report.error(
                "Envoi du justificatif vers Qonto refusé",
                f"{label} (HTTP {response.status_code})",
            )

    def getTransactionAttachment(self, id):
        attachmentsUrl = Qonto.baseUrl + "attachments/" + id
        response = requests.get(attachmentsUrl, headers=Qonto.genericHeaders)
        return (
            response.json()["attachment"]["url"],
            response.json()["attachment"]["file_content_type"].split("/")[1],
        )


    def getFileName(self, label, ref, date, attachmentNbr, extension, note):

        attachmentIndex = str(attachmentNbr) if attachmentNbr > 0 else ""
        
        formatedDate = date.split("T")[0].replace("-", "_")
        fileName = f"{formatedDate}_"
        fileName = f"{fileName}{ref}_" if ref else fileName
        fileName = f"{fileName}{label}{attachmentIndex}"
        fileName = f"{fileName}_{note}" if note else fileName
        fileName = f"{fileName}.{extension}"

        charsToReplace = [" ", "*", ":"]
        for char in charsToReplace:
            fileName = fileName.replace(char, "_")

        return fileName


    def writeAttachmentFile(self, writeDir, name, file):
        if not os.path.exists(writeDir):
            os.mkdir(writeDir)

        open(writeDir + "/" + name, "wb").write(file.content)

    def getGoogleWorkspaceInvoice(self):
        mailPath = Path(googleInvoiceInMail.get("payments-noreply@google.com", "Google Workspace : votre facture pour adn-dev.fr est disponible"))
        attachmentPath = list(mailPath.glob("*.pdf"))
        fileName = os.path.basename(attachmentPath[0])

        return attachmentPath, fileName

    def getCdviInvoice(self):
        mailPath = Path(googleInvoiceInMail.get("*@stripe.com", "Votre reçu nº*"))
        attachmentPath = list(mailPath.glob("Invoice*.pdf"))
        fileName = os.path.basename(attachmentPath[0])

        return attachmentPath, fileName
