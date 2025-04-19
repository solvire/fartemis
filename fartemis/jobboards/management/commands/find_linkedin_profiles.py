"""
Depricated: 
used to find LinkedIn profiles originally before the controller took over
Used for prototyping. 



./manage.py find_linkedin_profiles --first_name=Steven --last_name=Scott --company=Netki --search_engine=both --verbose
./manage.py find_linkedin_profiles --first_name=Dawn --last_name=Newton --company=Netki --search_engine=both --verbose
./manage.py find_linkedin_profiles --first_name=Olivia --last_name=Melman --company="DigitalOcean" --search_engine=both --verbose
"""
import logging
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from django.core.management.base import BaseCommand
from django.conf import settings
from langchain_tavily import TavilySearch  # Updated correct import

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Search for a person\'s LinkedIn profile using a procedural web search approach'

    def add_arguments(self, parser):
        parser.add_argument(
            '--first_name',
            type=str,
            help='First name of the person to search for',
            required=True
        )
        parser.add_argument(
            '--last_name',
            type=str,
            help='Last name of the person to search for',
            required=True
        )
        parser.add_argument(
            '--company',
            type=str,
            help='Company name (optional)',
            required=False
        )
        parser.add_argument(
            '--search_engine',
            type=str,
            choices=['duckduckgo', 'tavily', 'both'],
            default='both',
            help='Search engine to use'
        )
        parser.add_argument(
            '--max_pages',
            type=int,
            help='Maximum number of pages to check',
            default=5
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        first_name = options['first_name']
        last_name = options['last_name']
        company = options.get('company', '')
        max_pages = options['max_pages']
        verbose = options.get('verbose', False)
        search_engine = options.get('search_engine', 'both')
        
        # Configure logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
        
        self.stdout.write(f"Searching for LinkedIn profile of {first_name} {last_name}")
        if company:
            self.stdout.write(f"Associated with company: {company}")
        
        # Step 1: Perform the search with selected engine(s)
        search_results = []
        
        if search_engine in ['duckduckgo', 'both']:
            self.stdout.write("Using DuckDuckGo search...")
            duckduckgo_results = self._perform_duckduckgo_search(first_name, last_name, company)
            search_results.extend(duckduckgo_results)
        
        if search_engine in ['tavily', 'both']:
            self.stdout.write("Using Tavily search...")
            tavily_results = self._perform_tavily_search(first_name, last_name, company)
            search_results.extend(tavily_results)
        
        if not search_results:
            self.stdout.write(self.style.ERROR("No search results found"))
            return
        
        # Step 2: Sort pages by priority, with company association as a major factor
        prioritized_pages = self._prioritize_pages(search_results, first_name, last_name, company)
        
        self.stdout.write(f"Found {len(prioritized_pages)} pages to analyze")
        
        # Step 3: Analyze top pages for LinkedIn profile links
        linkedin_profiles = []
        pages_analyzed = 0
        
        for page in prioritized_pages:
            if pages_analyzed >= max_pages:
                break
                
            url = page['url']
            priority = page['priority']
            reason = page['reason']
            
            self.stdout.write(f"Analyzing page: {url} (Priority: {priority}, Reason: {reason})")
            
            # If this is already a LinkedIn profile URL, add it directly
            if 'linkedin.com/in/' in url:
                profile_handle = self._extract_handle_from_url(url)
                if profile_handle:
                    match_score = self._calculate_profile_match_score(url, "", first_name, last_name, company)
                    linkedin_profiles.append({
                        'url': url,
                        'text': f"{first_name} {last_name}",
                        'context': f"Direct profile URL",
                        'match': match_score
                    })
                    self.stdout.write(self.style.SUCCESS(f"  - Added direct profile: {url} (Match: {match_score})"))
            
            # Fetch and parse the page to look for more LinkedIn profiles
            page_content = self._fetch_page(url)
            if not page_content:
                continue
                
            # Extract LinkedIn profile links
            page_profiles = self._extract_linkedin_profiles(page_content, first_name, last_name, company)
            
            if page_profiles:
                self.stdout.write(self.style.SUCCESS(f"Found {len(page_profiles)} potential LinkedIn profiles"))
                for profile in page_profiles:
                    self.stdout.write(f"  - {profile['url']} (Match: {profile['match']})")
                    linkedin_profiles.append(profile)
            else:
                self.stdout.write(self.style.WARNING("No LinkedIn profiles found on this page"))
            
            pages_analyzed += 1
        
        # Deduplicate and rank the final results
        final_profiles = self._deduplicate_profiles(linkedin_profiles)
        
        # Display final results
        self.stdout.write("\nPotential LinkedIn Profiles:")
        if final_profiles:
            for i, profile in enumerate(final_profiles, 1):
                self.stdout.write(self.style.SUCCESS(
                    f"{i}. {profile['url']} (Match: {profile['match']}, Confidence: {profile['confidence']})"
                ))
            
            # Extract the best handle
            best_handle = self._extract_best_handle(final_profiles)
            if best_handle:
                self.stdout.write(self.style.SUCCESS(f"\nBest LinkedIn handle found: {best_handle}"))
                return best_handle
        else:
            self.stdout.write(self.style.ERROR("No LinkedIn profiles found"))
            return None

    def _perform_duckduckgo_search(self, first_name, last_name, company=None):
        """
        Perform a web search using DuckDuckGo's modern HTML structure
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            # Construct search term
            search_term = f"{first_name} {last_name}"
            if company:
                search_term += f" {company}"
            search_term += " linkedin"
            
            # Use DuckDuckGo HTML search
            encoded_query = search_term.replace(' ', '+')
            search_url = f"https://duckduckgo.com/?q={encoded_query}&kl=wt-wt"
            
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse the search results
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            # Look for result containers
            for result in soup.select('article'):
                # Modern DuckDuckGo structure - find title links
                title_link = result.select_one('h2 a, h3 a, a[data-testid="result-title-a"]')
                
                if title_link:
                    title = title_link.get_text(strip=True)
                    url = title_link.get('href', '')
                    
                    # Find snippet
                    snippet_elem = result.select_one('p[data-testid="result-snippet"], .result__snippet')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    # Find URL display element
                    url_elem = result.select_one('[data-testid="result-extras-url-link"], .result__url')
                    if url_elem and not url:
                        url = url_elem.get('href', '') or url_elem.get_text(strip=True)
                    
                    # Process links with special handling for LinkedIn URLs
                    if url:
                        # Clean up relative URLs
                        if url.startswith('/'):
                            url = f"https://duckduckgo.com{url}"
                        
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet,
                            'source': 'duckduckgo'
                        })
            
            # If we didn't find any results with the modern structure, try the alternate structure
            if not results:
                # Try to find links in the modern structure
                for link in soup.select('a[data-testid="result-extras-url-link"]'):
                    url = link.get('href')
                    if not url:
                        continue
                        
                    # Try to get title and snippet
                    parent = link.parent.parent
                    title_elem = parent.select_one('h2, h3')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    snippet_elem = parent.select_one('p')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    results.append({
                        'title': title,
                        'url': url,
                        'snippet': snippet,
                        'source': 'duckduckgo'
                    })
            
            # Still no results? Try other selectors
            if not results:
                for link in soup.select('a[href^="https://"]'):
                    url = link.get('href', '')
                    
                    # Only include external links that might be relevant
                    if 'linkedin.com' in url or 'duckduckgo.com' not in url:
                        title = link.get_text(strip=True)
                        
                        # Try to get a snippet from surrounding text
                        parent = link.parent
                        context = parent.get_text(strip=True) if parent else ""
                        snippet = context.replace(title, "").strip()
                        
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet,
                            'source': 'duckduckgo'
                        })
            
            return results
            
        except Exception as e:
            logger.error(f"Error performing DuckDuckGo search: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _perform_tavily_search(self, first_name, last_name, company=None):
        """
        Perform a web search using Tavily
        """
        try:
            # Construct search term
            search_term = f"{first_name} {last_name}"
            if company:
                search_term += f" {company}"
            search_term += " linkedin"
            
            # Initialize Tavily search tool
            tavily_search = TavilySearch(
                max_results=10,
                api_key=getattr(settings, 'TAVILY_API_KEY', None)
            )
            
            # Execute search
            search_results = tavily_search.invoke(search_term)
            
            # Process search results
            results = []
            
            # Determine format and extract results
            if isinstance(search_results, dict) and "results" in search_results:
                result_items = search_results["results"]
            elif isinstance(search_results, list):
                result_items = search_results
            else:
                result_items = []
            
            # Format results to match our expected structure
            for item in result_items:
                if isinstance(item, dict):
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'snippet': item.get('content', ''),
                        'source': 'tavily'
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error performing Tavily search: {e}")
            return []

    def _prioritize_pages(self, search_results, first_name, last_name, company=None):
        """
        Prioritize pages based on likelihood of containing LinkedIn profile links,
        with higher priority for company association
        """
        prioritized = []
        
        for result in search_results:
            url = result['url']
            
            # Add scheme if missing
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
                
            title = result['title']
            snippet = result['snippet']
            
            # Calculate priority based on various factors
            priority = 0
            reason = []
            
            # Major boost for URLs that are already LinkedIn profile pages
            if 'linkedin.com/in/' in url:
                priority += 200
                reason.append("Direct LinkedIn profile URL")
                
                # Name in profile URL
                name_match_score = self._calculate_name_match_in_url(url, first_name, last_name)
                if name_match_score > 0:
                    priority += 50 * name_match_score
                    reason.append("Name in profile URL")
                
                # Company in profile URL
                if company and company.lower().replace(' ', '') in url.lower():
                    priority += 100
                    reason.append(f"{company} in profile URL")
            
            # Good boost for LinkedIn post URLs that mention the company
            elif 'linkedin.com/posts/' in url and company:
                priority += 150
                reason.append("LinkedIn post URL")
                
                # Check if company is in the URL
                if company.lower().replace(' ', '') in url.lower():
                    priority += 50
                    reason.append(f"{company} in post URL")
            
            # General boost for any LinkedIn domain
            elif 'linkedin.com' in url:
                priority += 100
                reason.append("LinkedIn domain")
            
            # Check title and snippet for keywords
            content = (title + ' ' + snippet).lower()
            
            # Check for name in content
            if first_name.lower() in content and last_name.lower() in content:
                priority += 20
                reason.append("Full name in content")
                
            # Check for company association - major priority boost
            if company and company.lower() in content:
                priority += 100
                reason.append(f"Associated with {company}")
                
            # Check for LinkedIn mentions
            if 'linkedin' in content:
                priority += 10
                reason.append("LinkedIn mentioned")
                
            # Check for profile-related terms
            if any(term in content for term in ['profile', 'cv', 'resume', 'professional']):
                priority += 5
                reason.append("Profile-related terms")
            
            prioritized.append({
                'url': url,
                'title': title,
                'snippet': snippet,
                'priority': priority,
                'reason': ', '.join(reason),
                'source': result.get('source', 'unknown')
            })
        
        # Sort by priority (highest first)
        return sorted(prioritized, key=lambda x: x['priority'], reverse=True)

    def _calculate_name_match_in_url(self, url, first_name, last_name):
        """
        Calculate how well a name matches a URL
        Returns a score between 0 and 1
        """
        url_lower = url.lower()
        first_lower = first_name.lower()
        last_lower = last_name.lower()
        
        # Extract handle from linkedin.com/in/handle
        handle = self._extract_handle_from_url(url)
        if not handle:
            return 0
        
        handle_lower = handle.lower()
        score = 0
        
        # Check for exact matches
        if handle_lower == f"{first_lower}{last_lower}" or handle_lower == f"{last_lower}{first_lower}":
            return 1.0
        
        # Check for variations
        variations = [
            f"{first_lower}.{last_lower}",
            f"{first_lower}-{last_lower}",
            f"{first_lower}_{last_lower}",
            f"iam{first_lower}{last_lower}",
            f"i.am.{first_lower}.{last_lower}",
            f"{first_lower[0]}{last_lower}",
            f"{first_lower}{last_lower[0]}"
        ]
        
        for variation in variations:
            if variation in handle_lower:
                score = 0.8
                break
        
        # Partial matches
        if score == 0:
            if first_lower in handle_lower and last_lower in handle_lower:
                score = 0.7
            elif first_lower in handle_lower or last_lower in handle_lower:
                score = 0.5
        
        return score

    def _extract_handle_from_url(self, url):
        """Extract just the handle part from a LinkedIn profile URL"""
        if '/in/' not in url:
            return None
            
        # Split at /in/ and take everything after
        after_in = url.split('/in/')[1]
        
        # Remove URL parameters and trailing slashes
        handle = after_in.split('?')[0].split('/')[0].rstrip('/')
        
        return handle

    def _fetch_page(self, url):
        """
        Fetch and parse a webpage
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            # Add scheme if missing
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching page {url}: {e}")
            return None

    def _calculate_profile_match_score(self, url, context, first_name, last_name, company=None):
        """Calculate a match score for a LinkedIn profile"""
        score = 0
        
        # Name matching in URL
        name_url_score = self._calculate_name_match_in_url(url, first_name, last_name)
        score += name_url_score * 10  # Scale up to our scoring range
        
        # Context matching
        context_lower = context.lower()
        if first_name.lower() in context_lower:
            score += 3
        
        if last_name.lower() in context_lower:
            score += 3
        
        # Company association
        if company and company.lower() in context_lower:
            score += 5
            
        # Special score boost for handles that look like "iamstevenscott"
        handle = self._extract_handle_from_url(url)
        if handle and handle.lower() == f"iam{first_name.lower()}{last_name.lower()}":
            score += 10
        
        return score

    def _extract_linkedin_profiles(self, page_content, first_name, last_name, company=None):
        """
        Extract LinkedIn profile links from a page, with company association consideration
        """
        soup = BeautifulSoup(page_content, 'html.parser')
        linkedin_profiles = []
        
        # Look for all links
        for link in soup.find_all('a'):
            href = link.get('href', '')
            
            # Check if it's a LinkedIn profile link
            if 'linkedin.com/in/' in href:
                # Add scheme if missing
                if not href.startswith('http://') and not href.startswith('https://'):
                    href = 'https://' + href
                    
                # Extract the text of the link and surrounding context
                link_text = link.get_text(strip=True)
                
                # Try to get some surrounding context (parent paragraph or div)
                parent = link.parent
                context = parent.get_text(strip=True) if parent else ""
                
                # Calculate match score
                match_score = self._calculate_profile_match_score(href, context, first_name, last_name, company)
                
                # Add this profile
                linkedin_profiles.append({
                    'url': href,
                    'text': link_text,
                    'context': context,
                    'match': match_score
                })
        
        # Sort by match score (highest first)
        return sorted(linkedin_profiles, key=lambda x: x['match'], reverse=True)

    def _deduplicate_profiles(self, profiles):
        """
        Deduplicate and rank the final list of profiles
        """
        unique_profiles = {}
        
        for profile in profiles:
            url = profile['url']
            
            # Extract the base profile URL without parameters
            clean_url = url.split('?')[0].rstrip('/')
            
            if clean_url in unique_profiles:
                # Update match score if this instance has a higher score
                if profile['match'] > unique_profiles[clean_url]['match']:
                    unique_profiles[clean_url] = profile
            else:
                unique_profiles[clean_url] = profile
        
        # Calculate confidence score
        final_profiles = []
        for profile in unique_profiles.values():
            # Scale match score to confidence percentage (max match is 20 with all bonuses)
            confidence = min(1.0, profile['match'] / 20.0)
            profile['confidence'] = f"{int(confidence * 100)}%"
            final_profiles.append(profile)
        
        # Sort by match score (highest first)
        return sorted(final_profiles, key=lambda x: x['match'], reverse=True)

    def _extract_best_handle(self, profiles):
        """
        Extract the LinkedIn handle from the highest confidence profile
        """
        if not profiles:
            return None
            
        # Get the highest confidence profile
        best_profile = profiles[0]
        
        # Extract handle from URL
        url = best_profile['url']
        
        return self._extract_handle_from_url(url)
    
    