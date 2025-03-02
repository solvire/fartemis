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


# Search for posts containing a specific term
python manage.py test_bluesky --search-posts="AI jobs"

# Search for users
python manage.py test_bluesky --search-users="python developer"

# Follow a user
python manage.py test_bluesky --follow=someone.bsky.social

# Unfollow a user
python manage.py test_bluesky --unfollow=someone.bsky.social

# Check your notifications
python manage.py test_bluesky --notifications
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
        parser.add_argument(
            '--search-posts',
            type=str,
            help='Search for posts containing the query'
        )
        parser.add_argument(
            '--search-users',
            type=str,
            help='Search for users matching the query'
        )
        parser.add_argument(
            '--follow',
            type=str,
            help='Follow a user'
        )
        parser.add_argument(
            '--unfollow',
            type=str,
            help='Unfollow a user'
        )
        parser.add_argument(
            '--notifications',
            action='store_true',
            help='Get your notifications'
        )

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('Initializing Bluesky client...'))
            
            # Get Bluesky client from factory
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
                    self.stdout.write(f'Display name: {profile.display_name}')
                    self.stdout.write(f'Description: {profile.description}')
                    self.stdout.write(f'Followers: {profile.followers_count}')
                    self.stdout.write(f'Following: {profile.follows_count}')
                    self.stdout.write(f'Posts: {profile.posts_count}')
            
            # Get timeline if requested
            if options['timeline']:
                limit = options['limit']
                self.stdout.write(f'Getting your timeline (limit: {limit})...')
                timeline = client.get_timeline(limit=limit)
                
                if not timeline or not hasattr(timeline, 'feed'):
                    self.stdout.write(self.style.WARNING('Could not retrieve timeline'))
                else:
                    feed = timeline.feed
                    self.stdout.write(self.style.SUCCESS(f'Retrieved {len(feed)} timeline items'))
                    
                    # Display recent posts
                    for i, item in enumerate(feed[:5], 1):
                        post = item.post
                        self.stdout.write(f'\n--- Post {i} ---')
                        self.stdout.write(f'Author: {post.author.handle}')
                        self.stdout.write(f'Text: {post.record.text}')
                        self.stdout.write(f'Likes: {post.like_count}')
                        self.stdout.write(f'Reposts: {post.repost_count}')
                        self.stdout.write(f'Replies: {post.reply_count}')
            
            # Get user posts if requested
            if options['user_posts']:
                handle = options['user_posts']
                limit = options['limit']
                self.stdout.write(f'Getting posts for {handle} (limit: {limit})...')
                user_posts = client.get_user_posts(handle, limit=limit)
                
                if not user_posts or not hasattr(user_posts, 'feed'):
                    self.stdout.write(self.style.WARNING(f'Could not retrieve posts for {handle}'))
                else:
                    feed = user_posts.feed
                    self.stdout.write(self.style.SUCCESS(f'Retrieved {len(feed)} posts from {handle}'))
                    
                    # Display recent posts
                    for i, item in enumerate(feed[:5], 1):
                        post = item.post
                        self.stdout.write(f'\n--- Post {i} ---')
                        self.stdout.write(f'Text: {post.record.text}')
                        self.stdout.write(f'Likes: {post.like_count}')
                        self.stdout.write(f'Reposts: {post.repost_count}')
                        self.stdout.write(f'Replies: {post.reply_count}')
            
            # Create a test post if requested
            if options['post']:
                post_text = options['post_text']
                self.stdout.write(f'Creating test post with text: "{post_text}"')
                post_result = client.create_post(post_text)
                
                if not post_result:
                    self.stdout.write(self.style.WARNING('Failed to create post'))
                else:
                    self.stdout.write(self.style.SUCCESS('Post created successfully!'))
                    self.stdout.write(f'Post URI: {post_result.uri}')
                    self.stdout.write(f'Post CID: {post_result.cid}')
            
            # Search posts if requested
            if options['search_posts']:
                query = options['search_posts']
                limit = options['limit']
                self.stdout.write(f'Searching posts with query: "{query}" (limit: {limit})...')
                search_results = client.search_posts(query=query, limit=limit)
                
                if not search_results or not hasattr(search_results, 'posts'):
                    self.stdout.write(self.style.WARNING(f'No posts found for query: {query}'))
                else:
                    posts = search_results.posts
                    self.stdout.write(self.style.SUCCESS(f'Found {len(posts)} posts matching query: {query}'))
                    
                    # Display matching posts
                    for i, post in enumerate(posts[:5], 1):
                        self.stdout.write(f'\n--- Result {i} ---')
                        self.stdout.write(f'Author: {post.author.handle}')
                        self.stdout.write(f'Text: {post.record.text}')
                        self.stdout.write(f'Likes: {post.like_count}')
                        self.stdout.write(f'Reposts: {post.repost_count}')
            
            # Search users if requested
            if options['search_users']:
                query = options['search_users']
                limit = options['limit']
                self.stdout.write(f'Searching users with query: "{query}" (limit: {limit})...')
                search_results = client.search_users(query=query, limit=limit)
                
                if not search_results or not hasattr(search_results, 'actors'):
                    self.stdout.write(self.style.WARNING(f'No users found for query: {query}'))
                else:
                    users = search_results.actors
                    self.stdout.write(self.style.SUCCESS(f'Found {len(users)} users matching query: {query}'))
                    
                    # Display matching users
                    for i, user in enumerate(users[:5], 1):
                        self.stdout.write(f'\n--- User {i} ---')
                        self.stdout.write(f'Handle: {user.handle}')
                        self.stdout.write(f'Display name: {user.display_name}')
                        self.stdout.write(f'Description: {user.description}')
            
            # Follow a user if requested
            if options['follow']:
                handle = options['follow']
                self.stdout.write(f'Following user: {handle}...')
                follow_result = client.follow_user(handle)
                
                if not follow_result:
                    self.stdout.write(self.style.WARNING(f'Failed to follow user: {handle}'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Successfully followed user: {handle}'))
            
            # Unfollow a user if requested
            if options['unfollow']:
                handle = options['unfollow']
                self.stdout.write(f'Unfollowing user: {handle}...')
                unfollow_result = client.unfollow_user(handle)
                
                if not unfollow_result:
                    self.stdout.write(self.style.WARNING(f'Failed to unfollow user: {handle}'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Successfully unfollowed user: {handle}'))
            
            # Get notifications if requested
            if options['notifications']:
                limit = options['limit']
                self.stdout.write(f'Getting your notifications (limit: {limit})...')
                notifications = client.get_notifications(limit=limit)
                
                if not notifications or not hasattr(notifications, 'notifications'):
                    self.stdout.write(self.style.WARNING('Could not retrieve notifications'))
                else:
                    notifs = notifications.notifications
                    self.stdout.write(self.style.SUCCESS(f'Retrieved {len(notifs)} notifications'))
                    
                    # Display recent notifications
                    for i, notif in enumerate(notifs[:5], 1):
                        self.stdout.write(f'\n--- Notification {i} ---')
                        self.stdout.write(f'Type: {notif.reason}')
                        self.stdout.write(f'From: {notif.author.handle}')
                        if hasattr(notif, 'record') and hasattr(notif.record, 'text'):
                            self.stdout.write(f'Content: {notif.record.text[:50]}...' if len(notif.record.text) > 50 else notif.record.text)
                        self.stdout.write(f'At: {notif.indexed_at}')
            
            self.stdout.write(self.style.SUCCESS('Bluesky client test completed'))
            
        except Exception as e:
            logger.exception("Error testing Bluesky client")
            raise CommandError(f'Error testing Bluesky client: {str(e)}')
