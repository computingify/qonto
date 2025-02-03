import os
import copy
import requests
import datetime
from pathlib import Path
import googleInvoiceInMail
import shutil
import extInfoAccess
from scapp_zoomalia import run_zoomalia
from datetime import datetime, date

class Qonto:
    listManageable = ["Free Telecom", "Google Cloud France SARL", "Zoomalia", "ZOOMALIA.COM", "HPY*ZOOMALIA.COM", "CDVI-HI", "ToolStation"]
    baseUrl = ""
    genericHeaders = {
        "Authorization": "",
    }
    tmpDir = ""

    def __init__(self, baseUrl, authorizationKey, tmpDir, requestedDate):
        Qonto.baseUrl = baseUrl
        Qonto.genericHeaders["Authorization"] = authorizationKey
        Qonto.tmpDir = tmpDir
        Qonto.requestedDate = requestedDate

    def run(self):
        print(">>>>> Get all transaction from Qonto")
        self.addMissingAttachment()
        self.receiveTransactionAttachment()

    def receiveTransactionAttachment(self):
        organisationUrl = Qonto.baseUrl + f'organizations/{extInfoAccess.getOrganisationSlug()}'
        
        transactions = self.getTransaction()

        print("List of transactions:")
        if transactions:
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
                                url, extension = self.getTransactionAttachment(attachmentId)
                                attachmentFile = requests.get(url)

                                name = self.getFileName(label, id, date, attachmentNbr, extension, note)

                                self.writeAttachmentFile(Qonto.tmpDir, name, attachmentFile)
                                attachmentNbr =+ 1
                                print("\t\t", "==> Successful downloaded:", name)
                        else:
                            print("==> FAILLURE No Attachment:", label, ref, "Amount:", transaction["side"], transaction["amount"], transaction["currency"], "Date:", date)
                else:
                    print(" >>>>>>>>>>>>>>>>>>>>>>>>>> DROP this transac <<<<<<<<<<<<<<<<<<<")
                    print("----- ", transaction["label"])
        else:
            print(f"ERROR no transaction find for {Qonto.requestedDate.year}/{Qonto.requestedDate.month}")

    def getTransaction(self):
        transactionsUrl = Qonto.baseUrl + "transactions/"

        headers = copy.deepcopy(Qonto.genericHeaders)
        headers["Content-Type"] = "application/json"

        data = {
            "slug": extInfoAccess.getSlug(),
            "iban": extInfoAccess.getIban(),
            "status": "completed",
        }

        response = requests.get(transactionsUrl, headers=headers, json=data)
        if response.json()["transactions"]:
            return response.json()["transactions"]
        else:
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
                        if label == "Free Telecom":
                            attachmentPaths, fileNames = self.getFreeInvoice()
                            deleteFileAtEnd = False

                        if label == "Google Cloud France SARL":
                            attachmentPaths, fileNames = self.getGoogleWorkspaceInvoice()
                            deleteFileAtEnd = True

                        if label == "CDVI-HI":
                            attachmentPaths, fileNames = self.getCdviInvoice()
                            deleteFileAtEnd = True
                            
                        if attachmentPaths and fileNames:
                            for attachment, fileName in zip(attachmentPaths, fileNames):
                                self.addAttachment(transactionId, attachment, fileName, label)
                                if deleteFileAtEnd == True:
                                    shutil.rmtree(os.path.dirname(attachment))
                        else:
                            print("ERROR: Don't fine the bill for:", attachmentPaths, fileNames)
                    elif not transaction["attachment_ids"]:
                        print("Not transaction found on Qonto for:", label, date, amount, " => need to be added manually")

    def addAttachment(self, transactionId, filePath, fileName, label):
        url = Qonto.baseUrl + 'transactions/' + transactionId + '/attachments/'

        files = [('file', (fileName, open(filePath, 'rb'), 'application/pdf'))]

        response = requests.post(url, headers=Qonto.genericHeaders, files=files)
        
        if response.ok:
            print(f'\t {label} ==> Successfully updated')
        else:
            print(f'\t {label} ==> Error on sending attachment file: ', response.text)

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

        print(f"writeDir: {writeDir} ¡ name: {name}")
        open(writeDir + "/" + name, "wb").write(file.content)


    def getFreeInvoice(self):
        path = Path('C:/Users/compu/Cozy Drive/Administratif/Free Internet/fbx24442322')
        fileName = f'{Qonto.requestedDate.strftime("%Y%m")}_free.pdf'
        if path and fileName:
            attachmentPath = list(path.glob(fileName))
        else:
            print(f"ERROR: path or label empty: \n path: {path}\n fileName: {fileName}")
        
        return attachmentPath, fileName

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
