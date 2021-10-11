from flask import Blueprint, request, make_response, render_template, jsonify, _request_ctx_stack
from google.cloud import datastore
import json
import constants
import requests

from functools import wraps

from six.moves.urllib.request import urlopen
from flask_cors import cross_origin
from jose import jwt

from os import environ as env
from werkzeug.exceptions import HTTPException

from dotenv import load_dotenv, find_dotenv
from flask import Flask
from flask import redirect
from flask import session
from flask import url_for
from authlib.integrations.flask_client import OAuth
from six.moves.urllib.parse import urlencode

client = datastore.Client()

bp = Blueprint('credit_card', __name__, url_prefix='/credit_cards')

CLIENT_ID = ''
CLIENT_SECRET = ''
DOMAIN = 'benitema-final.us.auth0.com'

ALGORITHMS = ["RS256"]

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@bp.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response
    
def verify_jwt(request):
    auth_header = request.headers['Authorization'].split();
    token = auth_header[1]
    
    jsonurl = urlopen("https://"+ DOMAIN+"/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.JWTError:
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Invalid header. "
                            "Use an RS256 signed JWT Access Token"}, 401)
    if unverified_header["alg"] == "HS256":
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Invalid header. "
                            "Use an RS256 signed JWT Access Token"}, 401)
    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=CLIENT_ID,
                issuer="https://"+ DOMAIN+"/"
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code": "token_expired",
                            "description": "token is expired"}, 401)
        except jwt.JWTClaimsError:
            raise AuthError({"code": "invalid_claims",
                            "description":
                                "incorrect claims,"
                                " please check the audience and issuer"}, 401)
        except Exception:
            raise AuthError({"code": "invalid_header",
                            "description":
                                "Unable to parse authentication"
                                " token."}, 401)

        return payload
    else:
        raise AuthError({"code": "no_rsa_key",
                            "description":
                                "No RSA key in JWKS"}, 401)


@bp.route('', methods=['POST','GET','PUT','PATCH','DELETE'])
def credit_cards_get_post():
    """
    An API endpoint for adding a new credit_card or getting a list of all the 
    credit_cards in the collection
    """

    # creates a new credit_card
    if request.method == 'POST':

        if request.content_type != 'application/json':
            raise AuthError({"code": "Unsupported Media Type",
                            "description":
                            "Unsupported media type. "
                            "Please use application/json with your request"}, 415)

        # get JSON data from the request body
        content = request.get_json()

        # do not create if an attribute is missing
        if "card_number" not in content.keys() or "type" not in content.keys() \
            or "expiration" not in content.keys() or "cvv_code" not in content.keys():
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Missing attribute. "
                                "The request object is missing at least one of the required attributes"}, 400)

        # do not accept invalid attribute/s
        for key in content.keys():
            if key == "card_number" or key == "type" or key == "expiration" or key == "cvv_code":
                continue
            else:
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Invalid attribute. "
                                "The request contains an invalid attribute"}, 400)
        
        # do a query for all the credit_cards in the credit_cards collection
        credit_cards_query = client.query(kind=constants.credit_cards)
        results = list(credit_cards_query.fetch())
        
        # make sure card number is unique
        for e in results:
            if content["card_number"] == e["card_number"]:
                raise AuthError({"code": "Forbidden",
                                "description":
                                "Card number not unique. "
                                "This credit card number already exists. Please enter a different card number"}, 403)

        # if valid, create a new credit card with the given attributes
        else:
            if request.headers.get('Authorization') is None:
                raise AuthError({"code": "invalid_header",
                                "description":
                                "Invalid header. "
                                "JWT Access Token is missing"}, 401)
            payload = verify_jwt(request)

            if request.accept_mimetypes['application/json']:
                new_credit_card = datastore.entity.Entity(key=client.key(constants.credit_cards))
                new_credit_card.update({"card_number": content["card_number"], "type": content["type"],
                "expiration": content["expiration"], "cvv_code": content["cvv_code"], "owner": payload["sub"]})
                client.put(new_credit_card)

                # add id and self attributes
                new_credit_card["id"] = new_credit_card.key.id
                new_credit_card["self"] = "https://" + request.host + "/credit_cards/" \
                    + str(new_credit_card.key.id)
                new_credit_card["orders"] = []


                res = make_response(json.dumps(new_credit_card))
                res.mimetype = 'application/json'
                res.status_code = 201

                # return newly created credit_card
                return res

            else:
                raise AuthError({"code": "Not Acceptable",
                    "description":
                    "Not acceptable. "
                    "Only application/json content type supported"}, 406)

    elif request.method == 'GET':

        if request.headers.get('Authorization') is None:
            raise AuthError({"code": "invalid_header",
                            "description":
                            "Invalid header. "
                            "JWT Access Token is missing"}, 401)
        payload = verify_jwt(request)

        if request.accept_mimetypes['application/json']:

            relationship_query = client.query(kind=constants.card_order)
            relationship_results = list(relationship_query.fetch())

            count = 0
            
            # do a query for all the credit_cards in the credit_cards collection
            query = client.query(kind=constants.credit_cards)
            query.add_filter('owner', '=', payload['sub'])
            query_r = list(query.fetch())

            # set limit of credit_cards per page to 5
            q_limit = int(request.args.get('limit', '5'))
            q_offset = int(request.args.get('offset', '0'))
            g_iterator = query.fetch(limit= q_limit, offset=q_offset)
            pages = g_iterator.pages
            results = list(next(pages))
            
            # build next_url
            if g_iterator.next_page_token:
                next_offset = q_offset + q_limit
                next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
            else:
                next_url = None

            # add an 'id' and 'self' attribute (not stored in Datastore)
            # to each credit_card
            for e in results:
                e["id"] = e.key.id
                e["self"] = "https://" + request.host + "/credit_cards/" + str(e.key.id)
                e["orders"] =[]

                for f in relationship_results:
                    if e["id"] == f["card_id"] and f["orders"] != []:
                        e["orders"] = f["orders"]
            
            for g in query_r:
                count += 1

            output = {"credit_cards": results}

            # if there are more credit_cards to be viewed, output next_url
            if next_url:
                output["next"] = next_url
            
            output["items_in_collection"] = count

            # return the list of credit_cards and their attributes
            res = make_response(json.dumps(output))             
            res.mimetype = 'application/json'
            res.status_code = 200

            return res

        else:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

    elif request.method == 'DELETE' or request.method == 'PUT' or request.method == 'PATCH':
        raise AuthError({"code": "method_not_allowed",
                        "description":
                        "Method not allowed. "
                        "Cannot delete or make changes to the /credit_cards URL"}, 405)

    else:
        return 'Method not recognized'

@bp.route('/<credit_card_id>', methods=['DELETE','GET','PATCH','PUT'])
def credit_cards_put_patch_delete(credit_card_id):
    """
    An API endpoint for deleting a credit_card or for getting a specific credit_card
    """

    credit_card_found = False

    # do a query for all the credit_cards in the credit_cards collection
    credit_cards_query = client.query(kind=constants.credit_cards)
    results = list(credit_cards_query.fetch())

    relationship_query = client.query(kind=constants.card_order)
    relationship_results = list(relationship_query.fetch())

    # add an 'id' attribute to each credit_card
    # check if the credit_card exists in the collection
    for e in results:
        e["id"] = e.key.id
        if credit_card_id == json.dumps(e["id"]):
            credit_card_found = True
    
    # if credit_card not found, return 404 error
    if credit_card_found == False:
        raise AuthError({"code": "Not Found",
                        "description":
                        "Credit card not found. "
                        "No credit_card with this credit_card_id exists"}, 404)

    credit_card_key = client.key(constants.credit_cards, int(credit_card_id))
    credit_card = client.get(key=credit_card_key)

    # deletes an existing credit_card
    if request.method == 'DELETE':

        if request.headers.get('Authorization') is None:
            raise AuthError({"code": "invalid_header",
                            "description":
                            "Invalid header. "
                            "JWT Access Token is missing"}, 401)

        payload = verify_jwt(request)
        
        if credit_card["owner"] == payload['sub']:
        # delete credit_card from credit_cards collection
            r_id = None
            credit_card["id"] = credit_card.key.id

            for e in relationship_results:
                if credit_card["id"] == e["card_id"] and e["orders"] != []:
                    r_id = e.key.id
                    relationship_key = client.key(constants.card_order, int(r_id))
                    client.delete(relationship_key)

            client.delete(credit_card_key)
            return ('',204)
        else:
            raise AuthError({"code": "Forbidden",
                            "description":
                            "Forbidden. "
                            "Only the owner of this credit card is authorized to delete it."}, 403)
    
    # edits an existing credit card's attribute/s
    elif request.method == 'PATCH':

        if request.headers.get('Authorization') is None:
            raise AuthError({"code": "invalid_header",
                            "description":
                            "Invalid header. "
                            "JWT Access Token is missing"}, 401)

        payload = verify_jwt(request)
        
        if credit_card["owner"] == payload['sub']:

            if request.content_type != 'application/json':
                raise AuthError({"code": "Unsupported Media Type",
                                "description":
                                "Unsupported media type. "
                                "Please use application/json with your request"}, 415)
            
            # get JSON data from the request body
            content = request.get_json()

            # nothing to modify if all 4 attributes are missing
            if "card_number" not in content.keys() and "type" not in content.keys() \
                and "expiration" not in content.keys() and "cvv_code" not in content.keys():
                    raise AuthError({"code": "Bad Request",
                                    "description":
                                    "Bad request. "
                                    "No valid attributes to modify"}, 400)

            # do not accept invalid attribute/s
            for key in content.keys():
                if key == "card_number" or key == "type" or key == "expiration" or key == "cvv_code":
                    continue
                else:
                    raise AuthError({"code": "Bad Request",
                                    "description":
                                    "Invalid attribute. "
                                    "The request contains an invalid attribute"}, 400)

            for e in results:
                
                # make sure card number is unique
                if "card_number" in content.keys():

                    # if current credit card's number matches a credit card number from the
                    # existing collection
                    if content["card_number"] == e["card_number"]:

                        # if current credit_card's id != to the matching credit_card's id,
                        # we know that we are not modifying the current credit_card
                        if credit_card.key.id != e["id"]:
                            # return uniqueness error
                            raise AuthError({"code": "Forbidden",
                                            "description":
                                            "Card number not unique. "
                                            "This credit card number already exists. Please enter a different card number"}, 403)
            
            # if valid, modify a credit_card with the passed attribute/s
            else:
                if request.accept_mimetypes['application/json']:

                    if "card_number" in content.keys():
                        credit_card.update({"card_number": content["card_number"]})
                    if "type" in content.keys():
                        credit_card.update({"type": content["type"]})
                    if "expiration" in content.keys():
                        credit_card.update({"expiration": content["expiration"]})
                    if "cvv_code" in content.keys():
                        credit_card.update({"cvv_code": content["cvv_code"]})

                    client.put(credit_card)

                    # add 'id' and 'self' attributes to the credit_card
                    credit_card["id"] = credit_card.key.id
                    credit_card["self"] = "https://" + request.host + "/credit_cards/" \
                        + str(credit_card.key.id)
                    credit_card["orders"] =[]

                    for f in relationship_results:
                        if credit_card["id"] == f["card_id"] and f["orders"] != []:
                            credit_card["orders"] = f["orders"]
                            
                    res = make_response(json.dumps(credit_card))
                    res.mimetype = 'application/json'
                    res.status_code = 200

                    # return modified credit_card
                    return res

                else:
                    raise AuthError({"code": "Not Acceptable",
                        "description":
                        "Not acceptable. "
                        "Only application/json content type supported"}, 406)

        else:
            raise AuthError({"code": "Forbidden",
                            "description":
                            "Forbidden. "
                            "Only the owner of this credit card is authorized to edit it."}, 403)
    
    elif request.method == 'PUT':

        if request.headers.get('Authorization') is None:
            raise AuthError({"code": "invalid_header",
                            "description":
                            "Invalid header. "
                            "JWT Access Token is missing"}, 401)

        payload = verify_jwt(request)
        
        if credit_card["owner"] == payload['sub']:

            if request.content_type != 'application/json':
                raise AuthError({"code": "Unsupported Media Type",
                                "description":
                                "Unsupported media type. "
                                "Please use application/json with your request"}, 415)
            
            # get JSON data from the request body
            content = request.get_json()

            # do not modify if one or more required attribute/s is missing
            if "card_number" not in content.keys() or "type" not in content.keys() \
                or "expiration" not in content.keys() or "cvv_code" not in content.keys():
                    raise AuthError({"code": "Bad Request",
                                    "description":
                                    "Missing attribute. "
                                    "The request object is missing at least one of the required attributes"}, 400)
                    
            # do not accept invalid attribute/s
            for key in content.keys():
                if key == "card_number" or key == "type" or key == "expiration" or key == "cvv_code":
                    continue
                else:
                    raise AuthError({"code": "Bad Request",
                                    "description":
                                    "Invalid attribute. "
                                    "The request contains an invalid attribute"}, 400)

            for e in results:

                # make sure card number is unique
                if "card_number" in content.keys():

                    # if current credit card's number matches a credit card number from the
                    # existing collection
                    if content["card_number"] == e["card_number"]:

                        # if current credit_card's id != to the matching credit_card's id,
                        # we know that we are not modifying the current credit_card
                        if credit_card.key.id != e["id"]:
                            # return uniqueness error
                            raise AuthError({"code": "Forbidden",
                                            "description":
                                            "Card number not unique. "
                                            "This credit card number already exists. Please enter a different card number"}, 403)
            
            # if valid, modify a credit_card with the passed attribute/s
            else:
                if request.accept_mimetypes['application/json']:
                    credit_card.update({"card_number": content["card_number"], "type": content["type"],
                    "expiration": content["expiration"], "cvv_code": content["cvv_code"]})
                    client.put(credit_card)

                    # add 'id' and 'self' attributes to the credit_card
                    credit_card["id"] = credit_card.key.id
                    credit_card["self"] = "https://" + request.host + "/credit_cards/" \
                        + str(credit_card.key.id)
                    credit_card["orders"] =[]

                    for f in relationship_results:
                        if credit_card["id"] == f["card_id"] and f["orders"] != []:
                            credit_card["orders"] = f["orders"]
                    
                    res = make_response(json.dumps(credit_card))
                    res.mimetype = 'application/json'
                    res.status_code = 200

                    # return modified credit_card
                    return res

                else:
                    raise AuthError({"code": "Not Acceptable",
                        "description":
                        "Not acceptable. "
                        "Only application/json content type supported"}, 406)

        else:
            raise AuthError({"code": "Forbidden",
                            "description":
                            "Forbidden. "
                            "Only the owner of this credit card is authorized to edit it."}, 403)

    # gets a specific credit_card with the given id, either as JSON or HTML
    elif request.method == 'GET':

        if request.headers.get('Authorization') is None:
            raise AuthError({"code": "invalid_header",
                            "description":
                            "Invalid header. "
                            "JWT Access Token is missing"}, 401)

        payload = verify_jwt(request)
        
        if credit_card["owner"] == payload['sub']:

            if request.accept_mimetypes['application/json']:
                base_url = '/credit_cards/' + credit_card_id

                # add 'id' and 'self' attributes to the credit_card
                credit_card["id"] = credit_card.key.id
                credit_card["self"] = "https://" + request.host + base_url
                credit_card["orders"] =[]

                for e in relationship_results:
                    if credit_card["id"] == e["card_id"] and e["orders"] != []:
                        credit_card["orders"] = e["orders"]

                res = make_response(json.dumps(credit_card))             
                res.mimetype = 'application/json'
                res.status_code = 200

                # return credit_card and its attributes as JSON
                return res

            else:
                raise AuthError({"code": "Not Acceptable",
                    "description":
                    "Not acceptable. "
                    "Only application/json content type supported"}, 406)
        else:
            raise AuthError({"code": "Forbidden",
                    "description":
                    "Forbidden. "
                    "Only the owner of this credit card is authorized to view it."}, 403)
    else:
        return 'Method not recognized'
