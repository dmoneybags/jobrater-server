#(c) 2024 Daniel DeMoney. All rights reserved.
from flask import request
import requests
import asyncio
import aiohttp
from typing import Dict
import os
from location import Location
from io import BytesIO
import json
from datetime import datetime, timedelta, timezone
import pytz
import logging
from timezonefinder import TimezoneFinder

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class LocationFinder:
    base_url : str = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

    def get_time_zone_str_from_lat_and_lng(lat, lng) -> str:
        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lng)
        return timezone_str

    def get_next_monday_timestamp(local_timezone_str: str, hour: int, minute: int) -> int:
        """Returns the Unix timestamp for the next available Monday at the specified hour and minute in the local timezone."""
        
        # Get current UTC time
        now_utc = datetime.now(pytz.utc)

        # Calculate the number of days until the next Monday
        days_until_monday = (7 - now_utc.weekday()) % 7 + 1  # At least 7 days away
        
        # Create a timezone object for the specified local timezone
        local_timezone = pytz.timezone(local_timezone_str)

        # Create the local datetime for the next Monday at the specified time
        next_monday_local = now_utc + timedelta(days=days_until_monday)
        next_monday_local = next_monday_local.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Localize the datetime to the specified timezone
        next_monday_local = local_timezone.localize(next_monday_local)

        # Convert the localized datetime to UTC
        next_monday_utc = next_monday_local.astimezone(pytz.utc)

        # Convert to Unix timestamp
        unix_timestamp = int(next_monday_utc.timestamp())
        logging.info(f"Querying Google Maps with leaving time of {unix_timestamp} (Local: {next_monday_local})")
        return unix_timestamp

    def get_next_monday_5pm_timestamp(local_timezone_str: str) -> int:
        """Returns the Unix timestamp for the next available Monday at 5:00 PM in the specified local timezone."""
        return LocationFinder.get_next_monday_timestamp(local_timezone_str, hour=17, minute=0)

    def get_next_monday_8am_timestamp(local_timezone_str: str) -> int:
        """Returns the Unix timestamp for the next available Monday at 8:00 AM in the specified local timezone."""
        return LocationFinder.get_next_monday_timestamp(local_timezone_str, hour=8, minute=0)
    '''
    try_get_company_address

    queries google places to get location of company office, returns none if no match is found

    args:
        company: string company name
        location_str: the string location, usually something like "Cupertino CA"
    returns:
        Location object or none
    '''
    def try_get_company_address(company : str, location_str : str) -> Location | None:
        logging.info("Querying google places for " + company + " at " + location_str)
        assert(type(company) == str)
        query : str = f"{company}, {location_str}"
        logging.debug("Sending request to read company location with query: " +  query)
        google_places_url : str = LocationFinder.base_url + f"?input={query}&inputtype=textquery&fields=name,formatted_address,geometry&key={GOOGLE_API_KEY}"
        response : requests.Response = requests.get(google_places_url)
        data : Dict = response.json()
        if 'candidates' in data and data['candidates']:
            return Location.create_from_google_places_response(data['candidates'][0])
        else:
            return None
    async def get_directions(
        origin_latitude: float, 
        origin_longitude: float, 
        destination_latitude: float, 
        destination_longitude: float, 
        returning=False
    ) -> Dict:
        # Define the base URL for Google Directions API
        directions_url = 'https://maps.googleapis.com/maps/api/directions/json'
        timezone_str = LocationFinder.get_time_zone_str_from_lat_and_lng(origin_latitude, origin_longitude)
        # Define parameters based on 'returning' flag
        if returning:
            params = {
                'origin': f"{origin_latitude},{origin_longitude}",
                'destination': f"{destination_latitude},{destination_longitude}",
                'key': GOOGLE_API_KEY,
                'departure_time': LocationFinder.get_next_monday_5pm_timestamp(timezone_str),
                'traffic_model': 'pessimistic' 
            }
        else:
            params = {
                'origin': f"{origin_latitude},{origin_longitude}",
                'destination': f"{destination_latitude},{destination_longitude}",
                'key': GOOGLE_API_KEY,
                'departure_time': LocationFinder.get_next_monday_8am_timestamp(timezone_str),
                'traffic_model': 'pessimistic' 
            }

        async with aiohttp.ClientSession() as session:
            # Make the request to get directions
            async with session.get(directions_url, params=params) as response:
                data = await response.json()

                if data['status'] == 'OK':
                    # Extract polyline and duration data
                    polyline = data['routes'][0]['overview_polyline']['points']
                    arriving_duration = data['routes'][0]['legs'][0]['duration']
                    duration_in_traffic = data['routes'][0]['legs'][0].get('duration_in_traffic', {})

                    # Build the static map URL
                    static_map_url = f'https://maps.googleapis.com/maps/api/staticmap?size=600x400&path=weight:5|color:blue|enc:{polyline}&key={GOOGLE_API_KEY}'
                    async with session.get(static_map_url) as map_response:
                        if map_response.status == 200:
                            # Return both image bytes and durations
                            image_bytes = BytesIO(await map_response.read())
                            return {
                                'arrivingTrafficDuration': duration_in_traffic,
                                'arrivingDuration': arriving_duration,
                                'mapImage': image_bytes.getvalue().decode('latin1')  # Encoding to pass binary data as a string
                            }
                        else:
                            logging.error("Failed to get map with status: " + str(map_response.status))
                            logging.error("Data:")
                            logging.error(json.dumps(data))
                            logging.error("args:")
                            logging.error(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude, 
                                        "destination_latitude": destination_latitude, "destination_longitude": destination_longitude}))
                            return None
                else:
                    logging.error("Failed to get directions with status: " + data['status'])
                    logging.error("Data:")
                    logging.error(json.dumps(data))
                    logging.error("args:")
                    logging.error(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude, 
                                    "destination_latitude": destination_latitude, "destination_longitude": destination_longitude}))
                    return None
    async def run_all_directions_queries_in_parallel(
        origin_lat: float, 
        origin_lng: float, 
        dest_lat: float, 
        dest_lng: float):
        response_json, other_way_arriving_json, response_json_reversed, other_way_returning_json = await asyncio.gather(
            LocationFinder.get_directions(float(origin_lat), float(origin_lng), float(dest_lat), float(dest_lng)),
            LocationFinder.get_directions(float(dest_lat), float(dest_lng), float(origin_lat), float(origin_lng)),
            LocationFinder.get_directions(float(dest_lat), float(dest_lng), float(origin_lat), float(origin_lng), returning=True),
            LocationFinder.get_directions(float(dest_lat), float(dest_lng), float(origin_lat), float(origin_lng)),
        )
        return response_json, other_way_arriving_json, response_json_reversed, other_way_returning_json
    
    #Adds whether a drive is in the direction of traffic or goes against it, uses simple queries of the reverse way and compares
    #the times
    def add_traffic_directions(response_json, other_way_arriving_json, other_way_returning_json):
        #if theres less than a 7 min differences its not worth talking about
        if abs(response_json["arrivingDuration"]["value"] - other_way_arriving_json["arrivingDuration"]["value"]) < 7:
            response_json["arrivingTrafficDirection"] = "Neutral"
        else:
            # now that we know the difference is more than 7 min we can just check if its greater than or less than
            if response_json["arrivingDuration"]["value"] > other_way_arriving_json["arrivingDuration"]["value"]:
                response_json["arrivingTrafficDirection"] = "With"
            else:
                response_json["arrivingTrafficDirection"] = "Against"
    
        if abs(response_json["leavingDuration"]["value"] - other_way_returning_json["arrivingDuration"]["value"]) < 10:
            response_json["leavingTrafficDirection"] = "Neutral"
        else:
            if response_json["leavingDuration"]["value"] > other_way_returning_json["arrivingDuration"]["value"]:
                response_json["leavingTrafficDirection"] = "With"
            else:
                response_json["leavingTrafficDirection"] = "Against"
    #Async because we run in parrallel with querying the census and hud apis
    async def get_location_map_async(origin_latitude: float, origin_longitude: float) -> dict:
        static_map_url = 'https://maps.googleapis.com/maps/api/staticmap'
        params = {
            'center': f"{origin_latitude},{origin_longitude}",
            'zoom': 10,  # Adjust zoom level as needed
            'size': '600x400',
            'markers': f"color:red|label:P|{origin_latitude},{origin_longitude}",
            'key': GOOGLE_API_KEY
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(static_map_url, params=params) as map_response:
                if map_response.status == 200:
                    # Read the content of the image as bytes
                    content = await map_response.read()
                    image_bytes = BytesIO(content)
                    return {
                        'mapImage': image_bytes.getvalue().decode('latin1')  # Encoding to pass binary data as a string
                    }
                else:
                    logging.error(f"Failed to get map with status code: {map_response.status}")
                    logging.error("args:")
                    logging.error(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude}))
                    return None
        
