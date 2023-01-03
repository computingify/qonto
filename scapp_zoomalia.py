import requests
import os
import datetime
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET
from weasyprint import HTML  # to install: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
import re

LOGIN_URL = ('https://www.zoomalia.com/login/')
URL = ('https://www.zoomalia.com/mesachats/voirfacture')

def makepdf(html):
    """Generate a PDF file from a string of HTML."""
    htmldoc = HTML(string=html, base_url="")
    return htmldoc.write_pdf()

def run_zoomalia(invoce_amount, transaction_date, login, pwd, tmp_dir):

    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)

    date_object = datetime.datetime.strptime(transaction_date, "%Y-%m-%dT%H:%M:%S.%fZ")

    # Create payload
    payload = {
        "EMAIL": login, 
        "PWD": pwd,
    }

    # Keep the session open to request information
    with requests.session() as s:
        # Perform login
        s.post(LOGIN_URL, data=payload)
        
        # Get bill page
        result = s.get(URL)
        soup = BeautifulSoup(result.content, 'html.parser')

        # Search for bill in the html content
        invoice_link = extract_html_info(soup, invoce_amount, date_object)

        base_url = 'https://www.zoomalia.com'
        css_path = '/css/v1/facture.css'
        css_file_name = f'{tmp_dir}/invoiceStyle.css'
        if invoice_link:
            # download invoice
            invoice = s.get(invoice_link)

            # get css style sheet
            css = s.get(base_url + css_path)
            open(css_file_name, 'wb').write(css.content)

            # replace original style sheet path to the local one
            soup_invoice = BeautifulSoup(invoice.content, 'html.parser')
            css_links = soup_invoice.find_all('link', {'href': css_path})
            for css_link in css_links:
                css_link['href'] = css_file_name

            # Replace all "chat" occurances by "chien"
            search_and_replace(soup_invoice, 'chat ', 'chien ')
            search_and_replace(soup_invoice, ' chat', ' chien')
            search_and_replace(soup_invoice, 'Chat ', 'Chien ')
            search_and_replace(soup_invoice, ' Chat', ' Chien')
            search_and_replace(soup_invoice, 'oiseau ', 'chien ')
            search_and_replace(soup_invoice, ' oiseau', ' chien')
            search_and_replace(soup_invoice, 'Oiseau ', 'Chien ')
            search_and_replace(soup_invoice, ' Oiseau', ' Chien')
            search_and_replace(soup_invoice, 'oiseaux ', 'chien ')
            search_and_replace(soup_invoice, ' oiseaux', ' chien')
            search_and_replace(soup_invoice, 'Oiseaux ', 'Chien ')
            search_and_replace(soup_invoice, ' Oiseaux', ' Chien')

            # generate the pdf
            pdf_path = f'{tmp_dir}/invoiceZoomalia_{str(int(invoce_amount))}euro_{date_object.strftime("%Y%m")}.pdf'
            open(pdf_path, 'wb').write(makepdf(soup_invoice.encode('utf-8')))

            return pdf_path

def extract_html_info(soup, expected_amount, expected_date):
    # Search for bill in the html content
    orders = soup.find_all("div", {"class": "order"})
    
    for order in orders:
        
        # Search the amount
        order_head = order.find("div", {"class": "order__head__amount"})
        strongs = order_head.find_all('strong')
        for strong in strongs:
            tmp = strong.text.replace(',', '.')
            index = tmp.find('.')
            amount = tmp[0:index+3]
            amount = float(amount)
            if amount == expected_amount:
                break

        # Search the date
        order_head = order.find("div", {"class": "order__head__date"})
        strongs = order_head.find_all('strong')
        for strong in strongs:
            date = strong.text
            break

        # Search for bill link
        if amount == expected_amount:
            href = order.find("a", {"class": "divider order-invoice"}, href=True)['href']
            return href

def search_and_replace(soup_object, searched, replace):
    findcat = soup_object.find_all(text = re.compile(searched)) #, re.IGNORECASE
    for cat in findcat:
        fixed_text = cat.replace(searched, replace)
        cat.replace_with(fixed_text)

if __name__ == '__main__':
    # with open('scapping/r.html') as f:
    #     # print(f.read().encode('utf-8'))
    #     soup = BeautifulSoup(f.read(), 'html.parser')
    #     f.close()
    # href = extract_html_info(soup, 216.96, '2022-11-02')
    # print('link =', href)

    today = datetime.date.today().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    run_zoomalia(248.93, today, "tmp")