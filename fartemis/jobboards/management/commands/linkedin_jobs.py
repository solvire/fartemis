# /home/solvire/Documents/projects/jobagent/fartemis/fartemis/jobboards/management/commands/linkedin_jobs.py

"""
Usage Example:
./manage.py linkedin_jobs --keywords "Python Engineer" --location "Raleigh, NC" --levels="4,5" --limit=10 --verbose
./manage.py linkedin_jobs --keywords "Data Scientist" --geo-id 103644278 --limit=5 # New York City Geo ID

Fetches jobs from LinkedIn using Selenium to automate browser interaction
and stores the raw job data (summary, details, skills) as FeedItem objects
for later processing. Requires LinkedIn credentials in Django settings and
a WebDriver (e.g., chromedriver) installed and accessible.
"""
import time
import random
import logging
import re # For extracting job ID from URL
import requests # For URL quoting helper

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

# Selenium Imports
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    from selenium.webdriver.chrome.options import Options as ChromeOptions # Alias to avoid name clash
    from selenium.webdriver.chrome.service import Service as ChromeService # For specific path
    selenium_available = True
except ImportError:
    selenium_available = False
    webdriver = None
    By = None
    Keys = None
    WebDriverWait = None
    EC = None
    TimeoutException = None
    NoSuchElementException = None
    WebDriverException = None
    ChromeOptions = None
    ChromeService = None
    logger = logging.getLogger(__name__)
    logger.error("Selenium library not found. Please install it: pip install selenium")


# Project models
from fartemis.jobboards.models import FeedSource, FeedItem
# Import the sanitization helper function
from fartemis.inherits.helpers import sanitize_unicode_nulls

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch jobs from LinkedIn via Selenium and store raw data as FeedItems'

    def add_arguments(self, parser):
        parser.add_argument('--keywords', type=str, default='Python Engineer',
                            help='Search keywords for jobs (e.g., "Software Engineer", "Product Manager")')
        parser.add_argument('--location', type=str,
                            help='Location name for job search (e.g., "London", "Remote", "United States")')
        parser.add_argument('--geo-id', type=str,
                            help='Optional: LinkedIn GeoID for precise location targeting (obtain via linkedin_geoid_finder command)')
        parser.add_argument('--limit', type=int, default=25,
                            help='Maximum number of job listings to fetch')
        parser.add_argument('--levels', type=str, default='4,5', # Defaulting to Mid-Senior, Director codes
                            help='Comma-separated experience level codes: 1=Internship, 2=Entry, 3=Associate, 4=Mid-Senior, 5=Director, 6=Executive')
        parser.add_argument('--verbose', action='store_true',
                            help='Display verbose output including partial job descriptions.')
        # Add arguments for WebDriver path and headless mode if desired
        parser.add_argument('--chromedriver-path', type=str, default=None,
                            help='Optional: Path to the chromedriver executable.')
        parser.add_argument('--headless', action='store_true',
                            help='Run Chrome in headless mode (no visible browser window).')


    def handle(self, *args, **options):
        if not selenium_available:
            self.stderr.write(self.style.ERROR("Selenium is required but not installed. Aborting."))
            return

        # Extract options
        keywords = options['keywords']
        location = options['location']
        geo_id = options['geo_id']
        limit = options['limit']
        # Directly use the codes provided, assuming user knows them
        levels = options['levels'].split(',') if options['levels'] else []
        verbose = options['verbose']
        chromedriver_path = options['chromedriver_path']
        headless = options['headless']


        # Validate location requirement: Need either location name or geo_id
        if not location and not geo_id:
             self.stderr.write(self.style.ERROR("Please provide either --location or --geo-id."))
             return

        # Get linkedin feed source
        feed_source = self._get_linkedin_feed_source()
        if not feed_source:
            return

        # Get LinkedIn credentials
        username = getattr(settings, 'LINKEDIN_USERNAME', None)
        password = getattr(settings, 'LINKEDIN_PASSWORD', None)

        if not username or not password:
            self.stderr.write(self.style.ERROR('LINKEDIN_USERNAME and/or LINKEDIN_PASSWORD not found in Django settings.'))
            return

        # --- Initialize WebDriver ---
        driver = None
        try:
            self.stdout.write("Initializing WebDriver...")
            chrome_options = ChromeOptions()
            if headless:
                self.stdout.write("Running in headless mode.")
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--disable-gpu') # Often needed for headless
            # Common arguments for running in containers/servers
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36") # Example UA

            if chromedriver_path:
                service = ChromeService(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Assumes chromedriver is in system PATH
                driver = webdriver.Chrome(options=chrome_options)

            driver.implicitly_wait(5) # Default wait time for elements
            self.stdout.write(self.style.SUCCESS("WebDriver initialized."))

            # --- LinkedIn Login ---
            self._linkedin_login(driver, username, password)

            # --- Perform Job Search ---
            # This function now returns a list of dicts with summary info
            job_summaries_data = self._search_linkedin_jobs(driver, keywords, location, geo_id, levels, limit)

            if not job_summaries_data:
                 self.stdout.write(self.style.WARNING("No job summaries collected from search results."))
                 # No need to return here, just proceed to finish
            else:
                # --- Process Each Job ---
                search_timestamp = timezone.now().isoformat()
                jobs_processed = 0
                jobs_skipped = 0
                total_to_process = len(job_summaries_data)

                self.stdout.write(f"\nProcessing {total_to_process} collected job summaries...")

                for i, job_summary in enumerate(job_summaries_data, 1):
                    job_id = job_summary.get('linkedin_job_id')
                    job_link = job_summary.get('job_link')

                    if not job_id or not job_link:
                        self.stderr.write(self.style.WARNING(f"Skipping summary #{i} due to missing ID or link."))
                        jobs_skipped += 1
                        continue

                    job_guid = f"linkedin_{job_id}"

                    # Check if FeedItem already exists
                    if FeedItem.objects.filter(guid=job_guid, source=feed_source).exists():
                        if verbose:
                            self.stdout.write(f'Job {job_id} (GUID: {job_guid}) already exists. Skipping...')
                        jobs_skipped += 1
                        continue

                    # Add random delay before fetching details
                    sleep_time = random.uniform(2.0, 5.0)
                    if verbose:
                        self.stdout.write(f'Sleeping for {sleep_time:.2f} seconds before fetching details for job {job_id}...')
                    time.sleep(sleep_time)

                    # Fetch detailed description using Selenium
                    self.stdout.write(f"Fetching details for job {i}/{total_to_process} (ID: {job_id})...")
                    detailed_info = self._get_job_details(driver, job_link)

                    # Combine summary and detailed info
                    combined_data = {
                        'job_summary': job_summary, # Contains title, company, location_text, link, id from scrape
                        'job_details': detailed_info, # Contains description_html, maybe skills
                        'extracted_skills': detailed_info.get('extracted_skills', []), # Get skills if scraped
                        'skills_data': None, # We don't have the raw skills API response anymore
                        'query_metadata': {
                            'keywords': keywords,
                            'location_name': location,
                            'geo_id': geo_id,
                            'levels': levels,
                            'search_timestamp': search_timestamp,
                            'fetch_timestamp': timezone.now().isoformat()
                        }
                    }

                    # Sanitize data
                    try:
                        sanitized_data = sanitize_unicode_nulls(combined_data)
                    except Exception as sanitize_err:
                         logger.error(f"Error sanitizing data for job {job_id}: {sanitize_err}", exc_info=True)
                         self.stderr.write(self.style.ERROR(f"Failed to sanitize data for job {i} ({job_id}). Skipping."))
                         jobs_skipped += 1
                         continue

                    # Create FeedItem
                    try:
                        FeedItem.objects.create(
                            guid=job_guid,
                            source=feed_source,
                            raw_data=sanitized_data,
                            is_processed=False,
                            fetched_at=timezone.now()
                        )
                        jobs_processed += 1
                        self.stdout.write(self.style.SUCCESS(f"Saved job {i}: {job_summary.get('title')}"))
                    except Exception as db_err:
                        self.stderr.write(self.style.ERROR(f"Database error saving job {job_id}: {db_err}"))
                        logger.error(f"Failed to save FeedItem for job {job_id}", exc_info=True)
                        jobs_skipped +=1


                # --- Post-loop summary ---
                feed_source.last_fetched = timezone.now()
                feed_source.save(update_fields=['last_fetched'])

                self.stdout.write("-" * 30)
                self.stdout.write(self.style.SUCCESS(f'LinkedIn job fetch completed.'))
                self.stdout.write(f'  Total job summaries scraped: {len(job_summaries_data)}') # Use count of collected items
                self.stdout.write(f'  New jobs saved to database: {jobs_processed}')
                self.stdout.write(f'  Jobs skipped (already exist or error): {jobs_skipped}')


        except WebDriverException as e:
             logger.error(f"WebDriver error occurred: {e}", exc_info=True)
             self.stderr.write(self.style.ERROR(f"A WebDriver error occurred: {e}. Check driver path/version."))
        except Exception as e:
            logger.error(f"An unexpected error occurred during Selenium job fetch: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))
        finally:
            if driver:
                self.stdout.write("Quitting WebDriver...")
                driver.quit()
                self.stdout.write("WebDriver quit.")


    def _get_linkedin_feed_source(self):
        """Gets or creates the LinkedIn FeedSource."""
        try:
            feed_source, created = FeedSource.objects.get_or_create(
                name='linkedin',
                defaults={
                    'description': 'Jobs fetched directly from LinkedIn via Selenium', # Updated description
                    'url': 'https://www.linkedin.com/jobs/',
                    'source_type': 'scrape' # Changed type to reflect method
                }
            )
            if created:
                 self.stdout.write(self.style.SUCCESS(f'Created LinkedIn FeedSource (ID: {feed_source.id})'))
            else:
                 self.stdout.write(f'Using existing LinkedIn FeedSource (ID: {feed_source.id})')
            return feed_source
        except Exception as e:
            logger.error(f"Failed to get or create LinkedIn FeedSource: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f'Error accessing FeedSource model: {str(e)}'))
            return None


    def _linkedin_login(self, driver, username, password):
        """Handles LinkedIn login using Selenium."""
        self.stdout.write("Navigating to LinkedIn login page (https://www.linkedin.com/login)...")
        driver.get("https://www.linkedin.com/login")
        wait = WebDriverWait(driver, 15) # Wait up to 15 seconds

        try:
            username_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
            self.stdout.write("Username field found.")
            username_field.send_keys(username)
            time.sleep(random.uniform(0.5, 1.2))

            password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
            self.stdout.write("Password field found.")
            password_field.send_keys(password)
            time.sleep(random.uniform(0.5, 1.2))

            # Try submitting the form via the password field first
            password_field.send_keys(Keys.RETURN)
            self.stdout.write("Login form submitted. Waiting for redirect...")

            # Wait for the URL to change to the feed page
            wait.until(EC.url_contains("linkedin.com/feed/"))
            self.stdout.write(self.style.SUCCESS("Login appears successful! Current URL: " + driver.current_url))

        except TimeoutException:
            self.stderr.write(self.style.ERROR("Timeout waiting for login elements or feed page redirect."))
            # Check for CAPTCHA or other issues
            captcha_challenge = driver.find_elements(By.XPATH, "//*[contains(text(), 'security check') or contains(text(), 'CAPTCHA') or contains(@id, 'captcha')]")
            if captcha_challenge:
                 self.stderr.write(self.style.ERROR("LinkedIn may be presenting a CAPTCHA or security check."))
                 driver.save_screenshot("linkedin_login_captcha_error.png")
                 self.stdout.write("Screenshot saved as linkedin_login_captcha_error.png")
                 raise Exception("LinkedIn CAPTCHA/Security Check required during login.")
            else:
                 driver.save_screenshot("linkedin_login_timeout_error.png")
                 self.stdout.write("Screenshot saved as linkedin_login_timeout_error.png")
                 raise Exception("Login timed out. Check page load state or network.")
        except NoSuchElementException as e:
            self.stderr.write(self.style.ERROR(f"Could not find login element (ID='username' or ID='password'): {e.msg}"))
            driver.save_screenshot("linkedin_login_element_not_found_error.png")
            self.stdout.write("Screenshot saved as linkedin_login_element_not_found_error.png")
            raise
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred during login: {e}"))
            driver.save_screenshot("linkedin_login_unexpected_error.png")
            self.stdout.write("Screenshot saved as linkedin_login_unexpected_error.png")
            logger.debug(f"Page source at login error:\n{driver.page_source[:2000]}")
            raise


    def _search_linkedin_jobs(self, driver, keywords, location_name, geo_id, levels, limit):
        """Performs job search on LinkedIn and scrapes summary data."""
        self.stdout.write(f"Starting job search for '{keywords}' in '{location_name or f'GeoID {geo_id}'}'...")

        base_search_url = "https://www.linkedin.com/jobs/search/"
        params = {}
        if keywords: params["keywords"] = keywords
        # Prioritize geoId if provided, otherwise use location name
        if geo_id: params["geoId"] = geo_id
        elif location_name: params["location"] = location_name
        # Add experience level filter parameter if levels are provided
        if levels: params["f_E"] = ",".join(levels) # e.g., f_E=4,5

        # Build URL
        query_string = "&".join([f"{k}={requests.utils.quote(str(v))}" for k, v in params.items() if v])
        search_url = f"{base_search_url}?{query_string}&origin=JOB_SEARCH_PAGE_JOB_FILTER&refresh=true" # Add common params

        self.stdout.write(f"Navigating to job search URL: {search_url}")
        driver.get(search_url)
        time.sleep(random.uniform(4, 7)) # Allow longer initial load

        # --- Updated Selectors ---
        job_card_selector = "div.job-search-card" # Updated based on inspecting typical LI job search
        title_selector = "h3.base-search-card__title"
        company_selector = "h4.base-search-card__subtitle a" # Link within the subtitle
        location_selector = "span.job-search-card__location"
        link_selector = "a.base-card__full-link" # Main link for the card

        job_summaries = []
        processed_job_links = set()
        last_height = driver.execute_script("return document.body.scrollHeight")
        jobs_collected_count = 0
        no_new_jobs_streak = 0

        self.stdout.write("Scrolling and extracting job summaries...")

        while jobs_collected_count < limit:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, job_card_selector))
                )
            except TimeoutException:
                self.stdout.write(self.style.WARNING("No job cards found with selector or timeout waiting."))
                break # Exit loop if no job cards appear

            job_elements = driver.find_elements(By.CSS_SELECTOR, job_card_selector)

            if not job_elements:
                logger.warning("No job elements found with selector. Check page structure.")
                break

            initial_count = len(job_summaries)
            self.stdout.write(f"Found {len(job_elements)} potential job cards in view.")

            for job_elem in job_elements:
                if jobs_collected_count >= limit:
                    break
                try:
                    job_link_element = job_elem.find_element(By.CSS_SELECTOR, link_selector)
                    job_link = job_link_element.get_attribute('href')

                    if not job_link or job_link in processed_job_links:
                        continue

                    job_id = None
                    if "/jobs/view/" in job_link:
                        job_id_match = re.search(r'/jobs/view/(\d+)/', job_link)
                        if job_id_match:
                            job_id = job_id_match.group(1)

                    # Extract other details safely
                    try: title = job_elem.find_element(By.CSS_SELECTOR, title_selector).text.strip()
                    except NoSuchElementException: title = "Title Not Found"

                    try: company_link = job_elem.find_element(By.CSS_SELECTOR, company_selector)
                    except NoSuchElementException: company = "Company Not Found"
                    else: company = company_link.text.strip()

                    try: location_text = job_elem.find_element(By.CSS_SELECTOR, location_selector).text.strip()
                    except NoSuchElementException: location_text = "Location Not Found"


                    summary_data = {
                        'title': title,
                        'company_name': company,
                        'location_text': location_text,
                        'job_link': job_link,
                        'linkedin_job_id': job_id
                    }

                    job_summaries.append(summary_data)
                    processed_job_links.add(job_link)
                    jobs_collected_count += 1
                    if self.verbose:
                        self.stdout.write(f"  Collected ({jobs_collected_count}/{limit}): {title} at {company} (ID: {job_id or 'N/A'})")

                except NoSuchElementException as e_inner:
                     if self.verbose: self.stdout.write(self.style.WARNING(f"  Could not parse a job card fully (missing element: {e_inner.msg}), skipping it."))
                     logger.warning(f"Partial parse for job card. HTML snippet: {job_elem.get_attribute('outerHTML')[:500]}...", exc_info=False)
                except Exception as e_parse:
                    logger.error(f"Error parsing individual job card: {e_parse}", exc_info=self.verbose)

            if jobs_collected_count >= limit:
                self.stdout.write(f"Reached desired limit of {limit} jobs.")
                break

            # Check if new jobs were actually added in this pass
            if len(job_summaries) == initial_count:
                no_new_jobs_streak += 1
                self.stdout.write(self.style.WARNING(f"No new unique jobs collected in this scroll pass ({no_new_jobs_streak})."))
            else:
                no_new_jobs_streak = 0 # Reset streak

            # If no new jobs found for a few consecutive scrolls, assume end or stuck
            if no_new_jobs_streak >= 3:
                 self.stdout.write(self.style.WARNING("No new jobs found for 3 consecutive scrolls. Stopping scroll."))
                 break


            # --- Scrolling Logic ---
            self.stdout.write("Scrolling down...")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2.5, 4.5)) # Wait for load

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                 # Check for "see more jobs" button
                try:
                    see_more_button = driver.find_element(By.XPATH, "//button[contains(., 'See more jobs')]") # More generic XPath
                    if see_more_button.is_displayed() and see_more_button.is_enabled():
                        self.stdout.write("Scrolling stopped, trying 'See more jobs' button...")
                        try:
                            driver.execute_script("arguments[0].scrollIntoView(true);", see_more_button) # Scroll button into view
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", see_more_button)
                            time.sleep(random.uniform(3, 5))
                            last_height = new_height # Update height after potential click
                            continue # Continue loop to check for new cards
                        except Exception as click_err:
                            self.stdout.write(self.style.ERROR(f"Failed to click 'See more jobs' button: {click_err}"))
                            break
                    else:
                        self.stdout.write("Scrolled to bottom, no more new jobs found via scroll or button.")
                        break
                except NoSuchElementException:
                    self.stdout.write("Scrolled to bottom, no 'see more jobs' button found.")
                    break
            last_height = new_height

        self.stdout.write(self.style.SUCCESS(f"Finished scrolling/scraping. Collected {len(job_summaries)} job summaries."))
        return job_summaries


    def _get_job_details(self, driver, job_url):
        """Fetches detailed job description from its individual page using Selenium."""
        self.stdout.write(f"Navigating to job detail page: {job_url}")
        if not job_url:
            return {'description_html': 'Error: No job URL provided.', 'extracted_skills': []}

        try:
            driver.get(job_url)
            wait = WebDriverWait(driver, 15) # Wait up to 15 seconds for elements

            # --- Selector for the main description container ---
            # Common possibilities (Inspect the actual job page):
            # div.jobs-description-content__text
            # section.jobs-description
            # div#job-details (or similar ID)
            # article.jobs-description__container
            description_selector = "section.jobs-description" # START WITH THIS - NEEDS VERIFICATION
            self.stdout.write(f"Waiting for description element ({description_selector})...")

            description_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, description_selector))
            )
            self.stdout.write("Description element found.")
            # Get inner HTML to preserve formatting like lists, paragraphs
            description_html = description_element.get_attribute('innerHTML').strip()
            logger.debug(f"Extracted description HTML (length: {len(description_html)})")

            # --- Selector for Skills (Optional - Inspect job page) ---
            # Skills might be within the description or in a separate section.
            # Examples:
            # ul.job-details-skill-list li span
            # a.job-details-skill-button
            # //h3[text()='Skills']/following-sibling::ul//li # XPath example
            skills_selector = "a.job-details-skill-button" # START WITH THIS - NEEDS VERIFICATION
            skills_list = []
            try:
                skill_elements = driver.find_elements(By.CSS_SELECTOR, skills_selector)
                if skill_elements:
                    for skill_elem in skill_elements:
                        skill_text = skill_elem.text.strip()
                        if skill_text:
                            skills_list.append(skill_text)
                    self.stdout.write(f"Extracted skills: {skills_list}")
                else:
                     if self.verbose: self.stdout.write("No skill elements found with the specified selector.")
            except Exception as skill_err:
                 logger.warning(f"Could not extract skills from {job_url}: {skill_err}", exc_info=False)
                 if self.verbose: self.stdout.write(self.style.WARNING(f"Could not extract skills: {skill_err}"))


            return {
                'description_html': description_html,
                'extracted_skills': skills_list,
            }
        except TimeoutException:
            self.stderr.write(self.style.WARNING(f"Timeout waiting for job details elements on {job_url}"))
            driver.save_screenshot(f"job_detail_timeout_{int(time.time())}.png")
            return {'description_html': 'Error: Timeout loading details.', 'extracted_skills': []}
        except Exception as e:
            logger.error(f"Error scraping details for {job_url}: {e}", exc_info=self.verbose)
            self.stderr.write(self.style.ERROR(f"Could not scrape details for {job_url}: {e}"))
            driver.save_screenshot(f"job_detail_error_{int(time.time())}.png")
            return {'description_html': f'Error: Could not scrape details ({e}).', 'extracted_skills': []}


    # This function is no longer used for filtering in the primary flow,
    # but kept in case the library expects numeric codes for a specific param.
    # The primary logic now uses the codes directly in the f_E URL parameter.
    def _prepare_experience_filters(self, level_codes):
        """Validates numeric level codes and prepares the filter dict if needed."""
        if not level_codes:
            return None

        valid_codes = {'1', '2', '3', '4', '5', '6'}
        validated_codes = [code for code in level_codes if code in valid_codes]

        if not validated_codes:
            self.stdout.write(self.style.WARNING(f"No valid experience level codes provided in '{','.join(level_codes)}'. Ignoring experience filter."))
            return None

        # Return structure potentially expected by some library function (if used elsewhere)
        # For direct URL construction with f_E, this dict isn't strictly needed,
        # but we keep the validation logic.
        return {'experience': validated_codes}