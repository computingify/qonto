# Generated by Selenium IDE
import pytest
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import datetime
import dateparser


# return number of days between d1 and d2 as integer
def days_between(d1, d2):
    date1 = datetime.datetime.strptime(d1, "%Y-%m-%dT%H:%M:%S.%fZ")
    date2 = datetime.datetime.strptime(d2, "%Y-%m-%dT%H:%M:%S.%fZ")
    return abs(date2 - date1).days

def convert_date(date_string):
  # dateparser.parse(date_string) => Convert french date into date format
  # .strftime("%Y-%m-%dT%H:%M:%S.%fZ") => Convert parsed date into standard one
  return dateparser.parse(date_string).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def get_elements(driver, order_index):
  css_selector_path_date = f"div.a-box-group:nth-child({order_index}) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > span:nth-child(1)"
  date_text = driver.find_element(By.CSS_SELECTOR, css_selector_path_date).text
  print("Raw date: ", date_text)
  date = convert_date(date_text)
                   montant    "div.a-box-group:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(4) > div:nth-child(2) > span:nth-child(1)"
                                "/html/body/div[1]/div[2]/div[1]/div[6]/div[2]/div[1]/div/div/div/div[1]/div/div[4]/div[2]/span"
                    Facture   "div.a-box-group:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > ul:nth-child(1) > span:nth-child(3) > span:nth-child(1) > a:nth-child(1)"
                                "/html/body/div[1]/div[2]/div[1]/div[6]/div[2]/div[1]/div/div/div/div[2]/div[2]/ul/span[1]/span/a"
                                "html.a-js.a-audio.a-video.a-canvas.a-svg.a-drag-drop.a-geolocation.a-history.a-webworker.a-autofocus.a-input-placeholder.a-textarea-placeholder.a-local-storage.a-gradients.a-transform3d.a-touch-scrolling.a-text-shadow.a-text-stroke.a-box-shadow.a-border-radius.a-border-image.a-opacity.a-transform.a-transition.a-ember.zufpdpkz.idc0_345.a-ws body.a-m-fr.a-aui_72554-c.a-aui_accordion_a11y_role_354025-c.a-aui_killswitch_csa_logger_372963-c.a-aui_launch_2021_ally_fixes_392482-t1.a-aui_pci_risk_banner_210084-c.a-aui_preload_261698-c.a-aui_rel_noreferrer_noopener_309527-c.a-aui_template_weblab_cache_333406-c.a-aui_tnr_v2_180836-c.a-meter-animate div#a-page div#yourOrders div#yourOrdersContent div#ordersContainer div.a-box-group.a-spacing-base.order.js-order-card div.a-box.a-color-offset-background.order-info div.a-box-inner div.a-fixed-right-grid div.a-fixed-right-grid-inner div.a-fixed-right-grid-col.actions.a-col-right div.a-row.a-size-base.yohtmlc-order-level-connections ul.a-unordered-list.a-nostyle.a-vertical span.hide-if-no-js span.a-declarative a.a-popover-trigger.a-declarative"
                              "#a-popover-content-3 > ul:nth-child(1) > li:nth-child(1) > span:nth-child(1) > a:nth-child(1)" Récap
                              "#a-popover-content-3 > ul:nth-child(1) > li:nth-child(2) > span:nth-child(1) > a:nth-child(1)" Facture 1 (content value should be Facture)
                                "/html/body/div[5]/div/div[1]/div/ul/li[2]/span/a"
                                "html.a-js.a-audio.a-video.a-canvas.a-svg.a-drag-drop.a-geolocation.a-history.a-webworker.a-autofocus.a-input-placeholder.a-textarea-placeholder.a-local-storage.a-gradients.a-transform3d.a-touch-scrolling.a-text-shadow.a-text-stroke.a-box-shadow.a-border-radius.a-border-image.a-opacity.a-transform.a-transition.a-ember.zufpdpkz.idc0_345.a-ws body.a-m-fr.a-aui_72554-c.a-aui_accordion_a11y_role_354025-c.a-aui_killswitch_csa_logger_372963-c.a-aui_launch_2021_ally_fixes_392482-t1.a-aui_pci_risk_banner_210084-c.a-aui_preload_261698-c.a-aui_rel_noreferrer_noopener_309527-c.a-aui_template_weblab_cache_333406-c.a-aui_tnr_v2_180836-c.a-meter-animate div#a-popover-3.a-popover.a-popover-no-header.a-declarative.a-arrow-bottom div.a-popover-wrapper div.a-popover-inner div#a-popover-content-3.a-popover-content ul.a-unordered-list.a-vertical.invoice-list.a-nowrap li span.a-list-item a.a-link-normal"
                              "#a-popover-content-3 > ul:nth-child(1) > li:nth-child(3) > span:nth-child(1) > a:nth-child(1)" Facture 2
                              "#a-popover-content-3 > ul:nth-child(1) > li:nth-child(4) > span:nth-child(1) > a:nth-child(1)" Demande de facture
                              "#a-popover-content-8 > ul:nth-child(1) > li:nth-child(2) > span:nth-child(1) > a:nth-child(1)" Facture de l autre item
                              "#a-popover-content-12 > ul:nth-child(1) > li:nth-child(2) > span:nth-child(1) > a:nth-child(1)"
                                "/html/body/div[8]/div/div[1]/div/ul/li[2]/span/a"
                              "#a-popover-content-10 > ul:nth-child(1) > li:nth-child(2) > span:nth-child(1) > a:nth-child(1)"
  css_selector_path_amount = f"div.a-box-group:nth-child({order_index}) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(4) > div:nth-child(2) > span:nth-child(1)"
  amount = driver.find_element(By.CSS_SELECTOR, css_selector_path_amount).text
  
  print("date: ", date, "amount: ", amount)

def run_amazon(invoce_amount, transaction_date, login, pwd, tmp_dir):
  driver = webdriver.Chrome('chromedriver')
  driver.get("https://www.amazon.fr/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.fr%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=frflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&")
  driver.find_element(By.ID, "ap_email").click()
  driver.find_element(By.ID, "ap_email").send_keys("adrien.jouve@adn-dev.fr")
  driver.find_element(By.CSS_SELECTOR, ".a-button-inner > #continue").click()
  driver.find_element(By.ID, "ap_password").send_keys("nhs!=ztWXRCEMJ/JU.ydD~5r|zj7G8K$")
  driver.find_element(By.ID, "signInSubmit").click()
  driver.find_element(By.CSS_SELECTOR, "#nav-link-yourAccount").click()
  driver.find_element(By.CSS_SELECTOR, "div.b-gallery:nth-child(1) > div:nth-child(1) > a:nth-child(1)").click()
  # content = driver.find_element(By.CSS_SELECTOR, "div.a-box-group:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(4) > div:nth-child(2) > span:nth-child(1)")
  # print("content = ", content.text)
  # create a loop here to scan all order, start at index 2
  # quit in case of undefine
  for x in range(2, 10):
    get_elements(driver, 2)

  driver.quit()


if __name__ == '__main__':
  today = datetime.date.today().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
  # run_amazon(248.93, today, '', '', "tmp")

  transaction_date = datetime.date.today().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
  date_text = '20 décembre 2022'
  item_date = convert_date(date_text)
  if (item_date <= transaction_date) and (days_between(item_date, transaction_date) <= 15):
    print("Good")
  else:
    print("No")