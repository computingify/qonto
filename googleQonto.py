import json
from urllib.error import HTTPError
from googleMail import search_messages, gmailAuthenticate
from bs4 import BeautifulSoup  # pip install BeatifulSoup4
from base64 import urlsafe_b64decode
import webbrowser
import datetime

def getQontoStatementUrl(service, message):
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message["id"], format="full")
        .execute()
    )
    payload = msg["payload"]

    body = payload.get("body")
    # print(json.dumps(body.get("data"), indent=2))
    dataEncoded = body.get("data")
    dataHtml = urlsafe_b64decode(dataEncoded)
    # print(dataHtml)
    # Parse HTML content using BeautifulSoup
    soup = BeautifulSoup(dataHtml, "html.parser")
    
    # Extract the title tag and print its content
    # title = soup.find("title")
    # if title:
    #     print("Email Title: " + title.get_text())
    
    for td in soup.find_all("td", {"class": "active-t btn"}):
        return td.a.get("href")


def getLastStatement(subject):
    """
    From my Gmail account, get the latest qonto mail containning statement link
    Extract the link and on the webbowser using this link
    the user should enter the login and dowload the statement
    at the end the statement is inside download directory
    """
    service = gmailAuthenticate()

    try:
        today = datetime.date.today()
        # get emails that match the query you specify
        searchQuery = f'in:inbox after:{today.year}/{today.month}/01 before:{today.year}/{today.month}/10 from:support@qonto.com subject:{subject}'
        print("searchQuery: {searchQuery}")
        results = search_messages(service, searchQuery)

        print(f"Found {len(results)} results: {results}")
        if 0 < len(results):
            for email in results:
                statementUrl = getQontoStatementUrl(service, email)
                if statementUrl:
                    # print("statementUrl : " + statementUrl)
                    webbrowser.open(statementUrl)

                    input("Press Enter when statement for {subject} downloaded")
                # else:
                #     print("Not find")

            return False
        else:
            print("No statement found for {subject}, Exit")
            return True
        

    except HTTPError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    getLastStatement()
