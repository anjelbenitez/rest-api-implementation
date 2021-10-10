from flask import Blueprint, request, jsonify, make_response, render_template
from google.cloud import datastore
import json
import constants

client = datastore.Client()

bp = Blueprint('order', __name__, url_prefix='/orders')

class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code

@bp.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response

@bp.route('', methods=['POST','GET','PUT','DELETE'])
def orders_get_post():
    """
    An API endpoint for adding a new order or getting a list of all the 
    orders in the collection
    """

    # creates a new order
    if request.method == 'POST':

        if request.content_type != 'application/json':
            raise AuthError({"code": "Unsupported Media Type",
                            "description":
                            "Unsupported media type. "
                            "Please use application/json with your request"}, 415)

        # get JSON data from the request body
        content = request.get_json()

        # do not create if an attribute is missing
        if "date_created" not in content.keys() or "order_total" not in content.keys() \
            or "status" not in content.keys():
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Missing attribute. "
                                "The request object is missing at least one of the required attributes"}, 400)

        # do not accept invalid attribute/s
        for key in content.keys():
            if key == "date_created" or key == "order_total" or key == "status":
                continue
            else:
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Invalid attribute. "
                                "The request contains an invalid attribute"}, 400)
        
        # do a query for all the orders in the orders collection
        orders_query = client.query(kind=constants.orders)
        results = list(orders_query.fetch())
        
        # if valid, create a new order with the given attributes
        if request.accept_mimetypes['application/json']:
            new_order = datastore.entity.Entity(key=client.key(constants.orders))
            new_order.update({"date_created": content["date_created"], "order_total": content["order_total"],
            "status": content["status"]})
            client.put(new_order)

            # add id and self attributes
            new_order["id"] = new_order.key.id
            new_order["self"] = "https://" + request.host + "/orders/" \
                + str(new_order.key.id)
            new_order["credit_card_id"] = None

            res = make_response(json.dumps(new_order))
            res.mimetype = 'application/json'
            res.status_code = 201

            # return newly created order
            return res

        else:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

    elif request.method == 'GET':

        # do a query for all the orders in the collection
        # also, implement pagination
        if request.accept_mimetypes['application/json']:
            relationship_query = client.query(kind=constants.card_order)
            relationship_results = list(relationship_query.fetch())

            query = client.query(kind=constants.orders)
            query_r = list(query.fetch())
            count = 0

            # set limit of orders per page to 5
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
            # to each order
            for e in results:
                e["id"] = e.key.id
                e["self"] = "https://" + request.host + "/orders/" + str(e.key.id)
                e["credit_card_id"] = None

                for f in relationship_results:
                    if e["id"] in f["orders"]:
                        e["credit_card_id"] = f["card_id"]

            for g in query_r:
                count += 1
            
            output = {"orders": results}


            # if there are more orders to be viewed, output next_url
            if next_url:
                output["next"] = next_url
            output["items_in_collection"] = count

            # return the list of orders and their attributes
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
                        "Cannot delete or make changes to the /orders URL"}, 405)

    else:
        return 'Method not recognized'

@bp.route('/<order_id>', methods=['DELETE','GET','PATCH','PUT'])
def orders_put_delete(order_id):
    """
    An API endpoint for deleting an order or for getting a specific order
    """

    order_found = False

    relationship_query = client.query(kind=constants.card_order)
    relationship_results = list(relationship_query.fetch())

    # do a query for all the orders in the orders collection
    orders_query = client.query(kind=constants.orders)
    results = list(orders_query.fetch())

    # add an 'id' attribute to each order
    # check if the order exists in the collection
    for e in results:
        e["id"] = e.key.id
        if order_id == json.dumps(e["id"]):
            order_found = True
    
    # if order not found, return 404 error
    if order_found == False:
        raise AuthError({"code": "Not Found",
                        "description":
                        "Order not found. "
                        "No order with this order_id exists"}, 404)

    order_key = client.key(constants.orders, int(order_id))
    order = client.get(key=order_key)
    
    # deletes an existing order
    if request.method == 'DELETE':
        r_id = None
        order["id"] = order.key.id

        # delete order from orders collection
        for e in relationship_results:
            if order["id"] in e["orders"]:
                r_id = e.key.id
                relationship_key = client.key(constants.card_order, int(r_id))
                client.delete(relationship_key)
        client.delete(order_key)
        return ('',204)

    
    # edits an existing order's attribute/s
    elif request.method == 'PATCH':

        if request.content_type != 'application/json':
            raise AuthError({"code": "Unsupported Media Type",
                            "description":
                            "Unsupported media type. "
                            "Please use application/json with your request"}, 415)
        
        # get JSON data from the request body
        content = request.get_json()

        # nothing to modify if all 3 attributes are missing
        if "date_created" not in content.keys() and "order_total" not in content.keys() \
            and "status" not in content.keys():
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Bad request. "
                                "No valid attributes to modify"}, 400)

        # do not accept invalid attribute/s
        for key in content.keys():
            if key == "date_created" or key == "order_total" or key == "status":
                continue
            else:
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Invalid attribute. "
                                "The request contains an invalid attribute"}, 400)
        
        # if valid, modify an order with the passed attribute/s
        if request.accept_mimetypes['application/json']:
            if "date_created" in content.keys():
                order.update({"date_created": content["date_created"]})
            if "order_total" in content.keys():
                order.update({"order_total": content["order_total"]})
            if "status" in content.keys():
                order.update({"status": content["status"]})

            client.put(order)

            # add 'id' and 'self' attributes to the order
            order["id"] = order.key.id
            order["self"] = "https://" + request.host + "/orders/" \
                + str(order.key.id)
            order["credit_card_id"] = None

            for e in relationship_results:
                if order["id"] in e["orders"]:
                    order["credit_card_id"] = e["card_id"]

            res = make_response(json.dumps(order))
            res.mimetype = 'application/json'
            res.status_code = 200

            # return modified order
            return res

        else:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

    elif request.method == 'PUT':

        if request.content_type != 'application/json':
            raise AuthError({"code": "Unsupported Media Type",
                            "description":
                            "Unsupported media type. "
                            "Please use application/json with your request"}, 415)
        
        # get JSON data from the request body
        content = request.get_json()

        # do not modify if one or more required attribute/s is missing
        if "date_created" not in content.keys() or "order_total" not in content.keys() \
            or "status" not in content.keys():
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Missing attribute. "
                                "The request object is missing at least one of the required attributes"}, 400)

        # do not accept invalid attribute/s
        for key in content.keys():
            if key == "date_created" or key == "order_total" or key == "status":
                continue
            else:
                raise AuthError({"code": "Bad Request",
                                "description":
                                "Invalid attribute. "
                                "The request contains an invalid attribute"}, 400)
        
        # if valid, modify an order with the passed attribute/s
        if request.accept_mimetypes['application/json']:
            order.update({"date_created": content["date_created"], "order_total": content["order_total"],
            "status": content["status"]})
            client.put(order)

            # add 'id' and 'self' attributes to the order
            order["id"] = order.key.id
            order["self"] = "https://" + request.host + "/orders/" \
                + str(order.key.id)
            order["credit_card_id"] = None

            for e in relationship_results:
                if order["id"] in e["orders"]:
                    order["credit_card_id"] = e["card_id"]

            res = make_response(json.dumps(order))
            res.mimetype = 'application/json'
            res.status_code = 200

            # return modified order
            return res

        else:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)

    # gets a specific order with the given id, either as JSON or HTML
    elif request.method == 'GET':
        if request.accept_mimetypes['application/json']:
            base_url = '/orders/' + order_id

            # add 'id' and 'self' attributes to the order
            order["id"] = order.key.id
            order["self"] = "https://" + request.host + base_url
            order["credit_card_id"] = None

            for e in relationship_results:
                if order["id"] in e["orders"]:
                    order["credit_card_id"] = e["card_id"]

            res = make_response(json.dumps(order))             
            res.mimetype = 'application/json'
            res.status_code = 200

            # return order and its attributes as JSON
            return res

        else:
            raise AuthError({"code": "Not Acceptable",
                "description":
                "Not acceptable. "
                "Only application/json content type supported"}, 406)
    else:
        return 'Method not recognized'
