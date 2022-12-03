import datetime
import shutil
import os
import json
import qonto
import sys
import extInfoAccess
from pathlib import Path
from googleQonto import getLastStatement
import printElement

def getLastMonthDate():
    # my_string = "2023-01-10"
    # my_date = datetime.datetime.strptime(my_string, "%Y-%m-%d")

    today = datetime.date.today()
    first = today.replace(day=1)
    last_month = first - datetime.timedelta(days=1)
    # print(last_month.strftime("%Y %m"))
    return last_month

def zipfile(dir):
    print(">>>>> Zip the directory", dir)
    shutil.make_archive(dir, "zip", dir)

def manageStatement(dir, lastMonth):
    path = Path(extInfoAccess.getDownloadDir())
    statementFileName = (f'{lastMonth.strftime("%Y-%m")}-{extInfoAccess.getOrganisationSlug()}-compte-principal-*statement.pdf')
    statementFile = list(path.glob(statementFileName))

    print(statementFile)
    if statementFile:
        if not os.path.exists(dir):
            os.mkdir(dir)

        try:
            shutil.move(statementFile[0], dir)
        except: 
            pass
    else:
        print("Statement file isn't present in Dowload directory")


def buildQonto(dirName, date):
    return qonto.Qonto("https://thirdparty.qonto.com/v2/", f'{extInfoAccess.getOrganisationSlug()}:{extInfoAccess.getSecretKey()}', dirName, date)


def main(argv):

    if "update" in argv:
        print('============ LAUNCH only UPDATE ==============')
        current_date = datetime.date.today()
        dirName = current_date.strftime("%Y_%m")
        buildQonto(dirName, current_date).addMissingAttachment()
    else:
        print('============ LAUNCH the COMPLET generation ==============')
        lastMonth = getLastMonthDate()
        print(
            ">>>>> Will get all transactions attachments for", lastMonth.strftime("%Y_%m")
        )
        dirName = lastMonth.strftime("%Y_%m")
        isError = getLastStatement()
        if isError == True:
            return 1

        manageStatement(dirName, lastMonth)

        buildQonto(dirName, lastMonth).run()

        printElement.process(dirName)

        zipfile(dirName)

        # Copy zip file localy
        cpPath = Path(r"C:/Users/compu/Documents/Administratif/adn dev/Factures Fournisseurs")
        shutil.copy(dirName + '.zip', cpPath)

        # TODO send zip file by mail to ANC2
        # TODO Filter on qonto transaction to get only current month
        # TODO get facture Free directly from Free API (remove Cozy usage)
        # TODO try to use scrapping to get releve de compte from qonto in place of opening webpage
        # TODO can update on user defined month
        # TODO Oauth sur compte Qonto => Impossible because needs to register the application to Qonto
        # TODO recherche des transactions qonto avec un filtre sur les dates

        # Remove tmp files
        shutil.rmtree(dirName)

    print('============ DONE ==============')

    # print(json.dumps(response, indent=2))

if __name__ == "__main__":
    main(sys.argv[1:])
