#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
from linkedin_api import Linkedin

# Authenticate using any Linkedin user account credentials
api = Linkedin('', '')

# GET a profile
# profile = api.get_profile('iamstevenscott')

# print(profile)


# GET a profiles contact info
# contact_info = api.get_profile_contact_info('iamstevenscott')
# print(contact_info)


# GET 1st degree connections of a given profile
# connections = api.get_profile_connections('iamstevenscott')
# print(connections)


# Search for Python developer jobs
# jobs = api.search_jobs(
#     keywords='Data Scientist',
#     location_name='Raleigh, North Carolina',
#     # limit=5
# )
jobs = api.search_jobs(
    keywords='Python Developer',
    # location_name='McLean, VA',
    location_name='73013',
    limit=5,
    distance=25
)
print(jobs)


# Process the results
# Get detailed job information
for job in jobs:
    # Extract key information
    job_id = job['entityUrn'].split(':')[-1]

    # Get full job details
    details = api.get_job(job_id)

    print(f"Title: {details.get('title', 'unknown')}")
    print(f"Company: {details.get('companyDetails', {}).get('name', 'unknown')}")
    print(f"Location: {details.get('formattedLocation', 'unknown')}")
    print(f"Remote? {details.get('workRemoteAllowed', 'unknown')}")
    print(f"Description: {details.get('description', 'unknown')}")

    # Get job skills
    skills = api.get_job_skills(job_id)
    if skills:
        print("\nRequired Skills:")
        for skill in skills.get('skillMatchStatuses', []):
            print(f"- {skill.get('skill', {}).get('name', 'unknown')}")
    print("---")


