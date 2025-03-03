import json
import os

def getOrganisation(society):
    if(checkIfExist(society)):
        return _get("qonto", society, "organization-slug")
    else:
        return ""

def getSecretKey(society):
    if(checkIfExist(society)):
        return _get("qonto", society, "secret-key")
    else:
        return ""

def getSlug(society):
    if(checkIfExist(society)):
        return _get("qonto", society, "slug")
    else:
        return ""

def getIban(society):
    if(checkIfExist(society)):
        return _get("qonto", society, "iban")
    else:
        return ""

def getDownloadDir():
    return os.path.expanduser(os.path.join(_get("paths", "downloads")))

def getTmpDir():
    return _get("paths", "tmp")

def getZipFileDestination(society):
    if(checkIfExist(society)):
        zipPath = _get("paths", society, "zipSave")
        zipPath = os.path.join(zipPath)
        return os.path.expanduser(zipPath)
    else:
        return ""
    
def checkIfExist(society):
    if( society == "adn-dev" or society == "adn-group" or society == "solio"):
        return True
    else:
        return False

def _get(generalKey, society, key=""):
    f = open("confidential.json", 'r')
    credential = json.load(f)
    try:
        if key == "":
            value = credential[generalKey][society]
        else:
            value = credential[generalKey][society][key]
    except:
        pass

    f.close()
    return value