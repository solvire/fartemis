# social/management/commands/test_bluesky.py
"""
The command execution syntax remains the same. Here are the example commands for testing the Bluesky client:
bashCopy# Test authentication only
python manage.py test_bluesky

# Get your own profile
python manage.py test_bluesky --profile=fartemis-alpha.bsky.social

# Get another user's profile
python manage.py test_bluesky --profile=someone-else.bsky.social

# View your timeline
python manage.py test_bluesky --timeline

# Get posts from a specific user
python manage.py test_bluesky --user-posts=some-user.bsky.social

# Create a test post
python manage.py test_bluesky --post --post-text="Testing my new Fartemis Bluesky integration!"

# Combine multiple operations
python manage.py test_bluesky --profile=fartemis-alpha.bsky.social --timeline --limit=20
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from fartemis.social.clients import APIClientFactory
from fartemis.social.constants import Social

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test Bluesky API client functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--post', 
            action='store_true',
            help='Send a test post to Bluesky'
        )
        parser.add_argument(
            '--profile',
            type=str,
            help='Get profile information for a specific Bluesky handle'
        )
        parser.add_argument(
            '--timeline',
            action='store_true',
            help='Get your Bluesky timeline'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Number of items to fetch for timeline or user posts'
        )
        parser.add_argument(
            '--user-posts',
            type=str,
            help='Get posts for a specific Bluesky handle'
        )
        parser.add_argument(
            '--post-text',
            type=str,
            default='Testing the Fartemis Bluesky integration!',
            help='Text to use when creating a test post'
        )

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('Initializing Bluesky client...'))
            
            # Get Bluesky client from factory - this will use settings.BLUESKY_USERNAME and settings.BLUESKY_PASSWORD
            client = APIClientFactory.generate(Social.BLUESKY)
            
            # Test authentication
            self.stdout.write('Testing authentication...')
            auth_result = client.check_credentials()
            
            if not auth_result:
                raise CommandError('Failed to authenticate with Bluesky')
                
            self.stdout.write(self.style.SUCCESS(f'Successfully authenticated as {client.username}'))
            self.stdout.write(f'DID: {client.did}')
            
            # Get profile if requested
            if options['profile']:
                handle = options['profile']
                self.stdout.write(f'Getting profile for {handle}...')
                profile = client.get_profile(handle)
                
                if not profile:
                    self.stdout.write(self.style.WARNING(f'Could not retrieve profile for {handle}'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Profile found for {handle}'))
                    # Format and display the profile information
                    self.stdout.write(f'Display name: {profile.get("displayName", "N/A")}')
                    self.stdout.write(f'Description: {profile.get("description", "N/A")}')
                    self.stdout.write(f'Followers: {profile.get("followersCount", 0)}')
                    self.stdout.write(f'Following: {profile.get("followsCount", 0)}')
            
            # Get timeline if requested
            if options['timeline']:
                limit = options['limit']
                self.stdout.write(f'Getting your timeline (limit: {limit})...')
                timeline = client.get_timeline(limit=limit)
                
                if not timeline or not timeline.get('feed'):
                    self.stdout.write(self.style.WARNING('Could not retrieve timeline'))
                else:
                    feed = timeline.get('feed', [])
                    self.stdout.write(self.style.SUCCESS(f'Retrieved {len(feed)} timeline items'))
                    
                    # Display recent posts
                    for i, item in enumerate(feed[:5], 1):
                        post = item.get('post', {})
                        record = post.get('record', {})
                        self.stdout.write(f'\n--- Post {i} ---')
                        self.stdout.write(f'Author: {post.get("author", {}).get("handle", "Unknown")}')
                        self.stdout.write(f'Text: {record.get("text", "No text")}')
                        self.stdout.write(f'Likes: {post.get("likeCount", 0)}')
                        self.stdout.write(f'Reposts: {post.get("repostCount", 0)}')
            
            # Get user posts if requested
            if options['user_posts']:
                handle = options['user_posts']
                limit = options['limit']
                self.stdout.write(f'Getting posts for {handle} (limit: {limit})...')
                user_posts = client.get_user_posts(handle, limit=limit)
                
                if not user_posts or not user_posts.get('feed'):
                    self.stdout.write(self.style.WARNING(f'Could not retrieve posts for {handle}'))
                else:
                    feed = user_posts.get('feed', [])
                    self.stdout.write(self.style.SUCCESS(f'Retrieved {len(feed)} posts from {handle}'))
                    
                    # Display recent posts
                    for i, item in enumerate(feed[:5], 1):
                        post = item.get('post', {})
                        record = post.get('record', {})
                        self.stdout.write(f'\n--- Post {i} ---')
                        self.stdout.write(f'Text: {record.get("text", "No text")}')
                        self.stdout.write(f'Likes: {post.get("likeCount", 0)}')
                        self.stdout.write(f'Reposts: {post.get("repostCount", 0)}')
            
            # Create a test post if requested
            if options['post']:
                post_text = options['post_text']
                self.stdout.write(f'Creating test post with text: "{post_text}"')
                post_result = client.create_post(post_text)
                
                if not post_result:
                    self.stdout.write(self.style.WARNING('Failed to create post'))
                else:
                    self.stdout.write(self.style.SUCCESS('Post created successfully!'))
                    self.stdout.write(f'Post URI: {post_result.get("uri", "Unknown")}')
            
            self.stdout.write(self.style.SUCCESS('Bluesky client test completed'))
            
        except Exception as e:
            raise CommandError(f'Error testing Bluesky client: {str(e)}')
        