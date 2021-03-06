#
# http request handlers
#

from splunk import auth, search
import splunk.rest 
import splunk.bundle as bundle
import splunk.entity as entity
import splunklib.client as client

import httplib2, urllib, os, time
import base64
import json
import xml.etree.ElementTree as ET
import os

from oauth2client.client import OAuth2WebServerFlow
from googleapiclient.discovery import build
import jsonbyteify

"""
NOTE: To use this script, the following Python library dependencies need 
to be installed in the Splunk Python environment:

pip install --upgrade google-api-python-client

google-api-python-client
uritemplate
six
httplib2
oauth2client
simplejson
pyasn1
pyasn1-modules
rsa

jsonbyteify
"""

# set our path to this particular application directory (which is suppose to be <appname>/bin)
app_dir = os.path.dirname(os.path.abspath(__file__))

# define the web content directory (needs to be <appname>/web directory)
web_dir = app_dir + "/web"

# filepath to admin credentials for connection
admin_credentials_filepath = os.path.join(app_dir, 'admin_credentials.json')
REST_config_filepath = os.path.join(app_dir, 'REST_config.json')

class fitbit_callback(splunk.rest.BaseRestHandler):

    """
    Fitbit OAuth2 Callback Endpoint
    """
    def handle_GET(self):
        
        # Parse authorization code from URL query string
        authCode = None
        errorCode = None
        queryParams = self.request['query']
        for param in queryParams:
            if param == 'code':
                authCode = queryParams['code']
        
        if authCode is None:
            # No Authorization Code, return 400
            self.response.setStatus(400)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Auth Code")
            return
        
        admin_credentials = None
        with open(admin_credentials_filepath, 'r') as file:
            admin_credentials = jsonbyteify.json_load_byteified(file)
        
        if admin_credentials is None:
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Admin Credentials")
            return
        
        REST_config = None
        with open(REST_config_filepath, 'r') as file:
            REST_config = jsonbyteify.json_load_byteified(file)
            
        REST_config = REST_config['fitbit']
        
        # Pull Client ID and Secret from Fitbit ModInput password store
        c = client.connect(host='localhost', port='8089', username=admin_credentials['username'], password=admin_credentials['password'])
        c.namespace.owner = 'nobody'
        c.namespace.app = REST_config['password_namespace']
        passwords = c.storage_passwords
                
        # Look for Client Secret
        password = None
        for entry in passwords:
            if entry.realm.lower() == REST_config['realm']:
                password = entry
                
        if password is None:
            # No password configured for Fitbit, return 500
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No client password provided")
        
        # Exchange authorization code for OAuth2 token
        http = httplib2.Http()
        clientId = password.username
        clientSecret = password.clear_password
        callback_url = REST_config['callback_uri']
        auth_uri = 'https://www.fitbit.com/oauth2/authorize'
        token_url = 'https://api.fitbit.com/oauth2/token'
        
        encoded_id_secret = base64.b64encode( (clientId + ':' + clientSecret) )
        authHeader_value = ('Basic ' + encoded_id_secret)
        headers = {'Authorization': authHeader_value, 'Content-Type': 'application/x-www-form-urlencoded'}
        data = {'clientId': clientId, 'grant_type': 'authorization_code', 'redirect_uri': callback_url, 'code': authCode}
        body = urllib.urlencode(data)
        resp, content = http.request(token_url, 'POST', headers=headers, body=body)
        token_json = jsonbyteify.json_loads_byteified(content)
        
        user_id = token_json['user_id']
        access_token = token_json['access_token']
        
        # Get User Profile JSON
        userProfile_url = 'https://api.fitbit.com/1/user/' + user_id + '/profile.json'
        authHeader_value = ('Bearer ' + access_token)
        headers = {'Authorization': authHeader_value, 'Content-Type': 'application/x-www-form-urlencoded'}
        body = ''
        resp, content = http.request(userProfile_url, 'GET', headers=headers, body=body)
        profile_json = jsonbyteify.json_loads_byteified(content)
        full_name = profile_json['user']['fullName']
        
        # Store id, name, and token in KV store
        c.namespace.app = REST_config['kv_namespace']
        collection_name = 'fitbit_tokens'
        
        if collection_name not in c.kvstore:
            # Create the KV Store if it doesn't exist
            c.kvstore.create(collection_name)
        
        kvstore = c.kvstore[collection_name]

        # Check if user already exists in KV Store
        userExists = False
        try:
            kv_user_dict = kvstore.data.query_by_id(user_id)
            userExists = True
        except:
            userExists = False
        
        kv_jsonstring = json.dumps({'_key': user_id, 'id': user_id, 'name': full_name, 'token': token_json})
        
        if userExists:
            # Update entry
            key = jsonbyteify._byteify(kv_user_dict['_key'])
            kvstore.data.update(key, kv_jsonstring)
        else:
            # Create new entry
            kvstore.data.insert(kv_jsonstring)
        
        # Return Success message
        self.response.setStatus(200)
        self.response.setHeader('content-type', 'text/xml')
        #self.response.write(kv_jsonstring)
        self.addMessage("Success", "Your Fitbit account was successfully added!")
        
    # listen to all verbs
    handle_POST = handle_DELETE = handle_PUT = handle_VIEW = handle_GET
    
    
class google_callback(splunk.rest.BaseRestHandler):

    """
    Google OAuth2 Callback Endpoint
    """
    def handle_GET(self):
    
        # Parse authorization code from URL query string
        authCode = None
        errorCode = None
        queryParams = self.request['query']
        for param in queryParams:
            if param == 'code':
                authCode = queryParams['code']
        
        if authCode is None:
            # No Authorization Code, return 400
            self.response.setStatus(400)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Auth Code")
            return
        
        admin_credentials = None
        with open(admin_credentials_filepath, 'r') as file:
            admin_credentials = jsonbyteify.json_load_byteified(file)
        
        if admin_credentials is None:
            # No admin credentials
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Admin Credentials")
            return
        
        REST_config = None
        with open(REST_config_filepath, 'r') as file:
            REST_config = jsonbyteify.json_load_byteified(file)
            
        REST_config = REST_config['google']

        
        # Pull Client ID and Secret from Google ModInput password store
        c = client.connect(host='localhost', port='8089', username=admin_credentials['username'], password=admin_credentials['password'])
        c.namespace.owner = 'nobody'
        c.namespace.app = REST_config['password_namespace']
        passwords = c.storage_passwords
        
        # Look for Client Secret
        password = None
        for entry in passwords:
            if entry.realm.lower() == REST_config['realm']:
                password = entry
                
        if password is None:
            # No password configured for Google, return 500
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No client password provided")
            return
        
        # Create flow object
        flow = OAuth2WebServerFlow(
            client_id = password.username,
            client_secret = password.clear_password,
            scope='https://www.googleapis.com/auth/fitness.activity.read https://www.googleapis.com/auth/fitness.body.read https://www.googleapis.com/auth/userinfo.profile',
            redirect_uri=REST_config['callback_uri'],
            access_type = 'offline'
            )
        
        # Exchange authorization code for token
        credentials = flow.step2_exchange(authCode)
        http_auth = credentials.authorize(httplib2.Http())
        
        # Use token to retrieve Full Name
        # Build service object
        service = build('plus', 'v1', http=http_auth)
        profile = service.people().get(userId='me').execute()
        user_id = profile['id']
        name = profile['name']
        full_name = name['givenName'] + " " + name['familyName']
        
        # Store id, name, and token in KV store
        credentials_json = jsonbyteify.json_loads_byteified(credentials.to_json())
        token_json = credentials_json['token_response']
        
        # Store id, name, and token in KV store
        c.namespace.app = REST_config['kv_namespace']
        collection_name = 'google_tokens'
        
        if collection_name not in c.kvstore:
            # Create the KV Store if it doesn't exist
            c.kvstore.create(collection_name)
        
        kvstore = c.kvstore[collection_name]
        
        # Check if user already exists in KV Store
        userExists = False
        try:
            kv_user_dict = kvstore.data.query_by_id(user_id)
            userExists = True
        except:
            userExists = False
        
        kv_jsonstring = json.dumps({'_key': user_id, 'id': user_id, 'name': full_name, 'token': token_json})
        
        if userExists:
            # Update entry
            key = jsonbyteify._byteify(kv_user_dict['_key'])
            kvstore.data.update(key, kv_jsonstring)
        else:
            # Create new entry
            kvstore.data.insert(kv_jsonstring)
        
        # Write Success message
        self.response.setStatus(200)
        self.response.setHeader('content-type', 'text/xml')
        #self.response.write(kv_jsonstring)
        self.addMessage("Success", "Your Google account was successfully added!")
        
    # listen to all verbs
    handle_POST = handle_DELETE = handle_PUT = handle_VIEW = handle_GET


class microsoft_callback(splunk.rest.BaseRestHandler):

    """
    Microsoft OAuth2 Callback Endpoint
    """
    def handle_GET(self):
    
        # Parse authorization code from URL query string
        authCode = None
        errorCode = None
        queryParams = self.request['query']
        for param in queryParams:
            if param == 'code':
                authCode = queryParams['code']
        
        if authCode is None:
            # No Authorization Code, return 400
            self.response.setStatus(400)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Auth Code")
            return
        
        admin_credentials = None
        with open(admin_credentials_filepath, 'r') as file:
            admin_credentials = jsonbyteify.json_load_byteified(file)
        
        REST_config = None
        with open(REST_config_filepath, 'r') as file:
            REST_config = jsonbyteify.json_load_byteified(file)
            
        REST_config = REST_config['microsoft']

        if admin_credentials is None:
            # No Admin credentials
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No Admin credentials")
            return
        
        # Pull Client ID and Secret from Microsoft ModInput password store
        c = client.connect(host='localhost', port='8089', username=admin_credentials['username'], password=admin_credentials['password'])
        c.namespace.owner = 'nobody'
        c.namespace.app = REST_config['password_namespace']
        passwords = c.storage_passwords
        
        # Look for Client Secret
        password = None
        for entry in passwords:
            if entry.realm.lower() == REST_config['realm']:
                password = entry
                
        if password is None:
            # No password configured for Google, return 500
            self.response.setStatus(500)
            self.response.setHeader('content-type', 'text/xml')
            #self.addMessage("Error", "Sorry, your account could not be added.")
            self.addMessage("Error", "No client password provided")
            return
        
        # Create flow object
        flow = OAuth2WebServerFlow(
            client_id = password.username,
            client_secret = password.clear_password,
            scope='mshealth.ReadProfile mshealth.ReadActivityHistory mshealth.ReadDevices mshealth.ReadActivityLocation offline_access',
            redirect_uri=REST_config['callback_uri'],
            auth_uri='https://login.live.com/oauth20_authorize.srf',
            token_uri='https://login.live.com/oauth20_token.srf'
            )
        
        # Exchange authorization code for token
        credentials = flow.step2_exchange(authCode)
        credentials_json = jsonbyteify.json_loads_byteified(credentials.to_json())
        token_json = credentials_json['token_response']
        access_token = token_json['access_token']
        user_id = token_json['user_id']
        
        # Use token to retrieve Full Name from User Profile
        userProfile_url = 'https://api.microsofthealth.net/v1/me/Profile'
        authHeader_value = ('bearer ' + access_token)
        headers = {'Authorization': authHeader_value}
        body = ""
        http = httplib2.Http()
        resp, content = http.request(userProfile_url, 'GET', headers=headers, body=body)
        
        profile_json = jsonbyteify.json_loads_byteified(content)
        full_name = profile_json['firstName']
        
        # Store id, name, and token in KV store
        c.namespace.app = REST_config['kv_namespace']
        collection_name = 'microsoft_tokens'
        
        if collection_name not in c.kvstore:
            # Create the KV Store if it doesn't exist
            c.kvstore.create(collection_name)
        
        kvstore = c.kvstore[collection_name]
        
        # Check if user already exists in KV Store
        userExists = False
        try:
            kv_user_dict = kvstore.data.query_by_id(user_id)
            userExists = True
        except:
            userExists = False
        
        kv_jsonstring = json.dumps({'_key': user_id, 'id': user_id, 'name': full_name, 'token': token_json})
        
        if userExists:
            # Update entry
            key = jsonbyteify._byteify(kv_user_dict['_key'])
            kvstore.data.update(key, kv_jsonstring)
        else:
            # Create new entry
            kvstore.data.insert(kv_jsonstring)
        
        # Return Success message
        self.response.setStatus(200)
        self.response.setHeader('content-type', 'text/xml')
        #self.response.write(kv_jsonstring)
        self.addMessage("Success", "Your Microsoft account was successfully added!")
        
    # listen to all verbs
    handle_POST = handle_DELETE = handle_PUT = handle_VIEW = handle_GET