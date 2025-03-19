from django.core.management.base import BaseCommand
import requests
import logging
import json
from urllib.parse import quote

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Find LinkedIn GeoIDs using the LinkedIn typeahead API'

    def add_arguments(self, parser):
        parser.add_argument('location', type=str, help='Location to search for')
        parser.add_argument('--output', type=str, default=None, help='Output file path for JSON results')
        parser.add_argument('--limit', type=int, default=10, help='Max number of results to display')

    def handle(self, *args, **options):
        location = options['location']
        output_file = options['output']
        limit = options['limit']
        
        self.stdout.write(f'Searching for GeoID for location: "{location}"...')
        
        # URL encode the query
        encoded_query = quote(location)
        
        # LinkedIn typeahead API URL
        url = (f"https://www.linkedin.com/jobs-guest/api/typeaheadHits?"
               f"query={encoded_query}&"
               f"typeaheadType=GEO&"
               f"geoTypes=POPULATED_PLACE,ADMIN_DIVISION_2,MARKET_AREA,COUNTRY_REGION")
        
        self.stdout.write(f"Accessing LinkedIn typeahead API: {url}")
        
        # Set up headers to simulate a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.linkedin.com/jobs/',
            'DNT': '1',
            'Connection': 'keep-alive',
        }
        
        try:
            # Make request to the typeahead API
            response = requests.get(url, headers=headers)
            
            # Check if successful
            if response.status_code == 200:
                try:
                    results = response.json()
                    
                    if not results:
                        self.stderr.write(self.style.ERROR(f"No locations found for '{location}'"))
                        return None
                    
                    self.stdout.write(self.style.SUCCESS(f"Found {len(results)} locations matching '{location}'"))
                    
                    # Format and display results
                    formatted_results = []
                    for i, location_info in enumerate(results[:limit], 1):
                        geo_id = location_info.get('id')
                        display_name = location_info.get('displayName')
                        geo_type = location_info.get('type')
                        
                        formatted_result = {
                            'geo_id': geo_id,
                            'display_name': display_name,
                            'type': geo_type
                        }
                        formatted_results.append(formatted_result)
                        
                        self.stdout.write(f"\n{i}. {display_name}")
                        self.stdout.write(f"   GeoID: {geo_id}")
                        self.stdout.write(f"   Type: {geo_type}")
                    
                    # Save results to file if requested
                    if output_file:
                        try:
                            with open(output_file, 'w') as f:
                                json.dump(formatted_results, f, indent=2)
                            self.stdout.write(self.style.SUCCESS(f'Results saved to {output_file}'))
                        except Exception as e:
                            self.stderr.write(f'Error saving to {output_file}: {str(e)}')
                    
                    # Print usage example for first result
                    if formatted_results:
                        first_geo_id = formatted_results[0]['geo_id']
                        self.stdout.write("\nHow to use GeoID with LinkedIn API:")
                        self.stdout.write(f"python manage.py linkedin_jobs_geoid --keywords='Python Engineer' --geo-id={first_geo_id}")
                    
                    # return formatted_results
                    
                except ValueError as e:
                    self.stderr.write(self.style.ERROR(f"Error parsing JSON response: {str(e)}"))
                    self.stderr.write(f"Raw response: {response.text[:200]}...")  # Show first 200 chars
                    return None
            else:
                self.stderr.write(self.style.ERROR(f"API request failed with status code {response.status_code}"))
                self.stderr.write(f"Response: {response.text[:200]}...")  # Show first 200 chars
                return None
                
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error accessing LinkedIn API: {str(e)}"))
            return None