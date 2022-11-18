from googleMail import read_message, search_messages, gmailAuthenticate
# import datetime

def get(emailAddress, subject):
    """
    From my Gmail account, get the emailAddress subject mail
    and extract the attached invoice
    """
    service = gmailAuthenticate()
    print(f'----------- Search for email address: {emailAddress}, and subject: {subject}')
    try:
        # get emails that match the query you specify
        # today = datetime.date.today()
        # searchQuery = f'in:inbox after:{today.year}/{today.month}/01 before:{today.year}/{today.month}/08 from:{emailAddress} subject:{subject}'
        searchQuery = f'in:inbox newer_than:1m from:{emailAddress} subject:{subject} has:attachment'
        results = search_messages(service,searchQuery)

        print(f"Found {len(results)} results.")
        if 0 < len(results):
            # Get only the most recent mail
            mailPath = read_message(service, results[0], True)

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")
    
    return mailPath

if __name__ == '__main__':
    # get("payments-noreply@google.com", "Google Workspace : votre facture pour adn-dev.fr est disponible")
    get("*@stripe.com", "Votre reçu nº*")