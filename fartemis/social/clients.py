# -*- coding: utf-8 -*-
"""
Author: solvire
Date: 2025-02-27

Client classes for talking to the social APIs
"""
from abc import ABC, abstractmethod
from django.conf import settings
import logging
from datetime import datetime, timedelta

from github import Github, GithubException
from atproto import Client as Bluesky, client_utils

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
    https://atproto.blue/en/latest/atproto_client/index.html#atproto_client.Client
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
        self.client = Bluesky()

    def authenticate(self):
        """
        Authenticate with Bluesky using the atproto SDK
        
        Returns:
            Profile data or None if authentication fails
        """
        logger.info(f"Authenticating with Bluesky as {self.username}")
        
        try:
            profile = self.client.login(self.username, self.password)
            self.did = self.client.me.did
            
            logger.info(f"Successfully authenticated with Bluesky. DID: {self.did}")
            return profile
            
        except Exception as e:
            logger.error(f"Authentication with Bluesky failed: {str(e)}")
            return None

    def check_credentials(self) -> dict:
        """
        Verify the current authentication status with Bluesky
        
        Returns:
            Profile data or None if credentials are invalid
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            return self.authenticate()
            
        try:
            profile = self.client.app.bsky.actor.get_profile(self.client.me.did)
            return profile
            
        except Exception as e:
            logger.error(f"Failed to verify Bluesky credentials: {str(e)}")
            return self.authenticate()

    def get_profile(self, actor):
        """
        Get a user's profile information
        
        Args:
            actor (str): The handle or DID of the user
            
        Returns:
            Profile data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            profile = self.client.app.bsky.actor.get_profile(actor)
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
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.send_post(text=text, reply_to=reply_to, embed=media)
            return response
            
        except Exception as e:
            logger.error(f"Failed to create Bluesky post: {str(e)}")
            return None

    def get_timeline(self, algorithm=None, cursor=None, limit=25):
        """
        Get the authenticated user's home timeline
        
        Args:
            algorithm (str, optional): Algorithm
            cursor (str, optional): Cursor of the last like in the previous page
            limit (int, optional): Limit count of posts to return
            
        Returns:
            Timeline data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            timeline = self.client.get_timeline(algorithm=algorithm, cursor=cursor, limit=limit)
            return timeline
            
        except Exception as e:
            logger.error(f"Failed to get Bluesky timeline: {str(e)}")
            return None

    def get_user_posts(self, actor, cursor=None, limit=None, filter=None):
        """
        Get posts from a specific user
        
        Args:
            actor (str): The handle or DID of the user
            cursor (str, optional): Cursor of the last post in the previous page
            limit (int, optional): Limit count of posts to return
            filter (str, optional): Filter (posts_with_replies, posts_with_media, posts_no_replies)
            
        Returns:
            User posts data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            feed = self.client.get_author_feed(actor=actor, cursor=cursor, limit=limit, filter=filter)
            return feed
            
        except Exception as e:
            logger.error(f"Failed to get posts for {actor}: {str(e)}")
            return None
            
    def follow_user(self, actor):
        """
        Follow a user on Bluesky
        
        Args:
            actor (str): The handle or DID of the user to follow
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.follow(actor)
            return response
            
        except Exception as e:
            logger.error(f"Failed to follow user {actor}: {str(e)}")
            return None
            
    def unfollow_user(self, actor):
        """
        Unfollow a user on Bluesky
        
        Args:
            actor (str): The handle or DID of the user to unfollow
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.delete_follow(actor)
            return response
            
        except Exception as e:
            logger.error(f"Failed to unfollow user {actor}: {str(e)}")
            return None
            
    def like_post(self, uri, cid):
        """
        Like a post on Bluesky
        
        Args:
            uri (str): URI of the post to like
            cid (str): CID of the post
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.like(uri, cid)
            return response
            
        except Exception as e:
            logger.error(f"Failed to like post {uri}: {str(e)}")
            return None
            
    def unlike_post(self, uri):
        """
        Unlike a post on Bluesky
        
        Args:
            uri (str): URI of the post to unlike
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.delete_like(uri)
            return response
            
        except Exception as e:
            logger.error(f"Failed to unlike post {uri}: {str(e)}")
            return None
            
    def repost(self, uri, cid):
        """
        Repost a post on Bluesky
        
        Args:
            uri (str): URI of the post to repost
            cid (str): CID of the post
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.repost(uri, cid)
            return response
            
        except Exception as e:
            logger.error(f"Failed to repost {uri}: {str(e)}")
            return None
            
    def delete_repost(self, uri):
        """
        Delete a repost on Bluesky
        
        Args:
            uri (str): URI of the repost to delete
            
        Returns:
            Response data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            response = self.client.delete_repost(uri)
            return response
            
        except Exception as e:
            logger.error(f"Failed to delete repost {uri}: {str(e)}")
            return None
            
    def get_likes(self, uri, cid, cursor=None, limit=None):
        """
        Get likes for a post
        
        Args:
            uri (str): URI of the post
            cid (str): CID of the post
            cursor (str, optional): Cursor of the last like in the previous page
            limit (int, optional): Limit count of likes to return
            
        Returns:
            Likes data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            likes = self.client.get_likes(uri=uri, cid=cid, cursor=cursor, limit=limit)
            return likes
            
        except Exception as e:
            logger.error(f"Failed to get likes for post {uri}: {str(e)}")
            return None
            
    def get_followers(self, actor, cursor=None, limit=None):
        """
        Get followers of a user
        
        Args:
            actor (str): The handle or DID of the user
            cursor (str, optional): Cursor of the last follower in the previous page
            limit (int, optional): Limit count of followers to return
            
        Returns:
            Followers data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            followers = self.client.get_followers(actor=actor, cursor=cursor, limit=limit)
            return followers
            
        except Exception as e:
            logger.error(f"Failed to get followers for {actor}: {str(e)}")
            return None
            
    def get_following(self, actor, cursor=None, limit=None):
        """
        Get users that a user is following
        
        Args:
            actor (str): The handle or DID of the user
            cursor (str, optional): Cursor of the last follow in the previous page
            limit (int, optional): Limit count of follows to return
            
        Returns:
            Following data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
            
        try:
            following = self.client.get_follows(actor=actor, cursor=cursor, limit=limit)
            return following
            
        except Exception as e:
            logger.error(f"Failed to get following for {actor}: {str(e)}")
            return None

    def search_posts(self, query, cursor=None, limit=None):
        """
        Search for posts containing the query
        
        Args:
            query (str): The search query
            cursor (str, optional): Cursor from a previous search
            limit (int, optional): Limit count of results to return
            
        Returns:
            Search results or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
                
        try:
            results = self.client.search_posts(query=query, cursor=cursor, limit=limit)
            return results
            
        except Exception as e:
            logger.error(f"Failed to search posts with query '{query}': {str(e)}")
            return None
            
    def search_users(self, query, cursor=None, limit=None):
        """
        Search for users
        
        Args:
            query (str): The search query
            cursor (str, optional): Cursor from a previous search
            limit (int, optional): Limit count of results to return
            
        Returns:
            Search results or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
                
        try:
            results = self.client.search_actors(query=query, cursor=cursor, limit=limit)
            return results
            
        except Exception as e:
            logger.error(f"Failed to search users with query '{query}': {str(e)}")
            return None
            
    def get_post_thread(self, uri, cid, depth=None):
        """
        Get a thread of posts
        
        Args:
            uri (str): URI of the post
            cid (str): CID of the post
            depth (int, optional): Depth of the thread
            
        Returns:
            Thread data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
                
        try:
            thread = self.client.get_post_thread(uri=uri, cid=cid, depth=depth)
            return thread
            
        except Exception as e:
            logger.error(f"Failed to get thread for post {uri}: {str(e)}")
            return None
            
    def get_notifications(self, cursor=None, limit=None, seen_at=None):
        """
        Get notifications for the authenticated user
        
        Args:
            cursor (str, optional): Cursor from a previous request
            limit (int, optional): Limit count of notifications to return
            seen_at (str, optional): Timestamp when notifications were last seen
            
        Returns:
            Notifications data or None if request fails
        """
        if not self.client or not hasattr(self.client, 'me') or not self.client.me:
            if not self.authenticate():
                logger.error("Not authenticated with Bluesky")
                return None
                
        try:
            notifications = self.client.get_notifications(cursor=cursor, limit=limit, seen_at=seen_at)
            return notifications
            
        except Exception as e:
            logger.error(f"Failed to get notifications: {str(e)}")
            return None
        

class GitHubClient(BaseAPIClient):
    """
    Client for interacting with GitHub's API using PyGithub
    Focused on retrieving commit information for the Fartemis repository
    """
    
    github = None
    
    def set_authentication(self, **kwargs):
        """
        Set up authentication parameters for GitHub using Personal Access Token
        """
        self.base_url = kwargs.get("base_url")  # Not directly used with PyGithub but kept for consistency
        self.token = kwargs.get("password")     # GitHub Personal Access Token
        
        # Initialize PyGithub client with PAT
        try:
            self.github = Github(self.token)
            logger.info("GitHub client initialized with Personal Access Token")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub client: {str(e)}")
            raise exceptions.ClientInitializationException(f"GitHub client initialization failed: {str(e)}")

    def check_credentials(self):
        """
        Verify the GitHub token is valid
        """
        if not self.github:
            return None
            
        try:
            user = self.github.get_user()
            return {
                "login": user.login,
                "name": user.name,
                "valid": True
            }
        except GithubException as e:
            logger.error(f"GitHub authentication failed: {str(e)}")
            return None
    
    def get_repository(self, owner, repo_name):
        """
        Get a repository by owner and name
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            
        Returns:
            github.Repository.Repository: Repository object or None if not found
        """
        if not self.github:
            logger.error("GitHub client not initialized")
            return None
            
        try:
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            return repo
        except GithubException as e:
            logger.error(f"Failed to get repository {owner}/{repo_name}: {str(e)}")
            return None
    
    def get_repository_commits(self, owner, repo_name, since=None, until=None, branch=None):
        """
        Get commits for a specific repository
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            since (datetime, optional): Only commits after this date
            until (datetime, optional): Only commits before this date
            branch (str, optional): Filter by branch name
            
        Returns:
            list: List of commits or empty list if not found
        """
        repo = self.get_repository(owner, repo_name)
        if not repo:
            return []
            
        try:
            # Create kwargs dictionary with only provided parameters
            # This prevents passing None values explicitly
            kwargs = {}
            if branch:
                kwargs['sha'] = branch
            if since:
                kwargs['since'] = since
            if until:
                kwargs['until'] = until
                
            # Get commits with filters
            commits = repo.get_commits(**kwargs)
            
            # Convert to list (handles pagination)
            commit_list = list(commits)
            logger.info(f"Retrieved {len(commit_list)} commits for {owner}/{repo_name}")
            
            return commit_list
        except Exception as e:
            logger.error(f"Failed to get commits for {owner}/{repo_name}: {str(e)}")
            return []
    
    def get_commit_details(self, owner, repo_name, commit_sha):
        """
        Get detailed information about a specific commit
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            commit_sha (str): Commit SHA
            
        Returns:
            github.Commit.Commit: Commit object or None if not found
        """
        repo = self.get_repository(owner, repo_name)
        if not repo:
            return None
            
        try:
            commit = repo.get_commit(commit_sha)
            return commit
        except GithubException as e:
            logger.error(f"Failed to get commit details for {commit_sha}: {str(e)}")
            return None
    
    def get_today_commits(self, owner, repo_name, branch=None):
        """
        Get commits for today
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            branch (str, optional): Filter by branch name
            
        Returns:
            list: List of commits or empty list if not found
        """
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        return self.get_repository_commits(
            owner=owner,
            repo_name=repo_name,
            since=yesterday,
            until=today,
            branch=branch
        )
    
    def get_commit_files(self, owner, repo_name, commit_sha):
        """
        Get files changed in a specific commit
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            commit_sha (str): Commit SHA
            
        Returns:
            list: List of files changed in the commit or empty list if not found
        """
        commit = self.get_commit_details(owner, repo_name, commit_sha)
        if not commit:
            return []
            
        try:
            return commit.files
        except GithubException as e:
            logger.error(f"Failed to get files for commit {commit_sha}: {str(e)}")
            return []
    
    def get_commit_stats(self, owner, repo_name, commit_sha):
        """
        Get statistics for a specific commit
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            commit_sha (str): Commit SHA
            
        Returns:
            dict: Commit statistics or empty dict if not found
        """
        commit = self.get_commit_details(owner, repo_name, commit_sha)
        if not commit:
            return {}
            
        try:
            return {
                'additions': commit.stats.additions,
                'deletions': commit.stats.deletions,
                'total': commit.stats.total
            }
        except GithubException as e:
            logger.error(f"Failed to get stats for commit {commit_sha}: {str(e)}")
            return {}
    
    def get_latest_release(self, owner, repo_name):
        """
        Get the latest release for a repository
        
        Args:
            owner (str): Repository owner
            repo_name (str): Repository name
            
        Returns:
            github.GitRelease.GitRelease: Release object or None if not found
        """
        repo = self.get_repository(owner, repo_name)
        if not repo:
            return None
            
        try:
            releases = repo.get_releases()
            if releases.totalCount > 0:
                return releases[0]
            return None
        except GithubException as e:
            logger.error(f"Failed to get latest release for {owner}/{repo_name}: {str(e)}")
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


        # github
        if client_name == constants.Social.GITHUB:
            api_client = GitHubClient()
            api_client.set_authentication(
                password=settings.GITHUB_ACCESS_TOKEN,  # Just passing the token
                base_url=settings.GITHUB_BASE_URL
            )
            return api_client


        raise exceptions.ClientInitializationException(
            "No valid client found for {}".format(client_name)
        )