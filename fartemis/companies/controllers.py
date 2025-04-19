import os
import json
import logging
import re

import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from typing import List, Dict, Any, Optional

from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from django.utils import timezone
from django.conf import settings
from langsmith import Client
import langsmith

from langchain_tavily import TavilySearch
from langchain.agents import create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools.render import format_tool_to_openai_function
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain.agents.format_scratchpad import format_to_openai_function_messages
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain.agents import initialize_agent, AgentType, AgentExecutor, create_react_agent
from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
from langchain.tools import tool
from langchain.chains.summarize import load_summarize_chain
from langsmith import Client
import langsmith

from fartemis.companies.models import CompanyProfile, CompanyRole, UserCompanyAssociation
from fartemis.jobboards.models import Job
from fartemis.users.models import User, ContactMethodType, UserContactMethod
from fartemis.llms.clients import LLMClientFactory, LLMProvider



from langchain.agents import AgentExecutor, tool

from .models import CompanyProfile, CompanyResearchReferences, CompanyResearchLog
from .constants import CompanyReviewSentiment, COUNTRY_CODE_MAPPING

logger = logging.getLogger(__name__)

class CompanyResearchController:
    """Controller for company research operations"""
    
    def __init__(self, llm=None, tavily_search=None, langsmith_client=None):
        """
        Initialize the controller with necessary API clients
        
        Args:
            llm: Language model instance (defaults to Claude if None)
            tavily_search: Search tool instance (defaults to TavilySearch if None)
            langsmith_client: LangSmith client for tracing (defaults to Client() if None)
        """
        # Initialize LangSmith client
        self.langsmith_client = langsmith_client or Client()
        
        # Initialize LLM
        if llm is None:
            # Default to Claude
            self.llm = init_chat_model("claude-3-7-latest", model_provider="anthropic")
        else:
            self.llm = llm
        
        # Initialize Tavily search tool
        if tavily_search is None:
            self.tavily_search_tool = TavilySearch(
                max_results=10,
                topic="general",
                search_depth="advanced",
            )
        else:
            self.tavily_search_tool = tavily_search
        
        # Create React agent with the provided or default LLM
        self.agent = create_react_agent(self.llm, [self.tavily_search_tool])
    
    def research_company(self, company_id: int) -> CompanyProfile:
        """
        Research a company using the React agent with Tavily search
        
        Args:
            company_id: ID of the company to research
            
        Returns:
            Updated company profile
        """
        # Get company profile
        company = CompanyProfile.objects.get(id=company_id)
        
        # Build research query
        query = self._build_research_query(company)
        
        # Create LangSmith run
        with langsmith.trace(
            project_name=settings.LANGCHAIN_PROJECT,
            name=f"Company Research: {company.name}",
            tags=["company_research", f"company_{company.id}"]
        ) as run:
            # Add company metadata to the run
            run.add_metadata({
                "company_id": company.id,
                "company_name": company.name,
                "research_type": "company_profile"
            })
            
            # Execute research
            research_result, references = self._execute_research(query)
            
            # Store AI analysis
            company.ai_analysis = research_result
            company.last_sentiment_update = timezone.now()
            company.save()
            
            # Extract and save references
            self._save_references(company, references)
            
            # Log research activity
            self._log_research(company, research_result)
            
            # Extract structured data and update profile
            self._update_profile_from_analysis(company, research_result, references)  # Pass references here
            
            # Add result summary to the run
            run.add_metadata({
                "references_count": len(references),
                "analysis_length": len(research_result)
            })
        
        return company
    
    def _build_research_query(self, company: CompanyProfile) -> str:
        """
        Build a comprehensive research query based on company details
        """
        location_info = ""
        if company.headquarters_city and company.headquarters_state:
            location_info = f" in {company.headquarters_city}, {company.headquarters_state}, {company.headquarters_country}"
        
        query = f"""
I need a comprehensive company profile on {company.name}{location_info}.
You are going to help me understand the type of company and culture as if I am evaluating working for that organization.

Please include:
- Company overview, history, and leadership
- Core business and products/services
- Company culture and work environment
- Growth and market position
- Work-life balance based on employee reviews
- Potential challenges of working there
- Location considerations

Include specific details that would help someone evaluate this company as a potential employer.
"""
        
        return query
    
    def _execute_research(self, query: str) -> tuple:
        """
        Execute research using React agent and extract references
        
        Returns:
            Tuple of (final_result, references)
        """
        # Track references during search
        references = []
        
        # Execute agent with tracing
        with langsmith.trace(
            name="React Agent Execution",
            run_type="chain"
        ) as run:
            # Add query metadata
            run.add_metadata({
                "query": query,
                "tool": "tavily_search"
            })
            
            # Execute the agent
            agent_execution = self.agent.invoke({"messages": query})
            
            # Extract the final answer
            final_result = agent_execution['messages'][-1].content
            
            # Extract references from intermediate steps
            steps = agent_execution.get('intermediate_steps', [])
            for step in steps:
                # Check if this is a tool call
                if step and isinstance(step, list) and len(step) >= 2:
                    action = step[0]
                    observation = step[1]
                    
                    # Check if the action is a tool call to tavily
                    if hasattr(action, 'tool') and action.tool == 'tavily_search_tool':
                        # Get the tool output which contains the search results
                        if observation:
                            try:
                                # Observation might be a string or dictionary, handle both
                                results = observation
                                if isinstance(observation, str):
                                    try:
                                        results = json.loads(observation)
                                    except:
                                        # If it's not JSON, store the raw text
                                        references.append({
                                            "title": "Search Result",
                                            "url": "N/A",
                                            "content": observation,
                                            "query": action.tool_input.get('query', '')
                                        })
                                        continue
                                
                                # Extract references
                                if isinstance(results, list):
                                    for result in results:
                                        if isinstance(result, dict) and 'url' in result:
                                            references.append({
                                                "title": result.get("title", ""),
                                                "url": result.get("url", ""),
                                                "content": result.get("content", ""),
                                                "query": action.tool_input.get('query', '')
                                            })
                            except Exception as e:
                                print(f"Error extracting search results: {e}")
                                run.add_metadata({
                                    "error": str(e),
                                    "error_type": "reference_extraction"
                                })
            
            # Add results metadata
            run.add_metadata({
                "references_count": len(references),
                "result_length": len(final_result)
            })
        
        return final_result, references

    def _find_careers_page(self, company: CompanyProfile, references: List[Dict[str, str]]) -> str:
        """
        Find the careers page URL for a company from references or by searching
        """
        with langsmith.trace(
            name="Find Careers Page",
            run_type="chain"
        ) as run:
            # First, check if we already have it
            if company.careers_page_url:
                return company.careers_page_url
            
            # Try hierarchical URL patterns first if we have a website
            if company.website:
                careers_url = self._try_common_careers_patterns(company.website, company.name)
                if careers_url:
                    run.add_metadata({
                        "source": "pattern_matching",
                        "url": careers_url
                    })
                    return careers_url
            
            # Check if it's in the references we already have
            for ref in references:
                content = ref.get("content", "").lower()
                url = ref.get("url", "").lower()
                title = ref.get("title", "").lower()
                
                careers_keywords = ["careers", "jobs", "work with us", "join us", "career", "job openings"]
                
                # Check if URL or title contains careers keywords
                is_careers_page = any(keyword in url for keyword in careers_keywords) or \
                                any(keyword in title for keyword in careers_keywords)
                
                # Check if it's on the company's official domain
                is_official_domain = False
                if company.website:
                    company_domain = self._extract_domain(company.website)
                    url_domain = self._extract_domain(url)
                    is_official_domain = company_domain == url_domain
                
                # Check if it's NOT a specific job listing
                # Job listings often have numerical IDs at the end of the URL
                is_specific_job = bool(re.search(r'/jobs/\d+', url)) or bool(re.search(r'/careers/\d+', url))
                
                # Only return if it's a careers page AND on official domain AND not a specific job listing
                if is_careers_page and is_official_domain and not is_specific_job:
                    run.add_metadata({
                        "source": "references",
                        "url": url,
                        "is_official": is_official_domain
                    })
                    return url
            
            # If pattern matching and references fail, search specifically for careers page
            # Use more specific query to prioritize official company pages
            query = f"{company.name} official careers jobs listings page"
            
            try:
                search_results = self.tavily_search_tool.invoke(query)
                
                # Handle different response formats
                results_to_process = self._normalize_search_results(search_results)
                
                # Filter and score results to prioritize actual job pages over informational pages
                scored_results = []
                for result in results_to_process:
                    # Skip if not a dictionary
                    if not isinstance(result, dict):
                        continue
                    
                    url = result.get("url", "").lower()
                    title = result.get("title", "").lower()
                    content = result.get("content", "").lower()
                    
                    # Skip URLs that look like specific job listings
                    is_specific_job = bool(re.search(r'/jobs/\d+', url)) or bool(re.search(r'/careers/\d+', url))
                    if is_specific_job:
                        continue
                    
                    # Calculate score based on URL and title matches
                    score = 0
                    
                    # Check if it's on the company's official domain (highest priority)
                    is_official_domain = False
                    if company.website:
                        company_domain = self._extract_domain(company.website)
                        url_domain = self._extract_domain(url)
                        
                        # If it's the official company domain, give it a high score
                        if company_domain == url_domain:
                            is_official_domain = True
                            score += 50  # Much higher weight for official domain
                    
                    # Heavily penalize job board domains
                    job_board_domains = ["indeed.com", "linkedin.com", "glassdoor.com", "monster.com", 
                                        "careerbuilder.com", "ziprecruiter.com", "simplyhired.com",
                                        "dice.com", "theladders.com"]
                    
                    if any(board in url for board in job_board_domains):
                        score -= 30  # Strong penalty for job boards
                    
                    # Look for ideal URL patterns
                    if re.search(r'/careers/jobs/?$', url) or re.search(r'/site/[^/]+/careers/jobs/?$', url):
                        score += 20  # Highest score for the ideal pattern
                    elif '/careers/jobs' in url:
                        score += 15  # High score for variations of careers/jobs
                    elif re.search(r'/jobs/?$', url):
                        score += 10  # Good score for /jobs endpoint
                    elif re.search(r'/careers/?$', url):
                        score += 5   # Lower score for general careers page
                    
                    # Add to scored results if score is positive
                    if score > 0:
                        scored_results.append((score, url, is_official_domain))
                
                # Sort by score (descending)
                scored_results.sort(reverse=True)
                
                # Return the highest scored URL if any found
                if scored_results:
                    best_url = scored_results[0][1]
                    is_official = scored_results[0][2]
                    
                    # Clean up the URL by removing any specific job ID
                    if re.search(r'/jobs/\d+', best_url):
                        best_url = re.sub(r'/jobs/\d+.*', '/jobs', best_url)
                    if re.search(r'/careers/jobs/\d+', best_url):
                        best_url = re.sub(r'/jobs/\d+.*', '', best_url)
                    
                    run.add_metadata({
                        "source": "scored_search_results",
                        "url": best_url,
                        "score": scored_results[0][0],
                        "is_official": is_official
                    })
                    return best_url
                
                # If still not found, use LLM to help
                careers_prompt = f"""
Based on this company information, what is the most likely URL for their official job listings page?

Company: {company.name}
Website: {company.website or 'Unknown'}

Please provide ONLY the URL for the main job listings page, not for any specific job posting.
For example, a good URL would be "company.com/careers/jobs" and not "company.com/careers/jobs/12345".

Provide just the URL and nothing else.
"""
                
                response = self.llm.invoke(careers_prompt)
                suggested_url = response.content.strip()
                
                # Validate that the suggested URL is not a specific job listing
                is_specific_job = bool(re.search(r'/jobs/\d+', suggested_url)) or bool(re.search(r'/careers/\d+', suggested_url))
                if is_specific_job:
                    # Clean up the URL by removing any specific job ID
                    if re.search(r'/jobs/\d+', suggested_url):
                        suggested_url = re.sub(r'/jobs/\d+.*', '/jobs', suggested_url)
                    if re.search(r'/careers/jobs/\d+', suggested_url):
                        suggested_url = re.sub(r'/jobs/\d+.*', '', suggested_url)
                
                run.add_metadata({
                    "source": "llm_suggestion",
                    "url": suggested_url
                })
                
                # Basic validation
                if suggested_url.startswith('http') and '.' in suggested_url:
                    return suggested_url
                
            except Exception as e:
                logger.error(f"Error finding careers page: {e}")
                run.add_metadata({
                    "error": str(e)
                })
            
            return None



    def _normalize_search_results(self, search_results):
        """Helper to normalize different search result formats"""
        results_to_process = []
        
        # Check if search_results is a dictionary (single result or metadata container)
        if isinstance(search_results, dict):
            # If it has a 'results' key, use that
            if 'results' in search_results:
                results_to_process = search_results.get('results', [])
            # Otherwise, treat the dictionary itself as a single result
            else:
                results_to_process = [search_results]
        # Check if search_results is a list (multiple results)
        elif isinstance(search_results, list):
            results_to_process = search_results
        else:
            # If it's neither dict nor list, log the unexpected type
            logger.warning(f"Unexpected search_results type: {type(search_results)}")
        
        return results_to_process
    



    def _extract_domain(self, url: str) -> str:
        """
        Extract the base domain from a URL
        """
        try:
            # Parse the URL
            parsed = urlparse(url)
            
            # Get the netloc (domain with subdomains)
            domain = parsed.netloc
            
            # Remove www. if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Get the base domain (e.g., example.com from subdomain.example.com)
            domain_parts = domain.split('.')
            
            # Handle special cases like .co.uk, .com.au, etc.
            if len(domain_parts) > 2 and domain_parts[-2] in ['co', 'com', 'org', 'net', 'gov', 'edu', 'ac']:
                # For domains like example.co.uk
                if len(domain_parts) > 3:
                    return '.'.join(domain_parts[-3:])
                return '.'.join(domain_parts[-2:])
            
            # Standard case: return last two parts (example.com)
            if len(domain_parts) > 1:
                return '.'.join(domain_parts[-2:])
            
            return domain
        except Exception:
            return url


    def _try_common_careers_patterns(self, website: str, company_name: str) -> Optional[str]:
        """
        Try common patterns for careers pages before searching
        """
        # Extract domain from website
        try:
            parsed_url = urlparse(website)
            domain = parsed_url.netloc
            
            # Remove www. if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Create base domain without subdomains
            domain_parts = domain.split('.')
            if len(domain_parts) > 2:
                base_domain = '.'.join(domain_parts[-2:])
            else:
                base_domain = domain
            
            # Create a session for requests
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            # Try common career subdomain patterns first (highest priority)
            subdomain_patterns = [
                f"https://careers.{base_domain}/jobs",
                f"https://careers.{base_domain}",
                f"https://jobs.{base_domain}",
                f"https://work.{base_domain}",
                f"https://careers.{domain}",
                f"https://jobs.{domain}",
            ]
            
            # Check each subdomain pattern
            for url in subdomain_patterns:
                try:
                    response = session.get(url, timeout=5)
                    if response.status_code == 200:
                        return url
                except Exception:
                    continue
            
            # Try standard path patterns on main domain
            path_patterns = [
                f"{website.rstrip('/')}/jobs",
                f"{website.rstrip('/')}/careers/jobs",
                f"{website.rstrip('/')}/careers",
                f"{website.rstrip('/')}/work-with-us",
                f"{website.rstrip('/')}/join-us",
            ]
            
            # Check each path pattern
            for url in path_patterns:
                try:
                    response = session.get(url, timeout=5)
                    if response.status_code == 200:
                        return url
                except Exception:
                    continue
            
            # If main patterns don't work, try to find links on the main careers page
            try:
                careers_url = f"{website.rstrip('/')}/careers"
                response = session.get(careers_url, timeout=5)
                
                if response.status_code == 200:
                    # Look for links to job listings
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Look for job-related links
                    job_keywords = ['jobs', 'openings', 'positions', 'listings']
                    
                    for link in soup.find_all('a', href=True):
                        link_text = link.text.lower()
                        href = link['href']
                        
                        # Check if link contains job keywords
                        if any(keyword in link_text for keyword in job_keywords):
                            # Handle relative URLs
                            if href.startswith('/'):
                                href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
                            elif not href.startswith('http'):
                                href = f"{website.rstrip('/')}/{href.lstrip('/')}"
                            
                            return href
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"Error trying common patterns: {str(e)}")
        
        return None


    def _convert_to_country_code(self, country_name: str) -> str:
        """
        Convert a country name to its 2-letter ISO code
        """
        if not country_name:
            return None
            
        # Normalize the country name
        normalized = country_name.lower().strip()
        
        # Check if it's already a 2-letter code
        if len(normalized) == 2 and normalized.isalpha():
            return normalized.upper()
            
        # Check our mapping
        if normalized in COUNTRY_CODE_MAPPING:
            return COUNTRY_CODE_MAPPING[normalized]
            
        # If not found, ask LLM (for non-standard country names)
        try:
            country_prompt = f"""
Convert this country name to its 2-letter ISO country code (ISO 3166-1 alpha-2):

Country: {country_name}

Respond with ONLY the 2-letter code in uppercase.
"""
            
            response = self.llm.invoke(country_prompt)
            code = response.content.strip().upper()
            
            # Basic validation
            if len(code) == 2 and code.isalpha():
                return code
        except Exception as e:
            print(f"Error converting country name: {e}")
        
        # If all else fails, return the original
        return country_name

    def _save_references(self, company: CompanyProfile, references: List[Dict[str, str]]) -> None:
        """
        Save extracted references to CompanyResearchReferences
        """
        # Default sentiment
        default_sentiment = "neutral"
        
        with langsmith.trace(
            name="Save References",
            run_type="chain"
        ) as run:
            created_refs = []
            for ref in references:
                # Extract potential title from content if title is empty
                title = ref.get("title", "")
                if not title and ref.get("content"):
                    # Try to extract a title from the first line or sentence
                    content = ref.get("content", "")
                    first_line = content.split('\n')[0]
                    if len(first_line) > 10 and len(first_line) < 100:
                        title = first_line
                    else:
                        first_sentence = content.split('.')[0]
                        if len(first_sentence) > 10 and len(first_sentence) < 100:
                            title = first_sentence
                        else:
                            title = content[:100] + "..." if len(content) > 100 else content
                
                # Add the query to the content for context
                content = ref.get("content", "")
                query = ref.get("query", "")
                if query:
                    content = f"Search Query: {query}\n\n{content}"
                
                # Create reference
                ref_obj = CompanyResearchReferences.objects.create(
                    company=company,
                    title=title or "Untitled Reference",
                    url=ref.get("url", "N/A"),
                    content=content,
                    sentiment=default_sentiment
                )
                created_refs.append(ref_obj.id)
            
            run.add_metadata({
                "company_id": company.id,
                "references_count": len(created_refs),
                "reference_ids": created_refs
            })
    

    def _log_research(self, company: CompanyProfile, research_result: str) -> None:
        """
        Log the research activity
        """
        with langsmith.trace(
            name="Log Research",
            run_type="chain"
        ):
            log = CompanyResearchLog.objects.create(
                company=company,
                content=research_result
            )
    
    def _update_profile_from_analysis(self, company: CompanyProfile, analysis: str, references: List[Dict[str, str]]) -> None:
        """
        Extract structured data from analysis and update the company profile
        """
        with langsmith.trace(
            name="Extract Structured Data",
            run_type="chain"
        ) as run:
            # Use LLM to extract structured data
            extraction_prompt = f"""
            Based on the following company analysis, extract structured data for database storage.
            
            COMPANY ANALYSIS:
            {analysis}
            
            Return a JSON object with the following fields (leave empty if information is not available):
            {{
                "description": "Brief company description",
                "founded_year": 0000,
                "employee_count_min": 0,
                "employee_count_max": 0,
                "headquarters_city": "",
                "headquarters_state": "",
                "headquarters_country": "",
                "is_public": true/false,
                "stock_symbol": "",
                "funding_status": "",
                "glassdoor_rating": 0.0,
                "indeed_rating": 0.0,
                "employee_sentiment_score": 0.0,
                "sentiment_summary": ""
            }}
            """
            
            # Get structured data
            response = self.llm.invoke(extraction_prompt)
            
            try:
                # Extract JSON from response
                json_str = response.content
                
                # If the response contains markdown code blocks, extract JSON from them
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                # data = json.loads(json_str)
                data = self._extract_json_from_llm_response(response.content)
                
                # Log extracted data
                run.add_metadata({
                    "extracted_data": data
                })
                
                # Update company fields with extracted data
                if data.get("description"):
                    company.description = data["description"]
                    
                if data.get("founded_year"):
                    company.founded_year = data["founded_year"]
                    
                if data.get("employee_count_min"):
                    company.employee_count_min = data["employee_count_min"]
                    
                if data.get("employee_count_max"):
                    company.employee_count_max = data["employee_count_max"]
                    
                if data.get("headquarters_city"):
                    company.headquarters_city = data["headquarters_city"]
                    
                if data.get("headquarters_state"):
                    company.headquarters_state = data["headquarters_state"]
                    
                if data.get("headquarters_country"):
                    country_name = data["headquarters_country"]
                    company.headquarters_country = self._convert_to_country_code(country_name)
                    
                if data.get("is_public") is not None:
                    company.is_public = data["is_public"]
                    
                if data.get("stock_symbol"):
                    company.stock_symbol = data["stock_symbol"]
                    
                if data.get("funding_status"):
                    company.funding_status = data["funding_status"]
                    
                if data.get("glassdoor_rating"):
                    company.glassdoor_rating = data["glassdoor_rating"]
                    
                if data.get("indeed_rating"):
                    company.indeed_rating = data["indeed_rating"]
                    
                if data.get("employee_sentiment_score"):
                    company.employee_sentiment_score = data["employee_sentiment_score"]
                    
                if data.get("sentiment_summary"):
                    if not company.sentiment_data_points:
                        company.sentiment_data_points = {}
                    
                    company.sentiment_data_points["summary"] = data["sentiment_summary"]
                
                # Find careers page URL
                careers_url = self._find_careers_page(company, references)
                if careers_url:
                    company.careers_page_url = careers_url
                
                company.save()
                
                run.add_metadata({
                    "company_updated": True,
                    "updated_fields": list(data.keys()) + (["careers_page_url"] if careers_url else [])
                })
                
            except Exception as e:
                error_msg = f"Error extracting structured data: {e}"
                print(error_msg)
                run.add_metadata({
                    "error": error_msg,
                    "company_updated": False
                })

    def _extract_json_from_llm_response(self, response_content):
        """Extract JSON from LLM response, handling differences between models"""
        # Extract JSON from response
        json_str = response_content
        
        # If the response contains markdown code blocks, extract JSON from them
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        # Remove any extra text before or after the JSON object
        json_str = json_str.strip()
        if json_str.startswith("{") and "}" in json_str:
            # Extract just the JSON object
            json_str = json_str[:json_str.rindex("}")+1]
        
        return json.loads(json_str)
    




####### Employee Research Controller #########


class LinkedInProfileFinder:
    """
    Class for finding LinkedIn profiles for people based on name and company
    """
    
    def __init__(self, verbose=False):
        """Initialize the profile finder"""
        self.verbose = verbose
        
        # Configure logging
        if verbose:
            logging.basicConfig(level=logging.INFO)
            
    def find_profile(self, first_name, last_name, company=None, search_engine='both', max_pages=5):
        """
        Find LinkedIn profile for a person
        
        Args:
            first_name: Person's first name
            last_name: Person's last name
            company: Optional company name
            search_engine: 'duckduckgo', 'tavily', or 'both'
            max_pages: Maximum number of pages to analyze
            
        Returns:
            dict: Profile information or None if not found
        """
        logger.info(f"Searching for LinkedIn profile of {first_name} {last_name}")
        if company:
            logger.info(f"Associated with company: {company}")
            
        # Step 1: Perform search
        search_results = []
        
        if search_engine in ['duckduckgo', 'both']:
            logger.info("Using DuckDuckGo search...")
            duckduckgo_results = self._perform_duckduckgo_search(first_name, last_name, company)
            search_results.extend(duckduckgo_results)
        
        if search_engine in ['tavily', 'both']:
            logger.info("Using Tavily search...")
            tavily_results = self._perform_tavily_search(first_name, last_name, company)
            search_results.extend(tavily_results)
            
        if not search_results:
            logger.warning("No search results found")
            return None
            
        # Step 2: Prioritize pages
        prioritized_pages = self._prioritize_pages(search_results, first_name, last_name, company)
        
        # Step 3: Analyze pages for LinkedIn profiles
        linkedin_profiles = []
        pages_analyzed = 0
        
        for page in prioritized_pages:
            if pages_analyzed >= max_pages:
                break
                
            url = page['url']
            priority = page['priority']
            reason = page['reason']
            
            logger.info(f"Analyzing page: {url} (Priority: {priority}, Reason: {reason})")
            
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
                    logger.info(f"Added direct profile: {url} (Match: {match_score})")
            
            # Fetch and parse the page
            page_content = self._fetch_page(url)
            if not page_content:
                continue
                
            # Extract LinkedIn profiles
            page_profiles = self._extract_linkedin_profiles(page_content, first_name, last_name, company)
            
            if page_profiles:
                logger.info(f"Found {len(page_profiles)} potential LinkedIn profiles")
                for profile in page_profiles:
                    linkedin_profiles.append(profile)
            else:
                logger.info("No LinkedIn profiles found on this page")
                
            pages_analyzed += 1
            
        # Deduplicate and rank profiles
        final_profiles = self._deduplicate_profiles(linkedin_profiles)
        
        if not final_profiles:
            logger.warning("No LinkedIn profiles found")
            return None
            
        # Get the best profile
        best_profile = final_profiles[0]
        best_handle = self._extract_handle_from_url(best_profile['url'])
        
        if best_handle:
            # Return full profile info
            return {
                'handle': best_handle,
                'url': best_profile['url'],
                'confidence': best_profile['confidence'],
                'match_score': best_profile['match']
            }
        
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
    
    


##############################
## MAIN CONTROLLER CLASS ##
##############################
class EmployeeResearchController:
    """Controller for researching employees/contacts at companies"""
    
    def __init__(self, company_profile: CompanyProfile, job_id: int = None):
        """Initialize the controller with a company profile and optional job ID"""
        self.company = company_profile
        self.job = None
        
        
        if job_id:
            try:
                self.job = Job.objects.get(id=job_id)
            except Job.DoesNotExist:
                logger.warning(f"Job with ID {job_id} not found")
        
        self.linkedin_finder = LinkedInProfileFinder(verbose=False)

        # Initialize LLM
        self.llm = ChatAnthropic(
            model_name="claude-3-haiku-20240307",
            temperature=0.2,
            anthropic_api_key=settings.ANTHROPIC_API_KEY
        )
        
        # Initialize search tool
        self.tavily_search_tool = TavilySearch(
            max_results=10,
            topic="general",
            search_depth="advanced",
        )
        
        # Create a list of tools
        tools = [self.tavily_search_tool]
        
        # Convert tools to OpenAI functions using the recommended method
        functions = [convert_to_openai_function(t) for t in tools]
        
        # Create prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert researcher focused on finding information about companies and their employees.
            You are thorough, precise, and always cite your sources.
            """),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create the agent
        agent = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x.get("chat_history", []),
                "agent_scratchpad": lambda x: format_to_openai_function_messages(x["intermediate_steps"])
            }
            | prompt
            | self.llm.bind(functions=functions)
            | OpenAIFunctionsAgentOutputParser()
        )
        
        # Create the agent executor
        self.agent_executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=tools,
            verbose=True
        )
        
        # Initialize company roles
        self._init_company_roles()
    
    def _init_company_roles(self):
        """Initialize company roles"""
        self.hiring_manager_role, _ = CompanyRole.objects.get_or_create(
            name="Hiring Manager",
            defaults={"description": "Person responsible for making hiring decisions"}
        )
        
        self.recruiter_role, _ = CompanyRole.objects.get_or_create(
            name="Recruiter",
            defaults={"description": "Person responsible for recruiting candidates"}
        )
        
        self.engineering_lead_role, _ = CompanyRole.objects.get_or_create(
            name="Engineering Lead",
            defaults={"description": "Technical leader who may influence hiring decisions"}
        )
        
        self.executive_role, _ = CompanyRole.objects.get_or_create(
            name="Executive",
            defaults={"description": "C-level or executive who may influence hiring strategy"}
        )
    
    def find_company_employees(self) -> List[User]:
        """Main method to find employees at the company"""
        found_employees = []
        
        # 1. Research company leadership
        leadership_employees = self._find_company_leadership()
        found_employees.extend(leadership_employees)
        
        # 2. Research hiring managers and recruiters
        hiring_employees = self._find_hiring_team()
        found_employees.extend(hiring_employees)
        
        # 3. If we have a specific job, focus on that department
        if self.job:
            job_employees = self._find_employees_for_job()
            found_employees.extend(job_employees)
        
        # Create or update users
        user_objects = self._create_or_update_users(found_employees)
        
        return user_objects
    
    def _find_company_leadership(self) -> List[Dict]:
        """Find company leadership team members using web search"""
        query = f"""
        Who are the specific individuals on the leadership team at {self.company.name}?
        
        I need the names and titles of actual people, such as:
        - The CEO (full name)
        - The CTO (full name)
        - Other executive team members (with their full names)
        
        Important: Only list actual people with their first and last names. Don't include generic role descriptions without names.
        """
        
        try:
            result = self.agent_executor.run(query)
            return self._extract_employees_from_text(result)
        except Exception as e:
            logger.error(f"Error searching for leadership: {str(e)}")
            return []
    
    def _find_hiring_team(self) -> List[Dict]:
        """Find hiring managers and recruiters"""
        query = f"Who are the recruiters and hiring managers at {self.company.name}? Look for people in HR, talent acquisition, and recruiting."
        
        try:
            result = self.agent_executor.run(query)
            employees = self._extract_employees_from_text(result)
            
            # Add role based on title
            for emp in employees:
                title = emp.get("job_title", "").lower()
                
                if any(keyword in title for keyword in ["recruit", "talent", "hr", "people"]):
                    emp["role"] = self.recruiter_role
                    emp["influence_level"] = 7
                else:
                    emp["role"] = self.hiring_manager_role
                    emp["influence_level"] = 8
            
            return employees
        except Exception as e:
            logger.error(f"Error searching for hiring team: {str(e)}")
            return []
    
    def _find_employees_for_job(self) -> List[Dict]:
        """Find employees related to a specific job"""
        if not self.job:
            return []
        
        query = f"""Who would be the hiring manager for this job at {self.company.name}?
        Job title: {self.job.title}
        Job description: {self.job.description[:500]}...
        """
        
        try:
            result = self.agent_executor.run(query)
            employees = self._extract_employees_from_text(result)
            
            # Also extract from job description
            description_employees = self._extract_employees_from_job_description(self.job)
            employees.extend(description_employees)
            
            # Add role and source
            for emp in employees:
                title = emp.get("job_title", "").lower()
                
                if any(keyword in title for keyword in ["manager", "director", "head"]):
                    emp["role"] = self.hiring_manager_role
                    emp["influence_level"] = 9
                elif any(keyword in title for keyword in ["lead", "senior"]):
                    emp["role"] = self.engineering_lead_role
                    emp["influence_level"] = 7
                
                # Set source if not already set
                if "source" not in emp:
                    emp["source"] = f"job_specific_search_{self.job.id}"
            
            return employees
        except Exception as e:
            logger.error(f"Error searching for job-specific employees: {str(e)}")
            return []
    
    def _extract_employees_from_text(self, text: str) -> List[Dict]:
        """Extract employee information from text with improved filtering"""
        employees = []
        
        # More precise name with title pattern
        name_with_title_pattern = r'([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)(?:\s*[-–—:,]\s*|\s+is\s+|\s+as\s+)(?:the\s+)?([^,.]+?(?:Manager|Director|Lead|Head|Officer|CEO|CTO|CFO|COO|Engineer|Developer|Designer|Recruiter|Product|Marketing|Sales|VP|Vice President|President|Chief)(?:[^,.]{0,30}?))'
        
        matches = re.findall(name_with_title_pattern, text)
        for match in matches:
            name, title = match
            name_parts = name.strip().split(" ", 1)
            
            if len(name_parts) >= 2:
                # Skip common false positives
                if self._is_valid_name(name):
                    employee = {
                        "first_name": name_parts[0].strip(),
                        "last_name": name_parts[1].strip(),
                        "job_title": title.strip(),
                        "confidence_score": 0.7
                    }
                    employees.append(employee)
        
        # Extract clearly stated roles with names
        role_name_patterns = [
            r'(?:CEO|Chief Executive Officer)(?:[^,.]{0,10}?)(?:is|:)?\s+([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)',
            r'(?:CTO|Chief Technology Officer)(?:[^,.]{0,10}?)(?:is|:)?\s+([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)',
            r'(?:CFO|Chief Financial Officer)(?:[^,.]{0,10}?)(?:is|:)?\s+([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)',
            r'(?:COO|Chief Operating Officer)(?:[^,.]{0,10}?)(?:is|:)?\s+([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)',
            r'(?:VP|Vice President) of ([^,.]+?)(?:[^,.]{0,10}?)(?:is|:)?\s+([A-Z][a-zA-Z\-\']+(?:\s[A-Z][a-zA-Z\-\']+)+)',
        ]
        
        for pattern in role_name_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Handle both role+name and department+role+name patterns
                if isinstance(match, tuple) and len(match) == 2:
                    department, name = match
                    title = f"VP of {department}"
                else:
                    name = match
                    title = pattern.split('(?:is|:)?')[0].strip()
                    
                if self._is_valid_name(name):
                    name_parts = name.strip().split(" ", 1)
                    if len(name_parts) >= 2:
                        employee = {
                            "first_name": name_parts[0].strip(),
                            "last_name": name_parts[1].strip(),
                            "job_title": title.strip(),
                            "confidence_score": 0.8  # Higher confidence for clear role statements
                        }
                        employees.append(employee)
        
        # Extract email addresses
        email_pattern = r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
        emails = re.findall(email_pattern, text)
        
        # Try to associate emails with employees
        for email in emails:
            name_part = email.split('@')[0]
            
            for employee in employees:
                first_name = employee.get("first_name", "").lower()
                last_name = employee.get("last_name", "").lower()
                
                if first_name in name_part.lower() or last_name in name_part.lower():
                    employee["email"] = email
                    break
        
        return employees
    

    def _is_valid_name(self, name: str) -> bool:
        """Check if a string looks like a valid person name"""
        # Skip common false positives
        invalid_names = [
            "Executive Officer", "Financial Officer", "Technology Officer",
            "Revenue Officer", "Growth Officer", "Operating Officer", 
            "Marketing Officer", "Product Officer", "Other Executives",
            "New York", "San Francisco", "Los Angeles", "United States",
            "Company Profile", "Job Description", "More Information"
        ]
        
        for invalid in invalid_names:
            if invalid.lower() in name.lower():
                return False
        
        # Names should have 2-4 parts
        parts = name.split()
        if len(parts) < 2 or len(parts) > 4:
            return False
        
        # Names shouldn't contain common words
        common_words = ["the", "and", "or", "in", "at", "by", "for", "with", "about"]
        if any(word.lower() in common_words for word in parts):
            return False
        
        # Names should be reasonably sized
        if any(len(part) < 2 for part in parts):
            return False
        if any(len(part) > 15 for part in parts):
            return False
        
        return True


    def _extract_employees_from_job_description(self, job: Job) -> List[Dict]:
        """Extract potential hiring managers from job description"""
        employees = []
        
        if not job.description:
            return employees
            
        description = job.description
        
        # Patterns to identify hiring managers in job descriptions
        employee_patterns = [
            r"report(?:ing)? to (?:the )?([A-Z][a-z]+ [A-Z][a-z]+)",
            r"(?:the )?([A-Z][a-z]+ [A-Z][a-z]+)(?:,)? (?:the )?(?:hiring manager|manager)",
            r"(?:contact|email) ([A-Z][a-z]+ [A-Z][a-z]+)",
            r"(?:questions|inquiries)(?:[^.]*?)(?:to|contact) ([A-Z][a-z]+ [A-Z][a-z]+)"
        ]
        
        for pattern in employee_patterns:
            matches = re.findall(pattern, description)
            
            for match in matches:
                name_parts = match.split(" ", 1)
                if len(name_parts) >= 2:
                    employee = {
                        "first_name": name_parts[0].strip(),
                        "last_name": name_parts[1].strip(),
                        "job_title": self._infer_manager_title(job.title),
                        "role": self.hiring_manager_role,
                        "source": f"job_description_{job.id}",
                        "confidence_score": 0.9,
                        "influence_level": 9
                    }
                    employees.append(employee)

        return employees
    
    def _create_or_update_users(self, employee_data_list: List[Dict]) -> List[User]:
        """
        Create or update User objects based on found employee data
        
        Args:
            employee_data_list: List of dictionaries containing employee information
            
        Returns:
            List of User objects created or updated
        """
        user_objects = []
        
        # First, deduplicate employees
        unique_employees = self._deduplicate_employees(employee_data_list)
        
        for employee_data in unique_employees:
            first_name = employee_data.get("first_name", "").strip()
            last_name = employee_data.get("last_name", "").strip()
            
            # Skip if we don't have at least a name
            if not first_name or not last_name:
                continue
                
            # Get email
            email = employee_data.get("email")
            
            # If no email, generate a placeholder
            if not email:
                email = self._generate_placeholder_email(first_name, last_name, self.company.name)
            
            # Try to find existing user
            try:
                user = User.objects.get(email=email)
                # Update name if missing
                if not user.first_name:
                    user.first_name = first_name
                if not user.last_name:
                    user.last_name = last_name
                
            except User.DoesNotExist:
                # Create new user
                user = User.objects.create(
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )
            
            # Try to find LinkedIn profile
            if not user.linkedin_handle:
                profile_info = self.find_linkedin_profile(first_name, last_name)
                
                if profile_info:
                    # Update user with LinkedIn handle
                    user.linkedin_handle = profile_info['handle']
                    
                    # If we have a UserContactMethod model, create a LinkedIn contact method
                    linkedin_method_type, _ = ContactMethodType.objects.get_or_create(
                        name="LinkedIn Profile",
                        defaults={"category": "other"}
                    )
                    
                    UserContactMethod.objects.update_or_create(
                        user=user,
                        method_type=linkedin_method_type,
                        defaults={"value": profile_info['url']}
                    )
                    
                    # Check if the profile handle suggests a name change
                    if self._might_be_name_change(profile_info['handle'], first_name, last_name):
                        # Store original name in alternate_names
                        if not user.alternate_names:
                            user.alternate_names = []
                            
                        original_name = f"{first_name} {last_name}"
                        if original_name not in user.alternate_names:
                            user.alternate_names.append(original_name)
            
            # Save user
            user.save()
            
            # Create or update company association
            association, created = UserCompanyAssociation.objects.update_or_create(
                user=user,
                company=self.company,
                defaults={
                    "job_title": employee_data.get("job_title"),
                    "department": employee_data.get("department"),
                    "role": employee_data.get("role"),
                    "influence_level": employee_data.get("influence_level", 5),
                    "notes": f"Discovered via {employee_data.get('source', 'research')}. Confidence: {employee_data.get('confidence_score', 0.5)}",
                    "relationship_status": "to_contact"
                }
            )
            
            user_objects.append(user)
            
        return user_objects
    
    def _deduplicate_employees(self, employees: List[Dict]) -> List[Dict]:
        """Deduplicate employee data, merging information when appropriate"""
        # Group by name
        employee_dict = {}
        
        for emp in employees:
            first_name = emp.get("first_name", "").strip().lower()
            last_name = emp.get("last_name", "").strip().lower()
            
            if not first_name or not last_name:
                continue
                
            key = f"{first_name}|{last_name}"
            
            if key in employee_dict:
                # Merge records
                existing = employee_dict[key]
                
                # Keep non-empty values from the new record
                for field in ["job_title", "email", "linkedin_url"]:
                    if not existing.get(field) and emp.get(field):
                        existing[field] = emp.get(field)
                
                # Keep the source with higher confidence
                if emp.get("confidence_score", 0) > existing.get("confidence_score", 0):
                    existing["source"] = emp.get("source")
                    existing["confidence_score"] = emp.get("confidence_score")
                
                # Keep the highest influence level
                existing["influence_level"] = max(
                    existing.get("influence_level", 0),
                    emp.get("influence_level", 0)
                )
                
                # Keep role preference order: hiring manager > recruiter > other
                if (emp.get("role") == self.hiring_manager_role and 
                    existing.get("role") != self.hiring_manager_role):
                    existing["role"] = emp.get("role")
                    
            else:
                # Add new record
                employee_dict[key] = emp.copy()
                # Ensure first_name and last_name are properly capitalized
                employee_dict[key]["first_name"] = first_name.capitalize()
                employee_dict[key]["last_name"] = last_name.capitalize()
        
        return list(employee_dict.values())
    
    def _infer_manager_title(self, job_title: str) -> str:
        """Infer a likely manager title based on a job title"""
        if not job_title:
            return "Manager"
            
        job_title = job_title.lower()
        
        if "senior" in job_title or "sr." in job_title:
            base_title = job_title.replace("senior", "").replace("sr.", "").strip()
            return f"Director of {base_title}"
        elif "engineer" in job_title:
            return "Engineering Manager"
        elif "designer" in job_title:
            return "Design Manager"
        elif "product" in job_title:
            return "Product Manager"
        elif "data" in job_title:
            return "Data Science Manager"
        elif "marketing" in job_title:
            return "Marketing Manager"
        elif "sales" in job_title:
            return "Sales Manager"
        else:
            return f"Manager of {job_title}"
    
    def _generate_placeholder_email(self, first_name: str, last_name: str, company_name: str) -> str:
        """Generate a placeholder email for a user"""
        # Clean inputs
        first = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower()
        last = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower()
        company = re.sub(r'[^a-zA-Z0-9]', '', company_name).lower()
        
        return f"{first}.{last}.{company}@fartemis.placeholder"
    


    def find_linkedin_profile(self, first_name, last_name):
        """
        Find LinkedIn profile for a person using the profile finder
        
        Args:
            first_name: Person's first name
            last_name: Person's last name
            
        Returns:
            dict: Profile information or None if not found
        """
        # Use the company name from this controller
        company_name = self.company.name
        
        # Use the profile finder to find the LinkedIn profile
        profile_info = self.linkedin_finder.find_profile(
            first_name=first_name,
            last_name=last_name,
            company=company_name,
            search_engine='both',
            max_pages=5
        )
        
        return profile_info

    def _extract_field(self, text, field_name):
        """Extract a field from formatted text"""
        lines = text.split('\n')
        for line in lines:
            if line.startswith(f"{field_name}:"):
                return line.split(f"{field_name}:")[1].strip()
        return None



    def _extract_linkedin_profile_url(self, search_results):
        """Extract LinkedIn profile URL from search results"""
        
        # Process results depending on format
        results_to_process = []
        if isinstance(search_results, dict) and "results" in search_results:
            results_to_process = search_results.get("results", [])
        elif isinstance(search_results, list):
            results_to_process = search_results
        
        # Look for LinkedIn profile URLs
        for result in results_to_process:
            if not isinstance(result, dict):
                continue
                
            url = result.get("url", "")
            
            # Check if it's a direct LinkedIn profile
            if "linkedin.com/in/" in url:
                return url
        
        # Check content for LinkedIn profile URLs
        linkedin_pattern = r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+'
        
        for result in results_to_process:
            if not isinstance(result, dict):
                continue
                
            content = result.get("content", "")
            
            if content and isinstance(content, str):
                profile_urls = re.findall(linkedin_pattern, content)
                if profile_urls:
                    return profile_urls[0]
        
        return None


    def _might_be_name_change(self, handle, first_name, last_name):
        """
        Check if a LinkedIn handle suggests a name change
        
        Args:
            handle: LinkedIn handle
            first_name: First name we know
            last_name: Last name we know
            
        Returns:
            bool: True if might be a name change, False otherwise
        """
        handle_lower = handle.lower()
        first_lower = first_name.lower()
        last_lower = last_name.lower()
        
        # Direct match - not a name change
        if handle_lower == f"{first_lower}{last_lower}" or handle_lower == f"{last_lower}{first_lower}":
            return False
            
        # Common variations - not a name change
        variations = [
            f"{first_lower}.{last_lower}",
            f"{first_lower}-{last_lower}",
            f"{first_lower}_{last_lower}",
            f"iam{first_lower}{last_lower}",
            f"{first_lower[0]}{last_lower}",
            f"{first_lower}{last_lower[0]}"
        ]
        
        if any(variation in handle_lower for variation in variations):
            return False
            
        # If first name is in handle but last name is not, might be a name change
        if first_lower in handle_lower and last_lower not in handle_lower:
            return True
            
        # If neither name component is in the handle, might be a name change
        if first_lower not in handle_lower and last_lower not in handle_lower:
            return True
            
        return False

        
    def _check_for_name_change(self, profile_data, original_first, original_last):
        """
        Check if there's evidence of a name change in the profile data
        
        Args:
            profile_data: LinkedIn profile data dictionary
            original_first: Original first name
            original_last: Original last name
            
        Returns:
            dict: Name change information or None if no change detected
        """
        if not profile_data or not isinstance(profile_data, dict):
            return None
            
        try:
            # Get the LinkedIn profile URL
            profile_url = profile_data.get("url", "")
            if not profile_url:
                return None
                
            # Extract the handle from the URL
            if "/in/" in profile_url:
                handle = profile_url.split("/in/")[-1].rstrip("/")
            else:
                handle = ""
            
            # Check if handle contains the original names
            original_first_lower = original_first.lower()
            original_last_lower = original_last.lower()
            handle_lower = handle.lower()
            
            # If handle doesn't seem to match the original name, might indicate a name change
            if (original_first_lower not in handle_lower) and (original_last_lower not in handle_lower):
                # Use the title to try to extract the current name
                title = profile_data.get("title", "")
                
                # Try to extract name from LinkedIn title
                current_name = None
                if " - " in title:
                    current_name = title.split(" - ")[0].strip()
                elif " | " in title:
                    current_name = title.split(" | ")[0].strip()
                elif ":" in title:
                    current_name = title.split(":")[0].strip()
                
                if current_name and len(current_name.split()) >= 2:
                    # Make sure it looks like a name (not just "LinkedIn" or "Profile")
                    if not any(word.lower() in current_name.lower() for word in ["linkedin", "profile"]):
                        return {
                            "original_name": f"{original_first} {original_last}",
                            "current_name": current_name,
                            "confidence": 0.7
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for name change: {str(e)}")
            return None