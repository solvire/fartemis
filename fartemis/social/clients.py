# -*- coding: utf-8 -*-
"""
Author: solvire
Date: 2025-02-27

Client classes for talking to the social APIs
"""
from abc import ABC, abstractmethod
from django.conf import settings
import logging
import requests
import json
from datetime import datetime, timezone

from . import constants
from . import exceptions
from . import models

logger = logging.getLogger(__name__)


class BaseAPIClient(ABC):
    """
    A base client for communicating with an API
    """

    auth_token = None
    username = None
    password = None
    base_url = None
    headers = {
        "Content-Type": "application/json",
        "Content-Accept": "application/json",
        "User-Agent": "Fartemis/1.0"
    }

    @abstractmethod
    def set_authentication(self, **kwargs):
        """
        used in the local
        """
        pass

    @abstractmethod
    def check_credentials(self) -> dict:
        """
        see if this account is active
        """
        pass


# Existing code here...


class BlueskyClient(BaseAPIClient):
    """
    Client for connecting to Bluesky/AT Protocol using the official atproto SDK
    """
    
    client = None
    profile = None

    def set_authentication(self, **kwargs):
        """
        Set up authentication parameters for Bluesky
        """
        if "base_url" not in kwargs:
            raise exceptions.ClientInitializationException("base_url not present.")
        self.base_url = kwargs["base_url"]
        
        self.username = kwargs.get("username")
        self.password = kwargs.get("password")  # App password for Bluesky
        
        # Initialize the atproto Client
        self.client = Client(self.base_url)

    def authenticate(self):
        """
        Authenticate with Bluesky using the atproto SDK
        """
        logger.info(f"Authenticating with Bluesky as {self.username}")
        
        try:
            self.profile = self.client.login(self.username, self.password)
            self.did = self.profile.did
            
            logger.info(f"Successfully authenticated with Bluesky. DID: {self.did}")
            return self.profile
            
        except Exception as e:
            logger.error(f"Authentication with Bluesky failed: {str(e)}")
            return None

    def check_credentials(self) -> dict:
        """
        Verify the current authentication status with Bluesky
        """
        if not self.client or not getattr(self.client, 'me', None):
            return self.authenticate()
            
        try:
            # Get current session info to verify credentials are still valid
            profile = self.client.app.bsky.actor.getProfile({'actor': self.did})
            return profile
            
        except Exception as e:
            logger.error(f"Failed to verify Bluesky credentials: {str(e)}")
            
            # Try re-authenticating
            return self.authenticate()

    def get_profile(self, actor):
        """
        Get a user's profile information
        
        Args:
            actor (str): The handle or DID of the user
            
        Returns:
            dict: Profile information or None if request fails
        """
        if not self.client and not self.authenticate():
            logger.error("Not authenticated with Bluesky")
            return None
            
        try:
            profile = self.client.app.bsky.actor.getProfile({'actor': actor})
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get Bluesky profile for {actor}: {str(e)}")
            return None

    def create_post(self, text, reply_to=None, media=None):
        """
        Create a new post on Bluesky
        
        Args:
            text (str): The text content of the post
            reply_to (dict, optional): Reply reference if this is a reply
            media (list, optional): List of media attachments
            
        Returns:
            dict: Response data or None if request fails
        """
        if not self.client and not self.authenticate():
            logger.error("Not authenticated with Bluesky")
            return None
            
        try:
            # Use the SDK's send_post method
            response = self.client.send_post(text=text, reply_to=reply_to, media=media)
            return response
            
        except Exception as e:
            logger.error(f"Failed to create Bluesky post: {str(e)}")
            return None

    def get_timeline(self, limit=50):
        """
        Get the authenticated user's home timeline
        
        Args:
            limit (int): Maximum number of posts to return
            
        Returns:
            dict: Timeline data or None if request fails
        """
        if not self.client and not self.authenticate():
            logger.error("Not authenticated with Bluesky")
            return None
            
        try:
            timeline = self.client.app.bsky.feed.getTimeline({'limit': limit})
            return timeline
            
        except Exception as e:
            logger.error(f"Failed to get Bluesky timeline: {str(e)}")
            return None

    def get_user_posts(self, actor, limit=50):
        """
        Get posts from a specific user
        
        Args:
            actor (str): The handle or DID of the user
            limit (int): Maximum number of posts to return
            
        Returns:
            dict: User posts data or None if request fails
        """
        if not self.client and not self.authenticate():
            logger.error("Not authenticated with Bluesky")
            return None
            
        try:
            feed = self.client.app.bsky.feed.getAuthorFeed({'actor': actor, 'limit': limit})
            return feed
            
        except Exception as e:
            logger.error(f"Failed to get posts for {actor}: {str(e)}")
            return None


# Modify the APIClientFactory to include Bluesky
class APIClientFactory(object):
    """
    Get the appropriate client or die
    The name must match the identifier field in the provider table
    Using strings like poor people
    There may be overlapping clients for brokerages
    """

    @staticmethod
    def generate(client_name, is_staging=True, set_default_authentication=True):
        """
        Poorman's case statement for factory pattern
        If you want to set the authentication yourself then toggle the boolean
        """

            
        # bluesky
        if client_name == constants.Social.BLUESKY:
            api_client = BlueskyClient()
            api_client.set_authentication(
                username=settings.BLUESKY_USERNAME,
                password=settings.BLUESKY_PASSWORD,
                base_url=settings.BLUESKY_BASE_URL
            )
            return api_client

        raise exceptions.ClientInitializationException(
            "No valid client found for {}".format(client_name)
        )
