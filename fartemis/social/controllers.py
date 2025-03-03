"""
file: fartemis/social/controllers.py

Controllers for handling social media integrations

@author: solvire
@date: 2025-03-02
"""
import logging
from datetime import datetime, timedelta
import json
from django.conf import settings

from fartemis.social.constants import Social, ContentType, ContentStatus, ContentOrigin
from fartemis.social.models import PublishContent
from fartemis.social.clients import APIClientFactory

from fartemis.llm.clients import LLMClientFactory
from fartemis.llm.constants import LLMProvider, ModelName

from fartemis.social.models import DocumentationEntry

logger = logging.getLogger(__name__)



class GitHubIntegrationController:
    """
    Controller for integrating with GitHub
    Monitors commits, generates content, and creates documentation
    """
    
    def __init__(self, repo_owner=None, repo_name=None, version=None):
        """Initialize with repository information"""
        self.github_client = APIClientFactory.generate(Social.GITHUB)
        self.repo_owner = repo_owner or settings.GITHUB_REPO_OWNER
        self.repo_name = repo_name or settings.GITHUB_REPO_NAME
        self.version = version or self._determine_next_version()
    
    def _determine_next_version(self):
        """
        Determine the next version based on existing DocumentationEntry objects
        Uses semantic versioning: MAJOR.MINOR.PATCH
        """
        try:
            # Get the latest changelog entry
            latest_entry = DocumentationEntry.objects.filter(
                doc_type='changelog'
            ).order_by('-created').first()
            
            if not latest_entry:
                return "0.1.0"  # Default initial version
            
            # Extract version from title
            import re
            version_match = re.search(r'v?(\d+\.\d+\.\d+)', latest_entry.title)
            if not version_match:
                return "0.1.0"
            
            # Parse version
            version = version_match.group(1)
            major, minor, patch = map(int, version.split('.'))
            
            # Increment patch version
            new_version = f"{major}.{minor}.{patch + 1}"
            return new_version
            
        except Exception as e:
            logger.error(f"Error determining next version: {e}")
            return "0.1.0"
        
    def fetch_recent_commits(self, days=1, branch=None):
        """
        Fetch commits from the past N days
        
        Args:
            days (int): Number of days to look back
            branch (str, optional): Specific branch to check
            
        Returns:
            list: List of commit objects
        """
        since_date = datetime.now() - timedelta(days=days)

        logger.info(f"Fetching commits since {since_date} for {self.repo_owner}/{self.repo_name}")
        
        commits = self.github_client.get_repository_commits(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            since=since_date,
            branch=branch
        )
        
        logger.info(f"Fetched {len(commits)} commits from {self.repo_owner}/{self.repo_name}")
        return commits
    
    def analyze_commit_changes(self, commit):
        """
        Analyze changes made in a specific commit
        
        Args:
            commit: GitHub commit object
            
        Returns:
            dict: Analysis of the commit changes
        """
        commit_files = self.github_client.get_commit_files(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            commit_sha=commit.sha
        )
        
        commit_stats = self.github_client.get_commit_stats(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            commit_sha=commit.sha
        )
        
        # Categorize file changes
        file_categories = {
            'added': [],
            'modified': [],
            'removed': [],
            'renamed': []
        }
        
        extensions = {}
        directories = {}
        
        for file in commit_files:
            # Categorize by change type
            file_categories[file.status].append(file.filename)
            
            # Count file extensions
            ext = file.filename.split('.')[-1] if '.' in file.filename else 'no_extension'
            extensions[ext] = extensions.get(ext, 0) + 1
            
            # Count directories
            directory = file.filename.split('/')[0] if '/' in file.filename else 'root'
            directories[directory] = directories.get(directory, 0) + 1
        
        return {
            'commit_sha': commit.sha,
            'commit_message': commit.commit.message,
            'author': commit.commit.author.name,
            'date': commit.commit.author.date.isoformat(),
            'stats': commit_stats,
            'file_categories': file_categories,
            'extensions': extensions,
            'directories': directories,
            'files': [f.filename for f in commit_files]
        }
    
    def analyze_file_changes(self, commit):
        """
        Analyze code changes in files for a specific commit
        
        Args:
            commit: GitHub commit object
            
        Returns:
            dict: Analysis of file changes with code context
        """
        files = self.github_client.get_commit_files(
            owner=self.repo_owner,
            repo_name=self.repo_name,
            commit_sha=commit.sha
        )
        
        file_analyses = []
        
        for file in files:
            # Skip files that are too large, binary, or deleted
            if file.status == 'removed' or not file.patch:
                continue
                
            # Extract meaningful information from the patch
            context = {
                'filename': file.filename,
                'status': file.status,
                'additions': file.additions,
                'deletions': file.deletions,
                'patch': file.patch,
                'extension': file.filename.split('.')[-1] if '.' in file.filename else None,
            }
            
            # Extract function/class definitions from the patch
            import re
            
            # For Python files
            if context['extension'] == 'py':
                # Look for class and function definitions in the added lines
                class_pattern = r'^\+\s*class\s+(\w+)'
                func_pattern = r'^\+\s*def\s+(\w+)'
                
                classes = re.findall(class_pattern, file.patch, re.MULTILINE)
                functions = re.findall(func_pattern, file.patch, re.MULTILINE)
                
                context['classes'] = classes
                context['functions'] = functions
                
                # Extract docstrings from added code
                docstring_pattern = r'^\+\s*"""(.+?)"""'
                docstrings = re.findall(docstring_pattern, file.patch, re.MULTILINE | re.DOTALL)
                context['docstrings'] = docstrings
            
            file_analyses.append(context)
        
        return file_analyses
    
    def analyze_code_with_llm(self, file_analyses):
        """
        Use LLM to analyze Python code changes and provide insights
        
        Args:
            file_analyses: List of file analysis dictionaries
            
        Returns:
            dict: LLM-generated insights about the changes
        """
        try:
            # Initialize LLM client
            llm_client = LLMClientFactory.create(
                provider=LLMProvider.ANTHROPIC,
                api_key=settings.ANTHROPIC_API_KEY,
                model=ModelName.CLAUDE_3_SONNET
            )
            
            # Filter for Python files only
            python_files = [file for file in file_analyses if file.get('extension') == 'py']
            
            if not python_files:
                return {
                    'summary': "No Python files were modified in this update.",
                    'technical_debt': None,
                    'documentation': None
                }
            
            # Prepare input for LLM
            code_analysis_template = """
I need you to analyze these Python code changes and provide insights. For each file:
1. Explain what functionality was added or modified
2. Identify any potential technical debt, code smells, or areas for improvement
3. Extract and enhance key documentation points

Here are the file changes:

{file_changes}

Provide your analysis in this format:

## Functionality Summary
[A concise summary of what was implemented or changed across all files]

## Technical Insights
[Your technical analysis of the implementation, architecture decisions, etc.]

## Potential Improvements
[Any technical debt or improvements you'd suggest]

## Documentation Notes
[Enhanced documentation based on comments and docstrings in the code]
"""
            
            # Format file changes for the prompt
            file_changes_text = ""
            for analysis in python_files[:3]:  # Limit to 3 files to keep prompt size reasonable
                file_changes_text += f"\n### File: {analysis['filename']} ({analysis['status']})\n"
                file_changes_text += f"Changes: +{analysis['additions']} -{analysis['deletions']} lines\n"
                
                # Include classes and functions
                if 'classes' in analysis and analysis['classes']:
                    file_changes_text += f"New/Modified Classes: {', '.join(analysis['classes'])}\n"
                if 'functions' in analysis and analysis['functions']:
                    file_changes_text += f"New/Modified Functions: {', '.join(analysis['functions'])}\n"
                
                # Include docstrings
                if 'docstrings' in analysis and analysis['docstrings']:
                    file_changes_text += "Docstrings:\n"
                    for doc in analysis['docstrings'][:2]:  # Limit to 2 docstrings per file
                        file_changes_text += f"- {doc.strip()}\n"
                
                # Include a sample of the patch (first few lines)
                file_changes_text += "Sample changes:\n```python\n"
                patch_lines = analysis['patch'].split('\n')[:20]  # First 20 lines
                file_changes_text += "\n".join(patch_lines)
                file_changes_text += "\n```\n"
            
            # Add a note if we truncated the file list
            if len(python_files) > 3:
                file_changes_text += f"\n*Note: {len(python_files) - 3} additional Python files were modified but not shown here.*\n"
            
            # Render the prompt
            prompt = llm_client.render_prompt(code_analysis_template, file_changes=file_changes_text)
            
            # Call LLM
            response = llm_client.complete(prompt)
            
            # Parse the response into sections
            analysis_text = response['text']
            
            # Simple section extraction
            sections = {
                'summary': '',
                'technical_insights': '',
                'improvements': '',
                'documentation': ''
            }
            
            current_section = None
            for line in analysis_text.split('\n'):
                if '## Functionality Summary' in line:
                    current_section = 'summary'
                    continue
                elif '## Technical Insights' in line:
                    current_section = 'technical_insights'
                    continue
                elif '## Potential Improvements' in line:
                    current_section = 'improvements'
                    continue
                elif '## Documentation Notes' in line:
                    current_section = 'documentation'
                    continue
                
                if current_section and line.strip():
                    sections[current_section] += line + '\n'
            
            return sections
            
        except Exception as e:
            logger.error(f"Error analyzing code with LLM: {e}")
            return {
                'summary': "Error analyzing code changes.",
                'technical_debt': None,
                'documentation': None
            }

    
    def generate_commit_summary(self, commits):
        """
        Generate a summary of commits for social media
        
        Args:
            commits: List of GitHub commit objects
            
        Returns:
            dict: Summary content for different platforms
        """
        if not commits:
            return None
            
        # Analyze all commits
        detailed_analyses = []
        file_analyses = []
        total_additions = 0
        total_deletions = 0
        affected_directories = set()
        file_extensions = {}
        
        for commit in commits[:10]:  # Limit to 10 commits for analysis
            analysis = self.analyze_commit_changes(commit)
            detailed_analyses.append(analysis)
            
            # Analyze files
            commit_file_analyses = self.analyze_file_changes(commit)
            file_analyses.extend(commit_file_analyses)
            
            # Aggregate stats
            if 'stats' in analysis:
                total_additions += analysis['stats'].get('additions', 0)
                total_deletions += analysis['stats'].get('deletions', 0)
            
            # Track affected directories and file types
            for directory in analysis.get('directories', {}):
                affected_directories.add(directory)
                
            for ext, count in analysis.get('extensions', {}).items():
                file_extensions[ext] = file_extensions.get(ext, 0) + count
        
        # Use LLM to analyze code changes
        code_insights = self.analyze_code_with_llm(file_analyses)
        
        # Create enhanced content with LLM insights
        commit_count = len(commits)
        timeframe = "today" if commit_count == 1 else f"the past {len(commits)} commits"
        
        # For longer formats (blog, README)
        body = f"""## Latest Code Updates

In {timeframe}, we've made {commit_count} commits to the Fartemis project, with {total_additions} lines added and {total_deletions} lines removed.

### Key Changes:
"""
        
        # Add bullet points for each commit
        for analysis in detailed_analyses:
            commit_message = analysis['commit_message'].split('\n')[0]
            commit_sha = analysis['commit_sha'][:7]
            body += f"- {commit_message} ({commit_sha})\n"
        
        # Add LLM insights if available
        if code_insights and code_insights.get('summary'):
            body += f"\n### Functionality Summary\n{code_insights['summary']}\n"
        
        if code_insights and code_insights.get('technical_insights'):
            body += f"\n### Technical Insights\n{code_insights['technical_insights']}\n"
        
        if code_insights and code_insights.get('improvements'):
            body += f"\n### Potential Improvements\n{code_insights['improvements']}\n"
        
        # Add summary of affected directories and file types
        body += f"""
### Summary

These changes affected {len(affected_directories)} directories, primarily working with {", ".join(sorted(file_extensions, key=lambda x: file_extensions[x], reverse=True)[:3])} files.
"""
        
        # For Bluesky (300 char limit)
        short_summary = code_insights.get('summary', '').split('.')[0] if code_insights and code_insights.get('summary') else ''
        short_content = f"📊 Fartemis update: {commit_count} new commits with +{total_additions}/-{total_deletions} lines. Working on {', '.join(list(affected_directories)[:2])}. {short_summary} #Python #OpenSource #JobHunting"
        
        # For Twitter (280 char limit)
        micro_content = f"📊 Fartemis: {commit_count} commits, +{total_additions}/-{total_deletions} lines. #Python #OpenSource #JobHunting"
        
        # Return content for different platforms
        return {
            'title': f"Fartemis Development Update: {commit_count} New Commits",
            'body': body,
            'short_content': short_content,
            'micro_content': micro_content,
            'hashtags': ['Python', 'OpenSource', 'JobHunting', 'AI', 'Development'],
            'detailed_analyses': detailed_analyses,
            'code_insights': code_insights
        }
    

    def generate_documentation(self, commits):
        """
        Generate documentation for the CHANGELOG.md file using semantic versioning
        
        Args:
            commits: List of GitHub commit objects
            
        Returns:
            str: Markdown changelog entry
        """
        if not commits:
            return None
            
        summary = self.generate_commit_summary(commits)
        if not summary:
            return None
        
        # Get the current date for the changelog entry
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Create a changelog entry with version
        markdown = f"""## [v{self.version}] - {today}

### Added/Changed
"""
        
        # Add bullet points for each commit with their changes
        for analysis in summary['detailed_analyses']:
            # Get first line of commit message
            message = analysis['commit_message'].split('\n')[0]
            # Add bullet point with commit message and link to commit
            markdown += f"- {message} ([{analysis['commit_sha'][:7]}](https://github.com/{self.repo_owner}/{self.repo_name}/commit/{analysis['commit_sha']}))\n"
        
        # Add stats summary
        total_additions = sum(a['stats'].get('additions', 0) for a in summary['detailed_analyses'])
        total_deletions = sum(a['stats'].get('deletions', 0) for a in summary['detailed_analyses'])
        
        markdown += f"\n{total_additions} additions and {total_deletions} deletions across {len(commits)} commits\n"
        
        # Add LLM insights if available
        code_insights = summary.get('code_insights', {})
        
        if code_insights and code_insights.get('summary'):
            markdown += f"\n### Summary\n{code_insights['summary']}\n"
        
        if code_insights and code_insights.get('improvements'):
            markdown += f"\n### Technical Notes\n{code_insights['improvements']}\n"
        
        return markdown


    def create_content_from_commits(self, days=1, branch=None):
        """
        Check for recent commits and create content
        
        Args:
            days (int): Number of days to look back
            branch (str, optional): Branch to check
            
        Returns:
            tuple: (PublishContent object, documentation string)
        """
        # Fetch commits
        commits = self.fetch_recent_commits(days=days, branch=branch)
        
        if not commits:
            logger.info(f"No new commits found for {self.repo_owner}/{self.repo_name}")
            return None, None
        
        # Generate summary content
        summary = self.generate_commit_summary(commits)
        
        if not summary:
            logger.error("Failed to generate commit summary")
            return None, None
        
        # Generate documentation
        documentation = self.generate_documentation(commits)
        
        # Create PublishContent object
        content = PublishContent(
            title=summary['title'],
            body=summary['body'],
            short_content=summary['short_content'],
            micro_content=summary['micro_content'],
            content_type=ContentType.COMMIT_SUMMARY,
            hashtags=summary['hashtags'],
            origin_type=ContentOrigin.GITHUB,
            origin_id=commits[0].sha,  # Use the most recent commit SHA
            status=ContentStatus.READY
        )
        
        # Save to database
        try:
            content.save()
            logger.info(f"Created new publish content: {content.id}")
            return content, documentation
        except Exception as e:
            logger.error(f"Failed to save publish content: {str(e)}")
            return None, None
        
