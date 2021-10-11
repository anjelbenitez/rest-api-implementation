from google.cloud import datastore
from flask import Flask, request, make_response, render_template, jsonify, _request_ctx_stack
import json
import requests

from functools import wraps

from six.moves.urllib.request import urlopen
from flask_cors import cross_origin
from jose import jwt

from os import environ as env
from werkzeug.exceptions import HTTPException

from dotenv import load_dotenv, find_dotenv
from flask import redirect
from flask import session
from flask import url_for
from authlib.integrations.flask_client import OAuth
from six.moves.urllib.parse import urlencode

import http.client

import constants
# import user
import credit_card
import order
# import user_card
import card_order


app = Flask(__name__)
app.secret_key = 'SECRET_KEY'

client = datastore.Client()

CLIENT_ID = ''
CLIENT_SECRET = ''
DOMAIN = 'benitema-final.us.auth0.com'
AUDIENCE = f'https://{DOMAIN}/api/v2/'
GRANT_TYPE = "client_credentials"

CALLBACK_URL = 'https://final-project-benitema.wl.r.appspot.com/callback'

ALGORITHMS = ["RS256"]

# initialize Authlib
oauth = OAuth(app)

auth0 = oauth.register(
    'auth0',
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    api_base_url="https://" + DOMAIN,
    access_token_url="https://" + DOMAIN + "/oauth/token",
    authorize_url="https://" + DOMAIN + "/authorize",
    client_kwargs={
        'scope': 'openid profile email',
    },
)

app.register_blueprint(credit_card.bp)
app.register_blueprint(order.bp)
app.register_blueprint(card_order.bp)

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@app.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/users', methods=['GET'])
def get_users():

    client_id = ''
    client_secret = ''

    if request.method == 'GET':

        if not request.accept_mimetypes['application/json']:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

        base_url = f"https://{DOMAIN}"
        payload =   {
                    'grant_type': GRANT_TYPE,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'audience': AUDIENCE
                    }
        response = requests.post(f'{base_url}/oauth/token', data=payload)
        oauth = response.json()
        access_token = oauth.get('access_token')

        # Add the token to the Authorization header of the request
        headers =   {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                    }
        # url = 'https://' + DOMAIN + '/api/v2/users'
        r = requests.get(f'{base_url}/api/v2/users', headers=headers)
        user_item = []

        keys = ('name', 'user_id')

        data = json.loads(r.text)
        resp = jsonify(data)
        for x in resp.json[:]:
            user_item.append({key: x[key] for key in keys if key in x})

        users = {'Users': user_item}
        
        return(users, 200)

    else:
        return 'Method not recognized'


@app.route('/login', methods=['POST'])
def login_user():
    content = request.get_json()
    username = content["username"]
    password = content["password"]
    body = {'grant_type':'password','username':username,
            'password':password,
            'client_id':CLIENT_ID,
            'client_secret':CLIENT_SECRET
            }
    headers = { 'content-type': 'application/json' }
    url = 'https://' + DOMAIN + '/oauth/token'
    r = requests.post(url, json=body, headers=headers)
    return r.text, 200, {'Content-Type':'application/json'}
            

# exchange code for access token and id token
@app.route('/callback')
def callback_handling():
    # Handles response from token endpoint
    # Store user JWT in flask session.
    id_token = auth0.authorize_access_token()['id_token']

    resp = auth0.get('userinfo')
    userinfo = resp.json()

    session['jwt']=id_token
    session['avatar']=userinfo['picture']
    session['username']=userinfo['name']
    session['user_id']=userinfo['sub']
    return redirect('/dashboard')
        

@app.route('/ui_login')
def ui_login():
    return auth0.authorize_redirect(redirect_uri=CALLBACK_URL)
    

@app.route('/dashboard')
#@requires_auth
def dashboard():
    return render_template('info.html', jwt=session['jwt'], avatar=session['avatar'], username=session['username'], user_id=session['user_id'])

# handles user logout
@app.route('/logout')
def logout():
    # Clear session stored data
    session.clear()
    # user is redirected to logout endpoint
    # after successful logout, user is brought back to welcome page
    params = {'returnTo': url_for('index', _external=True), 'client_id': CLIENT_ID}
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))

if __name__ == '__main__':
    app.run(host='localhost', port=8080, debug=True)
    app.secret_key = 'SECRET_KEY'
