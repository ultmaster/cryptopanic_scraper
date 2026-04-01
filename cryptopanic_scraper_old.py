from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import time
import datetime
import re
import pickle
import urllib.parse
import argparse
from webdriver_manager.chrome import ChromeDriverManager
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")

parser.add_argument("-f", "--filter",
                    help="Type of News filter",
                    default="All",
                    choices=['all', "hot", "rising", "bullish",
                             "bearish", "lol", "commented", "important", "saved"])

parser.add_argument("-s", "--headless", help="Run Chrome driver headless",
                    action="store_true")

parser.add_argument("-l", "--limit", help="Amount of pages to scrape",
                    type=int, default=None)


args = parser.parse_args()

if args.verbose:
    print("verbosity turned on")

# TODO: Create logger for exception handling
# TODO: Replace print with logger
# TODO: Create bash script or cron to automate this script



SCROLL_PAUSE_TIME = 1


def setUp():

    url = "https://www.cryptopanic.com/news?filter={}".format(args.filter)

    options = webdriver.ChromeOptions()

    # initialize headless mode
    if args.headless:
        options.add_argument('headless')

    # Don't load images
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    # Set the window size
    options.add_argument('window-size=1200x800')

    # initialize the driver
    print("Initializing chromedriver.\n")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    print("Navigating to %s\n" % url)
    driver.get(url)

    # wait up to 2.5 seconds for the elements to become available
    driver.implicitly_wait(2.5)

    return driver


def loadMore(len_elements):
    # Infinite scroll

    # Load More News
    load_more = driver.find_element(By.CLASS_NAME, 'btn-outline-primary')
    driver.execute_script("arguments[0].scrollIntoView();", load_more)

    time.sleep(SCROLL_PAUSE_TIME)

    elements = driver.find_elements(By.CSS_SELECTOR,'div.news-row.news-row-link')
    if len_elements < len(elements):
        if args.verbose:
            print("Loading %s more rows" % (len(elements) - len_elements))
        return True
    else:
        if args.verbose:
            print("No more rows to load :/")
            print("Total rows loaded: %s\n" % len(elements))
        return False


def getData():
    data = dict()
    elements = driver.find_elements(By.CSS_SELECTOR,'div.news-row.news-row-link')

    total_rows = len(elements)
    print("Found %s rows on the page.\n" % total_rows)
    print("Downloading Data...\n")
    start = datetime.datetime.now()
    print("Time Start: %s\n" % start)

    for i in range(total_rows):
        if args.limit is not None and i >= args.limit:
            print(f'Limit argument of {args.limit} hit.')
            break
        time.sleep(.5)  # Busy sleep to keep cpu cool
        try:
            el = elements[i]

            #  Get date posted
            date_time = el.find_element(By.CSS_SELECTOR, 'time').get_attribute('datetime')

            #  Get Title of News
            title = el.find_element(By.CSS_SELECTOR, "span.title-text span:nth-child(1)").text
            if title == '':
                driver.execute_script("arguments[0].scrollIntoView();",
                                      el.find_element(By.CSS_SELECTOR, "span.title-text"))
                title = el.find_element(By.CSS_SELECTOR, "span.title-text span:nth-child(1)").text

            #  Get Currency Tags
            currencies = []
            currency_elements = el.find_elements(By.CLASS_NAME, "colored-link")
            for currency in currency_elements:
                currencies.append(currency.text)

            votes = dict()
            nc_votes = el.find_elements(By.CSS_SELECTOR, "span.nc-vote-cont")
            for nc_vote in nc_votes:
                vote = nc_vote.get_attribute('title')
                if vote is None:
                    continue
                value = vote[:2]
                action = vote.replace(value, '').replace('votes', '').strip()
                votes[action] = int(value)

            # Get Source URL (navigates away, so do this last)
            link_el = el.find_element(By.CSS_SELECTOR, "a.news-cell.nc-title")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_el)
            time.sleep(0.3)
            link_el.click()
            source_name = el.find_element(By.CSS_SELECTOR, "span.si-source-name").text
            source_link = driver.find_element(By.XPATH, "//div/h1/a[2]").get_property('href')
            source_url = re.sub(".*=", '', urllib.parse.unquote(str(source_link)))
            driver.back()
            driver.implicitly_wait(2.5)

            # Re-query elements after navigation invalidated the old references
            elements = driver.find_elements(By.CSS_SELECTOR, 'div.news-row.news-row-link')

            data[i] = {"Date": date_time,
                       "Title": title,
                       "Currencies": currencies,
                       "Votes": votes,
                       "Source": source_name,
                       "URL": source_url}
            if args.verbose:
                print("Downloaded %s of %s\nPublished: %s\nTitle: %s\nSource: %s\nURL: %s\n" % (i + 1,
                                                                                                total_rows,
                                                                                                data[i]["Date"],
                                                                                                data[i]["Title"],
                                                                                                data[i]["Source"],
                                                                                                data[i]["URL"]))
        except Exception as e:
            print(e)
            raise e

    print("Finished gathering %s rows of data\n" % len(data))
    print("Time End: %.19s" % datetime.datetime.now())
    print("Elapsed Time Gathering Data: %.7s\n" % (datetime.datetime.now() - start))

    return data


def saveData(data):
    # Save the website data
    file_name = "cryptopanic_{}_{:.10}->{:.10}.pickle".format(args.filter.lower(),
                                                              str(data[len(data) - 1]['Date']),
                                                              str(data[0]['Date']))
    # Make sure directory exists, if not make one.
    pathlib.Path("data").mkdir(parents=True, exist_ok=True)

    with open(os.path.join(os.getcwd(), 'data', file_name), 'wb') as f:
        pickle.dump(data, f)

    print("Saved data to %s\n" % file_name)


def tearDown():
    if args.verbose:
        print("Exiting Chrome Driver")
    driver.quit()


driver = setUp()
if __name__ == "__main__":
    if args.limit is not None:
        data_limit = args.limit
    else:
        data_limit = 100000  # Just make this number massive.
    print("Loading News Feed...\n")
    while True:

        elements = driver.find_elements(By.CSS_SELECTOR,'div.news-row.news-row-link')

        if len(elements) <= data_limit and loadMore(len(elements)):
            continue
        else:
            data = getData()
            saveData(data)
            tearDown()
            break
