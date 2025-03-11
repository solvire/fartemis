"""
Feed reader clients for job aggregation.

This module provides classes for reading and processing various feed types
(RSS, Atom, custom formats) to extract job postings.
"""

import logging
import hashlib
import feedparser
import requests
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

# Setup logging
logger = logging.getLogger(__name__)

class BaseFeedItem:
    """Standardized job posting data structure."""
    
    def __init__(self, 
                 title: str,
                 description: str,
                 url: str,
                 company_name: Optional[str] = None,
                 location: Optional[str] = None,
                 posted_date: Optional[datetime] = None,
                 source_name: str = "",
                 original_guid: Optional[str] = None,
                 original_data: Optional[Dict] = None):
        self.title = title
        self.description = description
        self.url = url
        self.company_name = company_name
        self.location = location
        self.posted_date = posted_date
        self.source_name = source_name
        self.original_guid = original_guid
        self.original_data = original_data or {}
        
        # Generate a consistent GUID if none provided
        if not self.original_guid:
            self.original_guid = self._generate_guid()
    
    def _generate_guid(self) -> str:
        """Generate a consistent GUID based on URL and title."""
        unique_string = f"{self.url}|{self.title}|{self.source_name}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'title': self.title,
            'description': self.description,
            'url': self.url,
            'company_name': self.company_name,
            'location': self.location,
            'posted_date': self.posted_date.isoformat() if self.posted_date else None,
            'source_name': self.source_name,
            'guid': self.original_guid,
            'original_data': self.original_data
        }


class BaseFeedClient(ABC):
    """Base class for all feed clients."""
    
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
    
    @abstractmethod
    def fetch_jobs(self, **kwargs) -> List[BaseFeedItem]:
        """Fetch jobs from the feed source."""
        pass
    
    def _clean_html(self, html_content: str) -> str:
        """Clean HTML content to plain text."""
        # Simple HTML tag stripping - in production, use a better HTML parser
        import re
        clean_text = re.sub(r'<[^>]+>', ' ', html_content)
        return re.sub(r'\s+', ' ', clean_text).strip()


class RSSFeedClient(BaseFeedClient):
    """Client for standard RSS/Atom feeds."""
    
    def fetch_jobs(self, **kwargs) -> List[BaseFeedItem]:
        """Fetch jobs from RSS feed."""
        try:
            # Parse the feed
            feed = feedparser.parse(self.url)
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"Feed parsing warning for {self.name}: {feed.bozo_exception}")
            
            jobs = []
            for entry in feed.entries:
                try:
                    # Extract standard fields with fallbacks
                    title = getattr(entry, 'title', '')
                    description = getattr(entry, 'description', getattr(entry, 'summary', ''))
                    url = getattr(entry, 'link', '')
                    guid = getattr(entry, 'id', '')
                    
                    # Try to extract date information
                    published = getattr(entry, 'published_parsed', 
                                       getattr(entry, 'updated_parsed', None))
                    if published:
                        posted_date = datetime(*published[:6])
                    else:
                        posted_date = None
                    
                    # Try to extract location and company from title or tags
                    location = None
                    company_name = None
                    
                    # Look for company in specific feed elements
                    if hasattr(entry, 'author'):
                        company_name = entry.author
                    
                    # Try to extract from tags if available
                    if hasattr(entry, 'tags'):
                        for tag in entry.tags:
                            tag_term = getattr(tag, 'term', '')
                            # Check if tag looks like a location
                            if any(loc_term in tag_term.lower() for loc_term in 
                                  ['remote', 'onsite', 'hybrid', 'location']):
                                location = tag_term
                            # Check if tag looks like a company
                            elif any(comp_term in tag_term.lower() for comp_term in 
                                    ['company', 'employer']):
                                company_name = tag_term
                    
                    # Create standardized job item
                    job = BaseFeedItem(
                        title=title,
                        description=self._clean_html(description),
                        url=url,
                        company_name=company_name,
                        location=location,
                        posted_date=posted_date,
                        source_name=self.name,
                        original_guid=guid,
                        original_data=entry
                    )
                    jobs.append(job)
                
                except Exception as e:
                    logger.error(f"Error processing entry in {self.name}: {e}")
                    continue
            
            logger.info(f"Fetched {len(jobs)} jobs from {self.name}")
            return jobs
            
        except Exception as e:
            logger.error(f"Error fetching from {self.name}: {e}")
            return []


class HackerNewsWhoIsHiringClient(BaseFeedClient):
    """Client for Hacker News 'Who is Hiring' monthly threads."""
    
    def __init__(self, name="hackernews_hiring", thread_id=None):
        # If no thread_id provided, we'll need to find the latest one
        self.thread_id = thread_id
        super().__init__(name, f"https://news.ycombinator.com/item?id={thread_id}" if thread_id else "")
    
    def _find_latest_thread_id(self) -> Optional[str]:
        """Find the latest 'Who is hiring' thread ID."""
        try:
            # Try to find from the Hacker News API
            response = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            top_stories = response.json()
            
            # Check top stories for "Who is hiring" in title
            for story_id in top_stories[:100]:  # Check only top 100
                story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                story = requests.get(story_url).json()
                
                if story.get('title', '').lower().startswith("ask hn: who is hiring"):
                    return str(story_id)
            
            # Fallback to known pattern - first weekday of month
            # This is a simplification - in production, implement a more robust method
            return None
            
        except Exception as e:
            logger.error(f"Error finding latest HN hiring thread: {e}")
            return None
    
    def fetch_jobs(self, **kwargs) -> List[BaseFeedItem]:
        """Fetch jobs from Hacker News 'Who is Hiring' thread."""
        if not self.thread_id:
            self.thread_id = self._find_latest_thread_id()
            if not self.thread_id:
                logger.error("Could not find latest HN hiring thread")
                return []
            self.url = f"https://news.ycombinator.com/item?id={self.thread_id}"
        
        try:
            # Fetch the thread via HN API
            response = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{self.thread_id}.json")
            thread = response.json()
            
            if not thread or 'kids' not in thread:
                logger.error(f"Invalid HN thread or no comments: {self.thread_id}")
                return []
            
            jobs = []
            for comment_id in thread.get('kids', []):
                try:
                    # Fetch each comment
                    comment_url = f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json"
                    comment = requests.get(comment_url).json()
                    
                    if not comment or 'text' not in comment or comment.get('deleted', False):
                        continue
                    
                    text = comment.get('text', '')
                    
                    # Parse the comment text which usually follows a pattern
                    # Like: "Company Name | Location | Position | URL"
                    lines = text.split('<p>')
                    first_line = lines[0]
                    
                    # Try to extract structured data
                    parts = [p.strip() for p in first_line.split('|')]
                    
                    title = "Job Opening"
                    company_name = None
                    location = None
                    url = None
                    
                    if len(parts) >= 1:
                        company_name = self._clean_html(parts[0])
                    
                    if len(parts) >= 2:
                        location = self._clean_html(parts[1])
                    
                    # Try to find position information
                    if len(parts) >= 3:
                        title = self._clean_html(parts[2])
                    
                    # Try to find URL in the text
                    import re
                    url_match = re.search(r'https?://[^\s<>"]+', text)
                    if url_match:
                        url = url_match.group(0)
                    else:
                        # Use HN comment URL as fallback
                        url = f"https://news.ycombinator.com/item?id={comment_id}"
                    
                    # Create job item
                    job = BaseFeedItem(
                        title=title,
                        description=self._clean_html(text),
                        url=url,
                        company_name=company_name,
                        location=location,
                        posted_date=datetime.fromtimestamp(comment.get('time', 0)),
                        source_name=self.name,
                        original_guid=f"hn-{comment_id}",
                        original_data=comment
                    )
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error processing HN comment {comment_id}: {e}")
                    continue
            
            logger.info(f"Fetched {len(jobs)} jobs from HN Who Is Hiring")
            return jobs
            
        except Exception as e:
            logger.error(f"Error fetching from HN Who Is Hiring: {e}")
            return []


class RedditJobBoardClient(BaseFeedClient):
    """Client for Reddit job board subreddits."""
    
    def __init__(self, name: str, subreddit: str):
        self.subreddit = subreddit
        url = f"https://www.reddit.com/r/{subreddit}/new.json?sort=new"
        super().__init__(name, url)
    
    def fetch_jobs(self, **kwargs) -> List[BaseFeedItem]:
        """Fetch jobs from Reddit."""
        try:
            # Custom headers to avoid Reddit API blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 Fartemis Job Aggregator (Python/3.8)'
            }
            response = requests.get(self.url, headers=headers)
            data = response.json()
            
            if 'data' not in data or 'children' not in data['data']:
                logger.error(f"Invalid Reddit response format for {self.name}")
                return []
            
            jobs = []
            for post in data['data']['children']:
                try:
                    post_data = post['data']
                    
                    # Skip if not a job post (simple heuristic)
                    title = post_data.get('title', '').lower()
                    if not any(term in title for term in ['hiring', 'job', 'position', 'career']):
                        continue
                    
                    # Create job item
                    job = BaseFeedItem(
                        title=post_data.get('title', ''),
                        description=post_data.get('selftext', ''),
                        url=f"https://www.reddit.com{post_data.get('permalink', '')}",
                        posted_date=datetime.fromtimestamp(post_data.get('created_utc', 0)),
                        source_name=f"reddit_{self.subreddit}",
                        original_guid=post_data.get('id', ''),
                        original_data=post_data
                    )
                    
                    # Try to extract company and location from title
                    # Common patterns like "[HIRING] Position at Company | Location"
                    import re
                    company_match = re.search(r'at\s+([A-Za-z0-9\s]+)', title)
                    if company_match:
                        job.company_name = company_match.group(1).strip()
                    
                    location_match = re.search(r'\|\s*([A-Za-z0-9,\s]+)', title)
                    if location_match:
                        job.location = location_match.group(1).strip()
                    
                    jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error processing Reddit post: {e}")
                    continue
            
            logger.info(f"Fetched {len(jobs)} jobs from Reddit {self.subreddit}")
            return jobs
            
        except Exception as e:
            logger.error(f"Error fetching from Reddit {self.subreddit}: {e}")
            return []


class FeedAggregator:
    """Aggregates jobs from multiple feed sources."""
    
    def __init__(self):
        self.feed_clients = []
    
    def add_client(self, client: BaseFeedClient):
        """Add a feed client to the aggregator."""
        self.feed_clients.append(client)
    
    def fetch_all_jobs(self, **kwargs) -> List[BaseFeedItem]:
        """Fetch jobs from all registered sources."""
        all_jobs = []
        
        for client in self.feed_clients:
            try:
                jobs = client.fetch_jobs(**kwargs)
                all_jobs.extend(jobs)
                logger.info(f"Added {len(jobs)} jobs from {client.name}")
            except Exception as e:
                logger.error(f"Error fetching from {client.name}: {e}")
        
        return all_jobs


