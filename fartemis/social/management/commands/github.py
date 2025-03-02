# social/management/commands/github.py
"""
# Test authentication only
python manage.py github

# Get repository info
python manage.py github --repo yourusername/fartemis

# Get recent commits
python manage.py github --repo yourusername/fartemis --commits

# Get commits from past 7 days
python manage.py github --repo yourusername/fartemis --commits --days 7

# Get commits from a specific branch
python manage.py github --repo yourusername/fartemis --commits --branch develop

# Get detailed information about a specific commit
python manage.py github --repo yourusername/fartemis --commit abc1234
"""

import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from fartemis.social.clients import APIClientFactory
from fartemis.social.constants import Social

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test GitHub API client functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo',
            type=str,
            help='Repository name (format: owner/repo)'
        )
        parser.add_argument(
            '--commits',
            action='store_true',
            help='Get recent commits for the repository'
        )
        parser.add_argument(
            '--commit',
            type=str,
            help='Get details for a specific commit SHA'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Number of days to look back for commits'
        )
        parser.add_argument(
            '--branch',
            type=str,
            help='Branch to check (default: main/master branch)'
        )

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('Initializing GitHub client...'))
            
            # Get GitHub client from factory
            client = APIClientFactory.generate(Social.GITHUB)
            
            # Test authentication
            self.stdout.write('Testing GitHub authentication...')
            auth_result = client.check_credentials()
            
            if not auth_result:
                raise CommandError('Failed to authenticate with GitHub')
                
            self.stdout.write(self.style.SUCCESS(f'Successfully authenticated as {auth_result["login"]}'))
            
            # If no repo specified, just verify authentication
            if not options.get('repo'):
                self.stdout.write(self.style.WARNING('No repository specified. Use --repo owner/repo to test further.'))
                return
                
            repo_full_name = options['repo']
            owner, repo_name = repo_full_name.split('/')
            
            # Get repository info
            self.stdout.write(f'Getting repository info for {repo_full_name}...')
            repo = client.get_repository(owner, repo_name)
            
            if not repo:
                raise CommandError(f'Repository {repo_full_name} not found or inaccessible')
                
            self.stdout.write(self.style.SUCCESS(f'Repository found: {repo.full_name}'))
            self.stdout.write(f'Description: {repo.description}')
            self.stdout.write(f'Stars: {repo.stargazers_count}')
            self.stdout.write(f'Forks: {repo.forks_count}')
            self.stdout.write(f'Default branch: {repo.default_branch}')
            
            # Get recent commits if requested
            if options['commits']:
                days = options['days']
                branch = options['branch']
                self.stdout.write(f'Getting commits for the past {days} days...')
                
                since_date = datetime.now() - timedelta(days=days)
                commits = client.get_repository_commits(
                    owner=owner,
                    repo_name=repo_name,
                    since=since_date,
                    branch=branch
                )
                
                if not commits:
                    self.stdout.write(self.style.WARNING(f'No commits found in the past {days} days'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Found {len(commits)} commits'))
                    
                    # Display recent commits
                    for i, commit in enumerate(commits[:5], 1):
                        self.stdout.write(f'\n--- Commit {i} ---')
                        self.stdout.write(f'SHA: {commit.sha[:7]}')
                        self.stdout.write(f'Author: {commit.commit.author.name}')
                        self.stdout.write(f'Date: {commit.commit.author.date}')
                        # Get the first line of the commit message
                        message = commit.commit.message.split('\n')[0]
                        self.stdout.write(f'Message: {message}')
            
            # Get specific commit if requested
            if options['commit']:
                commit_sha = options['commit']
                self.stdout.write(f'Getting details for commit {commit_sha}...')
                
                commit = client.get_commit_details(owner, repo_name, commit_sha)
                
                if not commit:
                    self.stdout.write(self.style.WARNING(f'Commit {commit_sha} not found'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Commit details:'))
                    self.stdout.write(f'SHA: {commit.sha}')
                    self.stdout.write(f'Author: {commit.commit.author.name} <{commit.commit.author.email}>')
                    self.stdout.write(f'Date: {commit.commit.author.date}')
                    self.stdout.write(f'Message: {commit.commit.message}')
                    
                    # Get stats
                    self.stdout.write(f'Additions: {commit.stats.additions}')
                    self.stdout.write(f'Deletions: {commit.stats.deletions}')
                    self.stdout.write(f'Total changes: {commit.stats.total}')
                    
                    # List files changed
                    self.stdout.write('\nFiles changed:')
                    for file in commit.files:
                        self.stdout.write(f'  {file.filename} ({file.status}: +{file.additions}, -{file.deletions})')
            
            self.stdout.write(self.style.SUCCESS('GitHub client test completed'))
            
        except Exception as e:
            logger.exception("Error testing GitHub client")
            raise CommandError(f'Error testing GitHub client: {str(e)}')