#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
from linkedin_api import Linkedin

# Authenticate using any Linkedin user account credentials
api = Linkedin('', '')

# GET a profile
profile = api.get_profile('iamstevenscott')

print(profile)


# GET a profiles contact info
contact_info = api.get_profile_contact_info('iamstevenscott')
print(contact_info)


# GET 1st degree connections of a given profile
connections = api.get_profile_connections('iamstevenscott')
print(connections)



