import json
from selenium import webdriver
import requests
import os
import logging
import threading

class CookieManager:

    lock = threading.Lock()

    @staticmethod
    def dump_cookies(driver: webdriver.Firefox, 
                     filename: str = os.path.join(os.getcwd(), 'src', 'background', 'cookies', 'cookies.json')):
        """Dump cookies from the browser instance to a JSON file."""
        # Acquire the lock
        with CookieManager.lock:
            # Get cookies from the Selenium browser
            cookies = driver.get_cookies()

            # Write the cookies to the JSON file
            with open(filename, 'w') as f:
                json.dump(cookies, f)

    @staticmethod
    def load_cookies(driver: webdriver.Firefox, 
                     filename: str = os.path.join(os.getcwd(), 'src', 'background', 'cookies', 'cookies.json')):
        """Load cookies from a JSON file into the Selenium browser."""
        # Acquire the lock
        with CookieManager.lock:
            # Check if the file exists
            if not os.path.exists(filename):
                logging.critical("COULD NOT FIND COOKIE FILE")
                logging.critical(filename)
                raise OSError

            # Load cookies from the JSON file
            with open(filename, 'r') as f:
                cookies = json.load(f)

            # Add each cookie to the Selenium browser
            for cookie in cookies:
                driver.add_cookie(cookie)