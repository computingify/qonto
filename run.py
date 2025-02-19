#!/usr/bin/env python3

import os
import sys
import subprocess

def activate_venv_and_run():
    # Chemin vers l'environnement virtuel 
    venv_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "qontoenv")
    
    # Activation de l'environnement virtuel
    if sys.platform == "win32":
        activate_script = os.path.join(venv_path, "Scripts", "activate.bat") 
    else:
        print('On Unix platform')
        activate_script = f"source {os.path.join(venv_path, 'bin', 'activate')}"

    # Exécution du script principal
    script_path = "getTransactionAttachments.py"
    
    try:
        if sys.platform == "win32":
            subprocess.run(f"{activate_script} && python3 {script_path}", shell=True, check=True)
        else:
            subprocess.run(f"{activate_script}; python3 {script_path}", shell=True, check=True)
        
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(activate_venv_and_run())