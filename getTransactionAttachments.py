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
from datetime import datetime, date, timedelta

def getLastMonthDate():
    # my_string = "2023-01-10"
    # my_date = datetime.datetime.strptime(my_string, "%Y-%m-%d")

    today = date.today()
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    return last_month

def zipfile(dir):
    print(">>>>> Zip the directory", dir)
    shutil.make_archive(dir, "zip", dir)

def manageStatement(dir, lastMonth):
    path = Path(extInfoAccess.getDownloadDir())
    statementFileName = (f'{lastMonth.strftime("%Y-%m")}-{extInfoAccess.getOrganisationSlug()}-compte-principal-*statement.pdf')
    statementFile = list(path.glob(statementFileName))

    # print(statementFile)
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

def openFileExplorer(path):
    try:
        # Using os.startfile to open the file explorer at the specified path
        os.startfile(path)
    except Exception as e:
        print(f"An error occurred: {e}")

def convert_str_to_datetime(str_time):
    try:
        # Parse the string time as a datetime object
        result_datetime = datetime.strptime(str_time, "%Y_%m")
        return result_datetime
    except ValueError:
        return None
    
def main(argv):

    if "update" in argv:
        print('============ LAUNCH only UPDATE ==============')
        current_date = date.today()
        dirName = current_date.strftime("%Y_%m")
        buildQonto(dirName, current_date).addMissingAttachment()
    else:
        print('============ LAUNCH the COMPLET generation ==============')
        lastMonth = getLastMonthDate()
        strLastMonth = lastMonth.strftime("%Y_%m")
        user_input = input(f"Will run on date {strLastMonth} ? (Y/n): ").strip().lower()
        if user_input == 'n':
            user_input = input(f"Enter a date on format YYYY_MM: ").strip().lower()
            lastMonth = convert_str_to_datetime(user_input)
            if not lastMonth:
                return 1
            print(lastMonth)
        print(
            ">>>>> Will get all transactions attachments for ", lastMonth.strftime("%Y_%m")
        )
        dirName = lastMonth.strftime("%Y_%m")
        # isError = getLastStatement()
        # if isError == True:
        #     return 1

        # manageStatement(dirName, lastMonth)

        buildQonto(dirName, lastMonth).run()

        user_input = input("Do you want to Print all invoice ? (y/N): ").strip().lower()
        if user_input == 'y':
            print("Printing...")
            printElement.process(dirName)

        # Copy zip file localy
        cpPath = Path(r"C:/Users/compu/Documents/Administratif/adn dev/Banque/Relever de comptes")
        doCopy = True
        print("path zip: ", os.path.join(cpPath, os.path.basename(dirName) + '.zip'))
        if os.path.exists(os.path.join(cpPath, os.path.basename(dirName) + '.zip')):
            user_input = input(f"The file {os.path.basename(dirName)}.zip already exists. Do you want to override it ? (y/N): ").strip().lower()
            if user_input == 'y':
                # Enable the copy operation
                doCopy = True
            else:
                doCopy = False
                print("File not copied. User chose not to override.")
        zipfile(dirName)
        if doCopy:
            print("Zip file is saved: ", str(cpPath))
            shutil.copy(dirName + '.zip', cpPath)

        openFileExplorer(cpPath)

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
