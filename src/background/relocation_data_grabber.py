#(c) 2024 Daniel DeMoney. All rights reserved.
import aiohttp
import asyncio
import json
import os
import time
import pandas as pd
from typing import Dict
from location import Location
from location_finder import LocationFinder
import logging

WALK_SCORE_KEY = os.environ["WALK_SCORE_KEY"]
HUD_KEY = os.environ["HUD_KEY"]
US_CENSUS_KEY = os.environ["US_CENSUS_KEY"]

class RelocationDataGrabber:
    zip_to_cbsa = pd.read_excel(os.path.join(os.getcwd(),"src", "background", "misc", "ZIP_CBSA_062024.xlsx"), dtype={'ZIP': str, 'CBSA': str})
    walk_score_url: str = "https://api.walkscore.com/score"
    hud_url: str = "https://www.huduser.gov/hudapi/public/fmr/data/"
    #census website said happy querying once you sign up and I nearly cried how nice
    #I'm tearing up rn
    census_url: str = "https://api.census.gov/data/2022/acs/acsse"
    def get_cbsa(zip_code):
        logging.info(f"Getting CBSA for {zip_code}")
        row = RelocationDataGrabber.zip_to_cbsa[RelocationDataGrabber.zip_to_cbsa['ZIP'] == zip_code]
        if not row.empty:
            return row['CBSA'].values[0]
        return None
    async def get_fips_code(location: Location) -> str:
        """
        Get the FIPS code based on latitude and longitude using the U.S. Census Bureau API.

        Args:
            location (Location): A Location object containing latitude and longitude.

        Returns:
            str: The FIPS code or an error message.
        """
        if location.latitude is None or location.longitude is None:
            return "Latitude and longitude are required to get FIPS code."

        # U.S. Census Geocoding Services API URL
        url = "https://geo.fcc.gov/api/census/block/find"

        # API query parameters
        params = {
            'latitude': location.latitude,
            'longitude': location.longitude,
            'format': 'json'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logging.debug(json.dumps(data, indent=2))
                    # Return FIPS code
                    return data.get('County', {}).get('FIPS', 'FIPS code not found')

        except aiohttp.ClientError as e:
            return f"Error occurred while fetching FIPS code: {str(e)}"
    async def get_walkability(location: Location):
        logging.info("Grabbing walkability...")
        params = {
            "format": "json",
            "lat": location.latitude,
            "lon": location.longitude,
            "address": location.address_str + " " + location.city + " " + location.state_code + " " + location.zip_code,
            "transit": 1,
            "bike": 1,
            "wsapikey": WALK_SCORE_KEY
        }
        headers = {
            "Referer": "https://demoney.net"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(RelocationDataGrabber.walk_score_url, params=params, headers=headers) as response:
                response_json = await response.json()
                logging.debug(json.dumps(response_json, indent=2))
                if response_json["status"] == 1:
                    return response_json
                return None
    
    async def get_fmr(location: Location):
        fips_code = await RelocationDataGrabber.get_fips_code(location)
        if not fips_code:
            logging.error("Failed to find a valid FIPS code, returning None")
            return None
    
        logging.info("Grabbing rent...")
        headers = {
            "Authorization": f"Bearer {HUD_KEY}"
        }
        url = f'https://www.huduser.gov/hudapi/public/fmr/data/{fips_code}99999'
    
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logging.error(f"Request failed with status code {response.status}")
                        return None
                    try:
                        response_json = await response.json()
                        logging.debug(json.dumps(response_json, indent=2))
                    except aiohttp.ContentTypeError:
                        logging.error("Response is not in JSON format")
                        return None

                    candidate = response_json.get("data", {}).get("basicdata")
                    if isinstance(candidate, list):
                        for subcandidate in candidate:
                            if subcandidate.get("zip_code") == location.zip_code:
                                return subcandidate.get("One-Bedroom")
                        return candidate[0].get("One-Bedroom") if candidate else None
                
                    rent = candidate.get("One-Bedroom")
                    logging.info(f"Got one-bedroom rent of {rent}")
                    return rent
        except Exception as e:
            logging.error(f"An error occurred while fetching FMR data: {e}")
            return None

    async def get_household_income(location: Location):
        logging.info("Grabbing Household income...")
        cbsa_code = RelocationDataGrabber.get_cbsa(location.zip_code)
        if not cbsa_code:
            logging.error("Failed to find a valid CBSA code, returning none")
            return None
        params = {
            "get": "K201902_001E",
            "for": f"metropolitan statistical area/micropolitan statistical area:{cbsa_code}",
            "key": US_CENSUS_KEY
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(RelocationDataGrabber.census_url, params=params) as response:
                if response.status == 200:
                    response_text = await response.text()
                    logging.debug(response_text)
                    response_json = await response.json()
                    logging.debug(json.dumps(response_json, indent=2))
                    return int(response_json[1][0])
                else:
                    return None

    async def get_data(location : Location):
        walkability_task = RelocationDataGrabber.get_walkability(location)
        fmr_task = RelocationDataGrabber.get_fmr(location)
        income_task = RelocationDataGrabber.get_household_income(location)
        map_task = LocationFinder.get_location_map_async(location.latitude, location.longitude)  # The async function for fetching the map
        
        # Run all tasks concurrently
        results = await asyncio.gather(walkability_task, fmr_task, income_task, map_task)
        
        walkability, fmr, income, map_image = results
        return {
            "walkability": walkability,
            "fmr": fmr,
            "income": income,
            "mapImage": map_image['mapImage']  # Extracting map image from the result
    }
