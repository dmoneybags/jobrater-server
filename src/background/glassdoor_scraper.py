#(c) 2024 Daniel DeMoney. All rights reserved.
'''
Execution flow:

Background.js

Listens for: a tab change event fired when the current tabs url changes
Executes: scrapes the jobId from the url
Sends: a message to the contentScript that we recieved a new job
\/
\/
ContentScript.js
Listens for: the new job event from background.js
Executes the scraping of the linkedin and glassdoor
Calls:
\/
\/
glassdoor_scraper_server
Listens for: requests sent from content script to scrape glassdoor for a given compnay
Executes the functions from 
\/
\/
glassdoor_scraper
'''

#Credit to scrapfly

"""
Python code I copied from scrapfly and editted to run smoother and not use their insanely priced api

ISSUES:

Glassdoor will block our requests sometimes and throw a captcha or however you spell it
"""
import os
from enum import Enum
import asyncio
import json
import os
import re
from seleniumwire import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.remote.webdriver import WebDriver, By
from bs4 import BeautifulSoup
import brotli
from html import escape
from typing import Dict, List, Optional, Tuple, TypedDict
from random import choice
from threading import Lock
import logging
from selenium.webdriver.remote.remote_connection import LOGGER
import time
from glassdoor_cookie_manager import CookieManager
import random

#os.environ['MOZ_HEADLESS'] = '1'

def get_random_header():
    headers_list : list[Dict] = [
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "screen-width": 2560,
            "screen-height": 1080
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/14.1.2 Safari/605.1.15"
            ),
            "Accept-Language": "en-US,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.apple.com/",
            "DNT": "1",
            "screen-width": 2560,
            "screen-height": 1440
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) "
                "Gecko/20100101 Firefox/89.0"
            ),
            "Accept-Language": "en-US,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.mozilla.org/",
            "DNT": "1",
            "screen-width": 2560,
            "screen-height": 1440
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/90.0.4430.93 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "screen-width": 1440,
            "screen-height": 900
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/14.0 Mobile/15E148 Safari/604.1"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.apple.com/",
            "DNT": "1",
            "screen-width": 390,
            "screen-height": 844
        }
    ]
    return choice(headers_list)

def get_driver(headless: bool = True):
    logging.info("generating driver...")
    
    # Randomize the User-Agent and headers to appear like different users
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    ]
    
    header: Dict = {
        "User-Agent": random.choice(user_agents),
        "TE": "trailers",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://www.glassdoor.com/",
        "Priority": "u=4",
        "Connection": "keep-alive",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept": "*/*"
    }
    
    # Inject custom headers into Selenium Wire requests
    seleniumwire_options = {
        'headers': header
    }
    
    # Random delay to mimic real user behavior
    def human_delay():
        time.sleep(random.uniform(1, 3))

    firefox_options = Options()
    if headless:
        firefox_options.add_argument("--headless")
    
    # Set preferences to hide automation traces
    firefox_options.set_preference("dom.webdriver.enabled", False)
    firefox_options.set_preference('useAutomationExtension', False)
    firefox_options.set_preference("media.peerconnection.enabled", False)
    firefox_options.set_preference("dom.webnotifications.enabled", False)
    firefox_options.set_preference("dom.push.enabled", False)
    firefox_options.set_preference("network.proxy.type", 1)
    firefox_options.set_preference("network.proxy.http", "127.0.0.1")
    firefox_options.set_preference("network.proxy.http_port", 8080)
    firefox_options.set_preference("network.proxy.ssl", "127.0.0.1")
    firefox_options.set_preference("network.proxy.ssl_port", 8080)
    firefox_options.set_preference("network.proxy.no_proxies_on", "localhost, 127.0.0.1")
    firefox_options.page_load_strategy = "eager"

    # Initialize the WebDriver
    driver: webdriver.Firefox = webdriver.Firefox(options=firefox_options, seleniumwire_options=seleniumwire_options)
    driver.set_window_size(*random.choice([(1920, 1080), (2560, 1440)]))
    
    # Random delay before executing scripts
    #human_delay()
    
    # Hide 'webdriver' from the navigator object
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Navigate to a dummy page and load cookies to simulate a real session
    #driver.get("https://www.glassdoor.com/404")
    #human_delay()
    
    #CookieManager.load_cookies(driver)
    
    # Return the driver
    return driver

def extract_apollo_state(html):
    """Extract apollo graphql state data from HTML source"""
    t = time.time()
    soup = BeautifulSoup(html, 'html.parser')
    script_tag = soup.find('script', id='__NEXT_DATA__')
    logging.info(f"Finding apollo script took {time.time() - t} seconds")
    if script_tag:
        data = script_tag.string.strip()
        if data:
            t = time.time()
            # Load JSON data into Python dictionary
            json_data = json.loads(data)
            # Access nested properties
            apollo_cache = json_data["props"]["pageProps"]["apolloCache"]
            logging.info(f"Finding apollo state in json {time.time() - t} seconds")
            return apollo_cache
    try:
        t = time.time()
        data = re.findall('apolloState":\s*({.+})};', html)[0]
        data = json.loads(data)
        logging.info(f"Using regex to find apollo state took {time.time() - t} seconds")
        return data
    except IndexError:
        raise ValueError("No apollo state in html: " + html)


def parse_reviews(html) -> Tuple[List[Dict], int]:
    """parse jobs page for job data and total amount of jobs"""
    cache = extract_apollo_state(html)
    xhr_cache = cache["ROOT_QUERY"]
    reviews = next(v for k, v in xhr_cache.items() if k.startswith("employerReviews") and v.get("reviews"))
    return reviews

def parse_salaries(html) -> Tuple[List[Dict], int]:
    """parse jobs page for job data and total amount of jobs"""
    cache = extract_apollo_state(html)
    xhr_cache = cache["ROOT_QUERY"]
    salaries = next(v for k, v in xhr_cache.items() if k.startswith("salariesByEmployer") and v.get("results"))
    return salaries
async def scrape_cache(url: str, session: WebDriver):
    """Scrape job listings"""
    t = time.time()
    session.get(url)
    logging.info(f"Requesting page from glassdoor took {time.time() - t} seconds")
    first_page_response = session.page_source  # Await here to fetch the first page asynchronously
    cache = extract_apollo_state(first_page_response)
    xhr_cache = cache["ROOT_QUERY"]
    key = [key for key in xhr_cache.keys() if key.startswith("employerReviewsRG")][0]
    company_data = xhr_cache[key]
    return company_data
def get_company_from_page_source(page_source: str, company_data_url: str):
    cache = extract_apollo_state(page_source)
    xhr_cache = cache["ROOT_QUERY"]
    key = [key for key in xhr_cache.keys() if key.startswith("employerReviewsRG")][0]
    company_data_full = xhr_cache[key]
    logging.info(json.dumps(company_data_full, indent=2))
    return {
        "overallRating": company_data_full["ratings"]["overallRating"],
        "businessOutlookRating": company_data_full["ratings"]["businessOutlookRating"],
        "careerOpportunitiesRating": company_data_full["ratings"]["careerOpportunitiesRating"],
        "ceoRating": company_data_full["ratings"]["ceoRating"],
        "compensationAndBenefitsRating": company_data_full["ratings"]["compensationAndBenefitsRating"],
        "cultureAndValuesRating": company_data_full["ratings"]["cultureAndValuesRating"],
        "diversityAndInclusionRating": company_data_full["ratings"]["diversityAndInclusionRating"],
        "seniorManagementRating": company_data_full["ratings"]["seniorManagementRating"],
        "workLifeBalanceRating": company_data_full["ratings"]["workLifeBalanceRating"],
        "glassdoorUrl": company_data_url
    }
async def get_company_data(company: str) -> Dict:
    with get_driver() as client:
        try:
            t = time.time()
            #block execution until we find the companies
            companies : list[FoundCompany] = await find_companies(company, client)
            logging.info(f"Getting companies took {time.time() - t} seconds")
            t = time.time()
            #Grab the url to the company
            if not len(companies):
                return {
                    "overallRating": None,
                    "businessOutlookRating": None,
                    "careerOpportunitiesRating": None,
                    "ceoRating": None,
                    "compensationAndBenefitsRating": None,
                    "cultureAndValuesRating": None,
                    "diversityAndInclusionRating": None,
                    "seniorManagementRating": None,
                    "workLifeBalanceRating": None,
                    "glassdoorUrl": None
                }
            company_data_url : str = companies[0]["url_reviews"]
            logging.info("Company Data Url: "+company_data_url)
            #Await scraping the company data from json embeded in the html
            company_data_full : Dict = await scrape_cache(company_data_url, client)
            logging.info(f"Scraping cache took {time.time() - t} seconds")
        except Exception as e:
            logging.error(f"ERROR!!!: GOT GLASSDOOR ERROR OF {e}")
            return {
                    "overallRating": None,
                    "businessOutlookRating": None,
                    "careerOpportunitiesRating": None,
                    "ceoRating": None,
                    "compensationAndBenefitsRating": None,
                    "cultureAndValuesRating": None,
                    "diversityAndInclusionRating": None,
                    "seniorManagementRating": None,
                    "workLifeBalanceRating": None,
                    "glassdoorUrl": None
            }
        finally:
            CookieManager.dump_cookies(client)
            client.quit()
    logging.info(json.dumps(company_data_full, indent=2))
    return {
        "overallRating": company_data_full["ratings"]["overallRating"],
        "businessOutlookRating": company_data_full["ratings"]["businessOutlookRating"],
        "careerOpportunitiesRating": company_data_full["ratings"]["careerOpportunitiesRating"],
        "ceoRating": company_data_full["ratings"]["ceoRating"],
        "compensationAndBenefitsRating": company_data_full["ratings"]["compensationAndBenefitsRating"],
        "cultureAndValuesRating": company_data_full["ratings"]["cultureAndValuesRating"],
        "diversityAndInclusionRating": company_data_full["ratings"]["diversityAndInclusionRating"],
        "seniorManagementRating": company_data_full["ratings"]["seniorManagementRating"],
        "workLifeBalanceRating": company_data_full["ratings"]["workLifeBalanceRating"],
        "glassdoorUrl": company_data_url
    }
class Region(Enum):
    """glassdoor.com region codes"""

    UNITED_STATES = "1"
    UNITED_KINGDOM = "2"
    CANADA_ENGLISH = "3"
    INDIA = "4"
    AUSTRALIA = "5"
    FRANCE = "6"
    GERMANY = "7"
    SPAIN = "8"
    BRAZIL = "9"
    NETHERLANDS = "10"
    AUSTRIA = "11"
    MEXICO = "12"
    ARGENTINA = "13"
    BELGIUM_NEDERLANDS = "14"
    BELGIUM_FRENCH = "15"
    SWITZERLAND_GERMAN = "16"
    SWITZERLAND_FRENCH = "17"
    IRELAND = "18"
    CANADA_FRENCH = "19"
    HONG_KONG = "20"
    NEW_ZEALAND = "21"
    SINGAPORE = "22"
    ITALY = "23"

class FoundCompany(TypedDict):
    """type hint for company search result"""
    name: str
    id: str
    url_overview: str
    url_jobs: str
    url_reviews: str
    url_salaries: str
async def find_companies(query: str, session: WebDriver) -> List[FoundCompany]:
    """find company Glassdoor ID and name by query. e.g. "ebay" will return "eBay" with ID 7853"""
    logging.debug("URL: " + f"https://www.glassdoor.com/api-web/employer/find.htm?autocomplete=true&maxEmployersForAutocomplete=10&term={query}")
    # Set a realistic timeout
    # UPDATE, now set upstream
    url = f"https://www.glassdoor.com/api-web/employer/find.htm?autocomplete=true&maxEmployersForAutocomplete=10&term={query}"
    logging.debug("URL: "+ url)
    session.get(url)
    result: str = session.find_element(By.XPATH, "/html/body").text
    try:
        data = json.loads(result)
    except Exception as e:
        time.sleep(100)
        logging.error("DATA CONVERSION FAILED FOR: " + result)
        raise e
    companies = []
    for result in data:
        companies.append(
            {
                "name": result["label"],
                "id": result["id"],
                "url_overview": Url.overview(result["label"], result["id"]),
                "url_jobs": Url.jobs(result["label"], result["id"]),
                "url_reviews": Url.reviews(result["label"], result["id"]),
                "url_salaries": Url.salaries(result["label"], result["id"]),
            }
        )
    return companies
class Url:
    """
    Helper URL generator that generates full URLs for glassdoor.com pages
    from given employer name and ID
    For example:
    > GlassdoorUrl.overview("eBay Motors Group", "4189745")
    https://www.glassdoor.com/Overview/Working-at-eBay-Motors-Group-EI_IE4189745.11,28.htm

    Note that URL formatting is important when it comes to scraping Glassdoor
    as unusual URL formats can lead to scraper blocking.
    """

    @staticmethod
    def overview(employer: str, employer_id: str, region: Optional[Region] = None) -> str:
        employer = employer.replace(" ", "-")
        url = f"https://www.glassdoor.com/Overview/Working-at-{employer}-EI_IE{employer_id}"
        # glassdoor is allowing any prefix for employer name and
        # to indicate the prefix suffix numbers are used like:
        # https://www.glassdoor.com/Overview/Working-at-eBay-Motors-Group-EI_IE4189745.11,28.htm
        # 11,28 is the slice where employer name is
        _start = url.split("/Overview/")[1].find(employer)
        _end = _start + len(employer)
        url += f".{_start},{_end}.htm"
        if region:
            return url + f"?filter.countryId={region.value}"
        return url

    @staticmethod
    def reviews(employer: str, employer_id: str, region: Optional[Region] = None) -> str:
        employer = employer.replace(" ", "-")
        url = f"https://www.glassdoor.com/Reviews/{employer}-Reviews-E{employer_id}.htm?"
        if region:
            return url + f"?filter.countryId={region.value}"
        return url

    @staticmethod
    def salaries(employer: str, employer_id: str, region: Optional[Region] = None) -> str:
        employer = employer.replace(" ", "-")
        url = f"https://www.glassdoor.com/Salary/{employer}-Salaries-E{employer_id}.htm?"
        if region:
            return url + f"?filter.countryId={region.value}"
        return url

    @staticmethod
    def jobs(employer: str, employer_id: str, region: Optional[Region] = None) -> str:
        employer = employer.replace(" ", "-")
        url = f"https://www.glassdoor.com/Jobs/{employer}-Jobs-E{employer_id}.htm?"
        if region:
            return url + f"?filter.countryId={region.value}"
        return url

    @staticmethod
    def change_page(url: str, page: int) -> str:
        """update page number in a glassdoor url"""
        if re.search(r"_P\d+\.htm", url):
            new = re.sub(r"(?:_P\d+)*.htm", f"_P{page}.htm", url)
        else:
            new = re.sub(".htm", f"_P{page}.htm", url)
        assert new != url
        return new

