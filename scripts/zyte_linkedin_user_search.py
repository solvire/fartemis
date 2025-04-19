#!/usr/bin/env python
# -*- coding: utf-8 -*-

# THIS DID NOT WORK

import requests
from bs4 import BeautifulSoup
import urllib.parse

# Zyte API configuration
ZYTE_API_KEY = ""  # Replace with your Zyte API key
ZYTE_API_URL = "https://api.zyte.com/v1/extract"

def get_linkedin_handle(first_name, last_name):
    """
    Look up a LinkedIn user's profile handle by first and last name using Zyte API.
    
    Args:
        first_name (str): User's first name
        last_name (str): User's last name
    
    Returns:
        str: LinkedIn profile URL (handle) or None if not found
    """
    # Construct LinkedIn search URL
    search_query = f"{first_name} {last_name}"
    encoded_query = urllib.parse.quote(search_query)
    linkedin_search_url = f"https://www.linkedin.com/search/results/people/?keywords={encoded_query}&origin=SWITCH_SEARCH_VERTICAL"

    # Zyte API request payload
    payload = {
        "url": linkedin_search_url,
        "httpResponseBody": True,
        "browserHtml": True  # Use browserHtml to handle dynamic content
    }

    # Set headers with Zyte API key
    headers = {
        "Authorization": f"Basic {ZYTE_API_KEY}:",
        "Content-Type": "application/json"
    }

    try:
        # Send request to Zyte API
        response = requests.post(ZYTE_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Extract HTML content (base64 encoded in Zyte's response)
        if "browserHtml" in data:
            html_content = data["browserHtml"]
        else:
            raise ValueError("No browserHtml content in response")

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the first profile link in search results
        # LinkedIn search results typically have profile links in <a> tags with class 'app-aware-link'
        profile_link = soup.find("a", class_="app-aware-link")
        
        if profile_link and "href" in profile_link.attrs:
            href = profile_link["href"]
            # Extract the LinkedIn profile URL (e.g., https://www.linkedin.com/in/username)
            if "/in/" in href:
                # Clean the URL to get only the profile handle
                profile_url = href.split("?")[0]  # Remove any query parameters
                return profile_url
        
        print(f"No profile found for {search_query}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error with Zyte API request: {e}")
        return None
    except Exception as e:
        print(f"Error parsing response: {e}")
        return None

# Example usage
if __name__ == "__main__":
    first_name = "Olivia"
    last_name = "Melman"
    linkedin_handle = get_linkedin_handle(first_name, last_name)
    if linkedin_handle:
        print(f"LinkedIn handle: {linkedin_handle}")
    else:
        print("Could not retrieve LinkedIn handle")