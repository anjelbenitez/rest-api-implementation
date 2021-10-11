from flask import Blueprint, request, jsonify, make_response
from google.cloud import datastore
import json
import constants

client = datastore.Client()

bp = Blueprint('card_order', __name__, url_prefix='/credit_cards/<card_id>/orders')

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@bp.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

@bp.route('', methods=['GET'])
def cards_cards_get(card_id):
    """
    An API endpoint for getting all the credit cards on a given order
    """
    if request.accept_mimetypes['application/json']:
        card_found = False

        # do a query for all the cards in the credit cards collection 
        # add an 'id' attribute to each card
        # check if the card exists in the collection
        credit_cards_query = client.query(kind=constants.credit_cards)
        credit_cards_results = list(credit_cards_query.fetch())
        for e in credit_cards_results:
            e["id"] = e.key.id
            if card_id == json.dumps(e["id"]):
                card_found = True

        # if card not found, return 404 error
        if card_found == False:
            raise AuthError({"code": "Not Found",
                            "description":
                            "Credit card not found. "
                            "No credit_card with this credit_card_id exists"}, 404)

        # otherwise do a query for all the relationships in the 
        # card_order collection
        # add a 'self' attribute to each relationship
        # check if the order exists in the card_order collection (that is, if
        # the order currently has a credit card on file)
        relationship_query = client.query(kind=constants.card_order)
        relationship_results = list(relationship_query.fetch())
        for f in relationship_results:
            f["self"] = "https://" + request.host + "/credit_cards/" \
                + card_id + "/orders"
            if int(card_id) == f["card_id"] and f["orders"] != []:
                res = make_response(json.dumps(f))
                res.mimetype = 'application/json'
                res.status_code = 200
                return res

        raise AuthError({"code": "OK",
                        "description":
                        "No Orders. "
                        "There are no orders associated with this credit card"}, 200)
    else:
        raise AuthError({"code": "Not Acceptable",
            "description":
            "Not acceptable. "
            "Only application/json content type supported"}, 406)

@bp.route('/<order_id>', methods=['PUT','DELETE','GET'])
def cards_cards_post_patch(card_id, order_id):
    """
    An API endpoint for adding, getting, or removing a relationship 
    between an order and a credit card
    """

    order_found = False
    card_found = False
    relationship_found = False
    card = None

    # do a query for all the cards in the credit cards collection 
    # add an 'id' attribute to each card
    # check if the card exists in the collection
    credit_cards_query = client.query(kind=constants.credit_cards)
    credit_cards_results = list(credit_cards_query.fetch())
    for e in credit_cards_results:
        e["id"] = e.key.id
        if card_id == json.dumps(e["id"]):
            card_found = True

    # do a query for all the orders in the orders collection 
    # add an 'id' attribute to each order
    # check if the order exists in the collection    
    orders_query = client.query(kind=constants.orders)
    orders_results = list(orders_query.fetch())
    for f in orders_results:
        f["id"] = f.key.id
        if order_id == json.dumps(f["id"]):
            order_found = True
    
    # do a query for all the relationships in the card_order collection 
    # check if a relationship exists between the credit card and an order     
    relationship_query = client.query(kind=constants.card_order)
    relationship_results = list(relationship_query.fetch())
    for g in relationship_results:
        if order_id in json.dumps(g["orders"]):
            relationship_found = True
            card = g["card_id"]
    
    # creates a new relationship between an order and a credit card
    if request.method == 'PUT':
        if not request.accept_mimetypes['application/json']:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)
        
        # if order or credit card can't be found, return 404
        if order_found == False or card_found == False:
            raise AuthError({"code": "Not Found",
                            "description":
                            "Not found. "
                            "The specified credit card and/or order does not exist"}, 404)

        # an array for storing the orders associated with a credit card
        orders = []

        # stores the relationship id of a given credit card and order
        r_id = None

        # get relationship id and orders
        relationship_query = client.query(kind=constants.card_order)
        relationship_results = list(relationship_query.fetch())
        for e in relationship_results:
            if card_id == e["card_id"]:
                r_id = e.key.id
                if e["orders"] != []:
                    orders = e["orders"]

        # if the order has already been added to an existing card,
        # return 403
        if relationship_found == True:
            raise AuthError({"code": "Forbidden",
                            "description":
                            "Forbidden. "
                            "This order has already been added to an existing credit card"}, 403)

        # if credit card does not yet have an order, 
        # create an card_order relationship
        if orders == []:
            relationship = datastore.entity.Entity(key=client.key(constants.card_order))

        # otherwise, pull up the existing relationship
        else:
            relationship_key = client.key(constants.card_order, int(r_id))
            relationship = client.get(key=relationship_key)
        
        # append new order ro orders array of the card_order relationship
        orders.append(int(order_id))
        relationship.update({"card_id": int(card_id), "orders": orders})
        client.put(relationship)

        # add self attribute to relationship with direct URL
        relationship["relationship_id"] = relationship.key.id
        relationship["self"] = "https://" + request.host + "/credit_cards/" \
            + str(card_id) + "/orders/" + str(order_id)
        
        # return newly created relationship
        res = make_response(json.dumps(relationship))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res

    elif request.method == 'DELETE':

        # if card_order relationship does not exist, return 404
        if card != int(card_id):
            raise AuthError({"code": "Not Found",
                            "description":
                            "Relationship not found. "
                            "No order with this order_id is associated with a credit card with this card_id"}, 404)
        
        # stores relationship id
        r_id = None

        # an array for storing the orders associated with a credit card
        orders = []

        # do a query for all the relationships in the card_order 
        # collection
        # store the relationship id and orders of the credit card with the
        # given card_id
        relationship_query = client.query(kind=constants.card_order)
        relationship_results = list(relationship_query.fetch())
        for e in relationship_results:
            if int(card_id) == e["card_id"] and int(order_id) in e["orders"]:
                r_id = e.key.id
                orders = e["orders"]

        # pull up the card_order relationship and remove the order
        # from the existing orders array
        print(orders)
        relationship_key = client.key(constants.card_order, int(r_id))
        relationship = client.get(key=relationship_key)
        orders.remove(int(order_id))
        relationship.update({"orders": orders})
        client.put(relationship)
        return ('',204)
    
    # a method for returning the created card_order relationship after
    # 'PUT' has been called
    elif request.method == 'GET':
        if not request.accept_mimetypes['application/json']:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

        if order_found == False or card_found == False:
            raise AuthError({"code": "Not Found",
                            "description":
                            "Not found. "
                            "The specified credit card and/or order does not exist"}, 404)
        
        r_id = None

        base_url = '/credit_cards/' + str(card_id) + '/orders/' + str(order_id)

        # do a query for all the relationships in the card_order 
        # collection
        # store the relationship id and orders of the credit card with the
        # given card_id
        relationship_query = client.query(kind=constants.card_order)
        relationship_results = list(relationship_query.fetch())
        for e in relationship_results:
            if int(card_id)== e["card_id"]:
                r_id = e.key.id

        # pull up the relationship
        relationship_key = client.key(constants.card_order, int(r_id))
        relationship = client.get(key=relationship_key)

        # add 'self' attribute to the card_order relationship
        relationship["self"] = "https://" + request.host + base_url
        
        # return card_order relationship with card_id and 
        # associated orders 
        res = make_response(json.dumps(relationship))
        res.mimetype = 'application/json'
        res.status_code = 200
        return res

    else:
        return 'Method not recognized'
