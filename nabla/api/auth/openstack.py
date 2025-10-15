import os

import ovh

# See https://help.ovhcloud.com/csm/en-api-getting-started-ovhcloud-api?id=kb_article_view&sysparm_article=KB0042777

# Get credentials from environment variables
application_key = os.getenv("OVH_APPLICATION_KEY")
application_secret = os.getenv("OVH_APPLICATION_SECRET")
consumer_key = os.getenv("OVH_CONSUMER_KEY")


# Instantiate. Visit https://eu.api.ovh.com/createToken/?GET=/me
# or https://www.ovh.com/auth/api/createToken
# to get your credentials https://www.ovh.com/manager/#/iam/api-keys
client = ovh.Client(
    endpoint="ovh-eu",
    application_key=application_key,
    application_secret=application_secret,
    consumer_key=consumer_key,
)


# Print nice welcome message
print("Welcome", client.get("/me")["firstname"])


# Request RO, /me API access
ck = client.new_consumer_key_request()
ck.add_rules(ovh.API_READ_ONLY, "/me")

# Request token
validation = ck.request()
print("Btw, your 'consumerKey' is '%s'" % validation["consumerKey"])
