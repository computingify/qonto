import json

def getOrganisationSlug():
    return _get("qonto", "organization-slug")

def getSecretKey():
    return _get("qonto", "secret-key")

def getSlug():
    return _get("qonto", "slug")

def getIban():
    return _get("qonto", "iban")

def getDownloadDir():
    return _get("paths", "downloads")

def getTmpDir():
    return _get("paths", "tmp")

def getZoomaliaLogin():
    return _get("zoomalia", "login")

def getZoomaliaPwd():
    return _get("zoomalia", "password")

def _get(generalKey, key):
    f = open("confidential.json", 'r')
    credential = json.load(f)
    try:
        value = credential[generalKey][key]
    except:
        pass

    f.close()
    return value