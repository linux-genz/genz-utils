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
log = logging.getLogger('zephyr')

""" ----------------------- ROUTES --------------------- """

@Journal.BP.route('/%s/create' % (Journal.name), methods=['POST'])
def create_resource():
    """
        Accepts POST request with a json body describing the resource and the
    fabric_uuid the resource belongs to.
    Body model:
    {
        'fabric_uuid' : 'string',
        'resource'    : 'object'
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
    fabric_uuid = body.get('fabric_uuid', None)

    # Check that the fabric_uuid matches ours
    if fabric_uuid != mainapp.conf.data['fabric_uuid']:
        msg = { 'error' : 'Incorrect fabric_uuid: {}.'.format(fabric_uuid) }
        return flask.make_response(flask.jsonify(msg), 404)

    # Validate resource against schema
    try:
        jsonschema.validate(resource, schema=get_resource_schema())
    except Exception as err:
        msg = { 'error' : str(err) }
        return flask.make_response(flask.jsonify(msg), 400)

    try:
        add_res = mainapp.conf.add_resource(resource)
    except Exception as err:
        msg = { 'error' : str(err) }
        return flask.make_response(flask.jsonify(msg), 400)

    endpoints = mainapp.get_endpoints(resource['consumers'], 'llamas', 'add')
    # If nobody subscribed to this "create" event, then nobody will be notified.
    if len(endpoints) == 0:
        msg = { 'warning' : 'Nothing happened. There are no subscribers to this event, yet.' }
        return flask.make_response(flask.jsonify(msg), 304)

    resp = send_resource(add_res, endpoints)
    return resp


@Journal.BP.route('/%s/remove' % (Journal.name), methods=['POST'])
def remove_resource():
    """
        Accepts POST request with a json body describing the resource and the
    fabric_uuid the resource belongs to.
    Body model:
    {
        'fabric_uuid' : 'string',
        'resource'    : 'object'
    }

    Refer to "get_resource_schema()" for the "resource" model
    """
    global Journal
    mainapp = Journal.mainapp
    body = flask.request.get_json()

    if body is None:
        msg = { 'error ' : 'body is None'}
        return flask.make_response(flask.jsonify(msg), 400)

    resource = body.get('resource', None)
    fabric_uuid = body.get('fabric_uuid', None)

    # Check that the fabric_uuid matches ours
    if fabric_uuid != mainapp.conf.data['fabric_uuid']:
        msg = { 'error' : 'Incorrect fabric_uuid: {}.'.format(fabric_uuid) }
        return flask.make_response(flask.jsonify(msg), 404)

    # Validate resource against schema
    try:
        jsonschema.validate(resource, schema=get_resource_schema())
    except Exception as err:
        msg = { 'error' : 'jsonschema: {}'.format(str(err)) }
        return flask.make_response(flask.jsonify(msg), 400)

    try:
        rm_res = mainapp.conf.remove_resource(resource)
    except Exception as err:
        msg = { 'error' : 'remove_resource: {}'.format(str(err)) }
        return flask.make_response(flask.jsonify(msg), 400)

    endpoints = mainapp.get_endpoints(resource['consumers'], 'llamas', 'remove')
    # If nobody subscribed to this "remove" event, then nobody will be notified.
    if len(endpoints) == 0:
        msg = { 'warning' : 'Nothing happened. There are no subscribers to this event.' }
        return flask.make_response(flask.jsonify(msg), 304)

    resp = send_resource(rm_res, endpoints)
    return resp


def send_resource(resource: dict, endpoints: list):
    """
        Makes an http call to each of the the "endpoints" urls.

        @return: a flask response object (with jsonified msg, status code, etc).
    """
    response = {}
    response['callback'] = {'failed': [], 'success': []}

    log.debug('send_resource: endpoints={}'.format(endpoints))
    if resource is None:
        response['error'] = 'Missing "resource" object! (the one describing the resource..)'
        return flask.make_response(flask.jsonify(response), 400)
    else:
        response['instance_uuids'] = [ res['instance_uuid'] for res in resource['resources'] ]

    try:
        jsonschema.validate(resource, schema=get_resource_schema())
    except Exception as err:
        response['error'] = str(err)
        return flask.make_response(flask.jsonify(response), 400)

    for endpoint in endpoints:
        try:
            log.debug('Sending {} to {}'.format(resource, endpoint))
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


@Journal.BP.route(f'/{Journal.name}/sfm', methods=['POST'])
def sfm():
    """
        Accepts POST request with a json body detailing resource changes
    that the PFM wants to alert the SFM about.
    POST body model:
    {
        'fabric_uuid'   : 'string',
        'mgr_uuid'      : 'string',
        'cur_timestamp' : int,
        'operation'     : 'string',
        'resource': {
          # See get_resource_schema()
        }
    }

    """
    global Journal
    mainapp = Journal.mainapp
    body = flask.request.get_json()
    fab = mainapp.conf.fab

    if body is None:
        msg = { 'error ' : 'body is None'}
        return flask.make_response(flask.jsonify(msg), 400)

    resource = body.get('resource', None)
    # Revisit: validate resource against schema
    fabric_uuid = body.get('fabric_uuid', None)
    # Revisit: check mgr_uuid
    op = body.get('operation', None)

    # Check that the fabric_uuid matches ours
    if fabric_uuid != str(fab.fab_uuid):
        msg = { 'error' : f'Incorrect fabric_uuid: {fabric_uuid}.' }
        return flask.make_response(flask.jsonify(msg), 404)

    # Check for a valid operation
    if not op in [ 'add', 'remove', 'add_cons', 'rm_cons' ]:
        msg = { 'error' : f'Unknown operation: {op}.' }
        return flask.make_response(flask.jsonify(msg), 404)
    if op == 'add' or op == 'add_cons':
        fab.conf.add_resource(resource, op=op, send=False)
    else: # op == 'remove' or op == 'rm_cons'
        fab.conf.remove_resource(resource, op=op, send=False)

    response = { 'ok': f'{op}'}
    return flask.make_response(flask.jsonify(response), 200)


def get_resource_schema():
    """
    The Resource schema that is sent in the body by the resource creator.
    """
    return {
        'producer': 'string',
        'consumers': [ 'string' ],
        'resources': [
            {
                'class_uuid': 'string',
                'instance_uuid': 'string',
                'flags': 'number',
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
