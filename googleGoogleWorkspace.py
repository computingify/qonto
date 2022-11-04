from googleMail import read_message, search_messages, gmailAuthenticate
import datetime

def getBillFromMail(emailAddress, subject):
    """
    From my Gmail account, get the latest qonto mail containning statement link
    Extract the link and on the webbowser using this link
    the user should enter the login and dowload the statement
    at the end the statement is inside download directory
    """
    service = gmailAuthenticate()
    print(f'----------- Search for email address: {emailAddress}, and subject: {subject}')
    try:
        today = datetime.date.today()
        # get emails that match the query you specify
        searchQuery = f'in:inbox after:{today.year}/{today.month}/01 before:{today.year}/{today.month}/06 from:{emailAddress} subject:{subject}'
        results = search_messages(service,searchQuery)

        print(f"Found {len(results)} results.")
        if 0 < len(results):
            for result in results:
                mailPath = read_message(service, result, True)

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")
    
    return mailPath


if __name__ == "__main__":
    getLastStatement()
# [END gmail_quickstart]
