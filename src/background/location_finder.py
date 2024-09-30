#(c) 2024 Daniel DeMoney. All rights reserved.
from flask import request
import requests
import aiohttp
from typing import Dict
import os
from location import Location
from io import BytesIO
import json
import time
from datetime import datetime, timedelta

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class LocationFinder:
    base_url : str = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

    def get_next_monday_7am_timestamp() -> int:
        """Returns the Unix timestamp for the next available Monday at 7:00 AM, at least a week away."""
        # Get current local time
        now = datetime.now()

        # Calculate the number of days until the next Monday
        days_until_monday = (7 - now.weekday()) % 7 + 7  # At least 7 days away

        # Create the timestamp for the next Monday at 7:00 AM
        next_monday_7am = now + timedelta(days=days_until_monday)
        next_monday_7am = next_monday_7am.replace(hour=7, minute=0, second=0, microsecond=0)

        # Convert the datetime to a Unix timestamp
        return int(time.mktime(next_monday_7am.timetuple()))

    def get_next_monday_5pm_timestamp() -> int:
        """Returns the Unix timestamp for the next available Monday at 5:00 PM, at least a week away."""
        # Get current local time
        now = datetime.now()

        # Calculate the number of days until the next Monday
        days_until_monday = (7 - now.weekday()) % 7 + 7  # At least 7 days away

        # Create the timestamp for the next Monday at 5:00 PM
        next_monday_5pm = now + timedelta(days=days_until_monday)
        next_monday_5pm = next_monday_5pm.replace(hour=17, minute=0, second=0, microsecond=0)

        # Convert the datetime to a Unix timestamp
        return int(time.mktime(next_monday_5pm.timetuple()))
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
        print(type(company))
        print(company)
        assert(type(company) == str)
        query : str = f"{company}, {location_str}"
        print("Sending request to read company location with query: " +  query)
        google_places_url : str = LocationFinder.base_url + f"?input={query}&inputtype=textquery&fields=name,formatted_address,geometry&key={GOOGLE_API_KEY}"
        response : requests.Response = requests.get(google_places_url)
        data : Dict = response.json()
        if 'candidates' in data and data['candidates']:
            return Location.create_from_google_places_response(data['candidates'][0])
        else:
            return None
    #Sync because we dont have a reason for it to be async
    def get_directions(origin_latitude: float, origin_longitude: float, destination_latitude: float, destination_longitude: float, returning=False) -> Dict:
        # Make a request to Google Directions API
        directions_url = 'https://maps.googleapis.com/maps/api/directions/json'
        params = {
            'origin': f"{origin_latitude},{origin_longitude}",
            'destination': f"{destination_latitude},{destination_longitude}",
            'key': GOOGLE_API_KEY,
            'departure_time': LocationFinder.get_next_monday_5pm_timestamp() if returning else LocationFinder.get_next_monday_7am_timestamp() 
        }
        response : requests.Response = requests.get(directions_url, params=params)

        data = response.json()

        if data['status'] == 'OK':
            # Extract the polyline and duration from the response
            polyline = data['routes'][0]['overview_polyline']['points']
            arriving_duration = data['routes'][0]['legs'][0]['duration']
            duration_in_traffic = data['routes'][0]['legs'][0].get('duration_in_traffic', {})

            static_map_url = f'https://maps.googleapis.com/maps/api/staticmap?size=600x400&path=weight:5|color:blue|enc:{polyline}&key={GOOGLE_API_KEY}'
            map_response = requests.get(static_map_url)

            if map_response.status_code == 200:
                # Return both the image and the duration
                image_bytes = BytesIO(map_response.content)
                return {
                    'arrivingTrafficDuration': duration_in_traffic,
                    'arrivingDuration': arriving_duration,
                    'mapImage': image_bytes.getvalue().decode('latin1')  # Encoding to pass binary data as a string
                }
            else:
                print("Failed to get map with: " + str(map_response.status_code))
                print("Data:")
                print(json.dumps(data))
                print("args:")
                print(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude, 
                              "destination_latitude": destination_latitude, "destination_longitude": destination_longitude}))
                return None
        else:
            print("Failed to get directions with: " + data['status'])
            print("Data:")
            print(json.dumps(data))
            print("args:")
            print(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude, 
                              "destination_latitude": destination_latitude, "destination_longitude": destination_longitude}))
            return None
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
                    print(f"Failed to get map with status code: {map_response.status}")
                    print("args:")
                    print(json.dumps({"origin_latitude": origin_latitude, "origin_longitude": origin_longitude}))
                    return None
        
