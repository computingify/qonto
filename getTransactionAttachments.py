import datetime
from enum import Enum
import shutil
import os
import json
import qonto
import sys
import extInfoAccess
import status
import subprocess
import traceback
from pathlib import Path
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

def manageStatement(dir, lastMonth, orgSlug, report, label="relevé Qonto", endedName="compte-principal-*statement.pdf"):
    """
    Déplace un relevé déposé à la main depuis le répertoire de téléchargement
    vers le répertoire de travail. Ne sert plus qu'à Bourse Direct : les relevés
    Qonto passent par l'API. Tout échec est remonté dans `report` pour être
    affiché en rouge dans l'interface, avec le nom de fichier attendu.
    """
    downloadDir = extInfoAccess.getDownloadDir()
    path = Path(downloadDir)

    # If it's not the default statement name, we just read the name endedName
    if("compte-principal-*statement.pdf" == endedName):
        statementFileName = (f'{lastMonth.strftime("%Y-%m")}-{orgSlug}-{endedName}')
    else:
        statementFileName = (f'{endedName}')

    if not path.is_dir():
        report.error(
            f"Répertoire de téléchargement introuvable ({label})",
            downloadDir,
        )
        return False

    statementFile = list(path.glob(statementFileName))

    if statementFile:
        if not os.path.exists(dir):
            os.mkdir(dir)
        try:
            shutil.move(statementFile[0], dir)
            print(f"Statement {label} moved: {os.path.basename(statementFile[0])}")
            return True
        except Exception as e:
            report.error(
                f"Déplacement du {label} impossible",
                f"{os.path.basename(statementFile[0])} ({type(e).__name__}: {e})",
            )
            return False
    else:
        print(f"Statement {orgSlug} file isn't present in Download directory")
        report.error(
            f"{label[0].upper()}{label[1:]} introuvable",
            f"attendu : {statementFileName} dans {downloadDir}",
        )
        return False

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


def processSociety(society, lastMonth, interactive):
    """Traite une société et renvoie son rapport d'anomalies."""
    report = status.Report(society)
    status.running(society)

    dirName = lastMonth.strftime("%Y_%m_") + society
    qontoClient = buildQonto(dirName, lastMonth, society)

    # Le relevé est récupéré uniquement via l'API Qonto : aucun repli sur le
    # dossier de téléchargement, un échec ici est une erreur franche.
    statementFiles, statementError = qontoClient.downloadStatement(dirName)
    if statementFiles:
        for name in statementFiles:
            print(f"Statement downloaded from Qonto API: {name}")
    else:
        report.error("Relevé Qonto non récupéré", statementError)

    if society == Society.ADN_GROUP:
        # Releve Bourse Direct pour ADN Group
        manageStatement(dirName, lastMonth, extInfoAccess.getOrganisation(society), report,
                        label="relevé Bourse Direct", endedName="pdf_*.pdf")
        # Rename the file pdf_*.pdf into Relevé_de_compte_Bourse_Direct.pdf
        bourse_direct_file = list(Path(dirName).glob("pdf_*.pdf"))
        if bourse_direct_file:
            new_name = Path(dirName) / "Relevé_de_compte_Bourse_Direct.pdf"
            bourse_direct_file[0].rename(new_name)
            print(f"Renamed {bourse_direct_file[0]} to {new_name}")
        else:
            print("No file matching 'pdf_*.pdf' found to rename.")

    report.absorb(qontoClient.run())

    if interactive:
        user_input = input("Do you want to Print all invoice ? (y/N): ").strip().lower()
        if user_input == 'y':
            print("Printing...")
            print(f"dirName = {dirName}")
            printElement.process(dirName)

    if not os.path.isdir(dirName):
        report.error(
            "Aucun fichier à archiver",
            f"le répertoire {dirName} n'a pas été créé, le zip ne peut pas être généré",
        )
        return report

    # Copy zip file localy
    cpPath = extInfoAccess.getZipFileDestination(society)
    destinationZip = os.path.join(cpPath, os.path.basename(dirName) + '.zip')
    doCopy = True
    print("path zip: ", destinationZip)
    if os.path.exists(destinationZip):
        if interactive:
            user_input = input(f"The file {os.path.basename(dirName)}.zip already exists. Do you want to override it ? (y/N): ").strip().lower()
            doCopy = (user_input == 'y')
        else:
            doCopy = False
        if not doCopy:
            print("File not copied. User choose to don't override.")
            report.warning(
                "Zip non copié : un fichier du même nom existe déjà",
                destinationZip,
            )

    zipfile(dirName)

    if doCopy:
        try:
            shutil.copy(dirName + '.zip', cpPath)
            print("Zip file is saved: ", str(cpPath))
        except Exception as e:
            report.error(
                "Copie du zip vers le dossier de destination impossible",
                f"{cpPath} ({type(e).__name__}: {e})",
            )
        else:
            openFileExplorer(cpPath)

    # Remove tmp files
    try:
        shutil.rmtree(dirName)
    except FileNotFoundError:
        print(f"Directory {dirName} does not exist, skipping removal.")
    except Exception as e:
        print(f"An error occurred while removing directory {dirName}: {e}")

    return report


def printSummary(reports):
    """Récapitulatif final lisible dans les logs."""
    print('============ RÉCAPITULATIF ============')
    for report in reports:
        if report.level == status.Level.OK:
            print(f"  ✓ {report.society} : OK")
        else:
            marker = "✗" if report.level == status.Level.ERROR else "!"
            print(f"  {marker} {report.society} : {len(report.errors)} erreur(s), {len(report.warnings)} avertissement(s)")
            for message in report.messages:
                print(f"      - {message}")


def main(argv):

    interactive = not ("--noGui" in argv)

    if "update" in argv:
        print('============ LAUNCH only UPDATE ==============')
        date = getLastMonthDate(getUserMonth())
        dirName = date.strftime("%Y_%m")
        buildQonto(dirName, date, Society.ADN_DEV).addMissingAttachment()
    else:
        print('============ LAUNCH the COMPLET generation ==============')
        for society in Society:
            status.emit(society, status.Level.PENDING)

        lastMonth = getLastMonthDate()
        strLastMonth = lastMonth.strftime("%Y_%m")
        user_input = input(f"Will run on date {strLastMonth} ? (Y/n): ").strip().lower()
        if user_input == 'n':
            user_input = input(f"Enter a date on format YYYY_MM: ").strip().lower()
            lastMonth = convert_str_to_datetime(user_input)
            if not lastMonth:
                status.emit(status.GLOBAL, status.Level.ERROR,
                            ["Date invalide, format attendu AAAA_MM"])
                return 1
            print(lastMonth)

        if interactive:
            print(">>>>> Will get all transactions attachments for ", lastMonth.strftime("%Y_%m"))
            # Les relevés Qonto sont téléchargés via l'API par chaque société.
            # Seul Bourse Direct reste manuel : il n'est pas exposé par Qonto.
            webbrowser.open("https://www.boursedirect.fr/fr/page/releves")

        # Handle all society
        reports = []
        for society in Society:
            print(f'>>>>>>>>>>>> START PROCESS for {society} <<<<<<<<<<<<')
            try:
                report = processSociety(society, lastMonth, interactive)
            except Exception as e:
                report = status.Report(society)
                report.error(
                    "Erreur inattendue pendant le traitement",
                    f"{type(e).__name__}: {e}",
                )
                traceback.print_exc()
            report.emit()
            reports.append(report)
            print(f'======= PROCESS ended for {society} =======')

        printSummary(reports)

        # TODO send zip file by mail to ANC2
        # TODO Filter on qonto transaction to get only current month
        # TODO Oauth sur compte Qonto => Impossible because needs to register the application to Qonto
        # TODO recherche des transactions qonto avec un filtre sur les dates


    print('============ DONE ============')

    # print(json.dumps(response, indent=2))

if __name__ == "__main__":
    main(sys.argv[1:])
