import datetime
from enum import Enum
import shutil
import os
import json
import qonto
import sys
import extInfoAccess
import subprocess
from pathlib import Path
from googleQonto import getLastStatement
import printElement
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import webbrowser

class Society(str, Enum):
    ADN_DEV = "adn-dev"
    ADN_GROUP = "adn-group"
    SOLIO = "solio"

def getLastMonthDate(months_ago=1):
    # Get the current date and time
    current_datetime = datetime.now()
    if months_ago == 0:
        return current_datetime

    # Calculate the first day of the current month
    first_day_of_current_month = current_datetime.replace(day=1)

    # Calculate the last day of the specified month(s) ago
    last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
    last_day_of_target_month = last_day_of_last_month - relativedelta(months=months_ago-1)
    return last_day_of_target_month

def getUserMonth():
    # Get user input for the number of months
    while True:
        try:
            months_ago = int(input("Enter the number of months (0 to 3): "))
            if 0 <= months_ago <= 3:
                break
            else:
                print("Invalid input. Please enter a number between 0 and 3.")
        except ValueError:
            print("Invalid input. Please enter a valid integer.")
    return months_ago

def zipfile(dir):
    print(">>>>> Zip the directory", dir)
    shutil.make_archive(dir, "zip", dir)

def manageStatement(dir, lastMonth, type, endedName="compte-principal-*statement.pdf"):
    path = Path(extInfoAccess.getDownloadDir())
    
    # If it's not the default statement name, we just read the name endedName
    if("compte-principal-*statement.pdf" == endedName):
        statementFileName = (f'{lastMonth.strftime("%Y-%m")}-{type}-{endedName}')
    else:
        statementFileName = (f'{endedName}')
    statementFile = list(path.glob(statementFileName))

    if statementFile:
        if not os.path.exists(dir):
            os.mkdir(dir)
        try:
            shutil.move(statementFile[0], dir)
        except: 
            pass
    else:
        print(f"Statement {type} file isn't present in Download directory")

def buildQonto(dirName, date, society):
    return qonto.Qonto("https://thirdparty.qonto.com/v2/", dirName, date, society)

def openFileExplorer(path):
    try:
        # Using os.startfile to open the file explorer at the specified path
        # os.startfile(path)
        subprocess.run(['open', '-R', path])
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
        date = getLastMonthDate(getUserMonth())
        dirName = date.strftime("%Y_%m")
        buildQonto(dirName, date, Society.ADN_DEV).addMissingAttachment()
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
        print(">>>>> Will get all transactions attachments for ", lastMonth.strftime("%Y_%m"))
        isError = getLastStatement(Society.ADN_DEV)
        if isError == True:
            return 1
        
        # Open web browser to download Bourse direct statement
        webbrowser.open("https://www.boursedirect.fr/fr/page/releves")

        # Handle all society
        for society in Society:
            print(f'>>>>>>>>>>>> START PROCESS for {society} <<<<<<<<<<<<')
            dirName = lastMonth.strftime("%Y_%m_") + society
            manageStatement(dirName, lastMonth, extInfoAccess.getOrganisation(society))
            if society == Society.ADN_GROUP:
                manageStatement(dirName, lastMonth, extInfoAccess.getOrganisation(society), "Relevé de compte Bourse Direct.pdf") # Releve Bourse Direct pour ADN Group
                
            buildQonto(dirName, lastMonth, society).run()

            user_input = input("Do you want to Print all invoice ? (y/N): ").strip().lower()
            if user_input == 'y':
                print("Printing...")
                print(f"dirName = {dirName}")
                printElement.process(dirName)

            # Copy zip file localy
            cpPath = extInfoAccess.getZipFileDestination(society)
            doCopy = True
            print("path zip: ", os.path.join(cpPath, os.path.basename(dirName) + '.zip'))
            if os.path.exists(os.path.join(cpPath, os.path.basename(dirName) + '.zip')):
                user_input = input(f"The file {os.path.basename(dirName)}.zip already exists. Do you want to override it ? (y/N): ").strip().lower()
                if user_input == 'y':
                    # Enable the copy operation
                    doCopy = True
                else:
                    doCopy = False
                    print("File not copied. User choose to don't override.")
            zipfile(dirName)
            if doCopy:
                print("Zip file is saved: ", str(cpPath))
                shutil.copy(dirName + '.zip', cpPath)

            openFileExplorer(cpPath)

            # Remove tmp files
            shutil.rmtree(dirName)
            shutil.rmtree(f'{dirName}.zip')
            
            print(f'======= PROCESS ended for {society} =======')
        
        # TODO send zip file by mail to ANC2
        # TODO Filter on qonto transaction to get only current month
        # TODO Oauth sur compte Qonto => Impossible because needs to register the application to Qonto
        # TODO recherche des transactions qonto avec un filtre sur les dates


    print('============ DONE ============')

    # print(json.dumps(response, indent=2))

if __name__ == "__main__":
    main(sys.argv[1:])
