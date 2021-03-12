#!/usr/bin/python3
import flask
import requests as HTTP_REQUESTS
import logging
import socket
import jsonschema
import json
from pdb import set_trace

import flask_fat

Journal = self = flask_fat.Journal(__file__)

""" ----------------------- ROUTES --------------------- """

@Journal.BP.route('/%s/create' % (Journal.name), methods=['POST'])
def create_resource():
    """
        Accepts POST request with a json body describing the resource and the
    list of endpoints (optional. Aliases or urls) to notify about the resource.
    Body model:
    {
        'endpoint' : 'array',
        'resource' : 'object'
    }

    Refer to "get_resource_schema()" for the "resource" model
    """
    global Journal
    mainapp = Journal.mainapp
    body = flask.request.get_json()

    if body is None:
        msg = { 'error ' : ''}
        return flask.make_response(flask.jsonify(msg), 400)

    resource = body.get('resource', None)
    endpoints = body.get('endpoint', [])

    # If nobody subscribed to this "create" event, then nobody will be notified.
    # TODO: save the target endpoints that have not subscribed yet and call them
    # with the shared resource once they subscribe.
    if not mainapp.add_callback:
        msg = { 'error' : 'Nothing happened. There are No subscribers to this event, yet.' }
        return flask.make_response(flask.jsonify(msg), 304)

    # Gets the list of endpoint targets to share resource with.
    endpoints = extract_target_endpoints(endpoints, mainapp.add_callback)

    if not mainapp.add_callback:
        msg = { 'error' : 'Targeted endpoints not found in the subscription list!' }
        return flask.make_response(flask.jsonify(msg), 404)

    resp = send_resource(resource, endpoints)

    return resp


def send_resource(resource: dict, endpoints: list):
    """
        Makes an http call to each of the the "endpoints" urls.

        @return: a flask response object (with jsonified msg, status code, etc).
    """
    response = {}
    response['callback'] = {'failed': [], 'success': []}

    logging.debug('send_resource: endpoints={}'.format(endpoints))
    if resource is None:
        response['error'] = 'Missing "resource" object! (the one describing the resource..)'
        return flask.make_response(flask.jsonify(response), 400)

    try:
        jsonschema.validate(resource, schema=get_resource_schema())
    except Exception as err:
        response['error'] = str(err)
        return flask.make_response(flask.jsonify(response), 400)

    for endpoint in endpoints:
        try:
            logging.debug('Sending {} to {}'.format(resource, endpoint))
            msg = HTTP_REQUESTS.post(endpoint, json=resource)
            if msg.status_code < 300:
                response['callback']['success'].append(endpoint)
            else:
                response['callback']['failed'].append(endpoint)
                response['error'] = msg.reason
        except Exception as err:
            if 'error' not in response:
                response['error'] = {}
            response['error'] = str(err)

    return flask.make_response(flask.jsonify(response), 200)


def extract_target_endpoints(targets, known):
    """
        There are subscribed endpoints (@known) and there are targets that a user
    wants to share the resource with. This function gets a "union" of the two and
    will return only those targets that are in the known state.

        @param targets: a list of urls or aliases to get urls from the the subscription list.
        @param known: a subscription dictionary of { 'alias' : 'url' } pairs.
    """
    if not targets:
        return known.values()

    result = []
    for target in targets:
        url = None

        #Check for the Alias match
        if target in known:
            url = known[target]

        #Check for URL match
        if url is None and target in known.values():
            url = target

        if url is not None and not url in result: # found and not duplicate
            result.append(url)

    return result


def get_resource_schema():
    """
    The Resource schema that is sent in the body by
    the resource creator/FM and which is understood by LLaMaS service.
    """
    return {
        'gcid': 'number',
        'cclass': 'number',
        'mgr_uuid': 'string',
        'fru_uuid': 'string',

        'resources': [
            {
                'class_uuid': 'string',
                'instance_uuid': 'string',
                'class': 'number',
                'memory': [
                    {
                        'start': 'number',
                        'length': 'number',
                        'type': 'number',
                        'ro_rkey': 'number',
                        'rw_rkey': 'number',
                    }
                ]
            }
        ]
    }
