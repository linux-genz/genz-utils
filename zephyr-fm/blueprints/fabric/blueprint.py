#!/usr/bin/python3
import flask
import requests as HTTP_REQUESTS
import logging
import socket
import jsonschema
import json
import time
from pdb import set_trace

import flask_fat

Journal = self = flask_fat.Journal(__file__)
log = logging.getLogger('zephyr')

""" ----------------------- ROUTES --------------------- """

@Journal.BP.route(f'/{Journal.name}/topology', methods=['GET'])
def topology():
    """
        Accepts GET request and returns a json body describing the fabric
    topology (which includes the fabric_uuid).
    Returned body model:
    {
        'directed'   : false,
        'multigraph' : true,
        'graph'      : {
           'fab_uuid' : 'string',
           'mgr_uuids': [ 'string' ],
           'timestamp': int,  # from time.time_ns()
        },
        'nodes': [
          {
            'id'           : 'string',
            'instance_uuid': 'string',
            'cclass'       : 'number',
            'mgr_uuid'     : 'string',
            'gcids'        : [ 'string' ],
            'fru_uuid'     : 'string',
            'max_data'     : 'number',
            'max_iface'    : 'number',
          }
        ],
        'links': [
          {
            'source'       : 'string',
            'target'       : 'string',
            'key'          : 'number',
            '<source_instance_uuid>'  : 'string',
            '<target_instance_uuid>'  : 'string',
          }
        ]
    }

    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab

    return flask.make_response(flask.jsonify(fab.to_json()), 200)


@Journal.BP.route(f'/{Journal.name}/resources', methods=['GET'])
def resources():
    """
        Accepts GET request and returns a json body describing the fabric
    resources (and the fabric_uuid).
    Returned body model:
    {
        'fab_uuid' : 'string',
        'fab_resources': [ Resources ]
    }

    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab

    return flask.make_response(flask.jsonify(fab.resources.to_json()), 200)


@Journal.BP.route(f'/{Journal.name}/routes', methods=['GET'])
def routes():
    """
        Accepts GET request and returns a json body describing the fabric
    routes (and the fabric_uuid).
    Returned body model:
    {
        'fab_uuid' : 'string',
    # Revisit: fix this
        'routes': {
          {
            'id'           : 'string',
            'instance_uuid': 'string',
            'cclass'       : 'number',
            'mgr_uuid'     : 'string',
            'gcids'        : [ 'string' ],
            'fru_uuid'     : 'string',
            'max_data'     : 'number',
            'max_iface'    : 'number',
          }
        }
    }

    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab

    return flask.make_response(flask.jsonify(fab.routes.to_json()), 200)


@Journal.BP.route(f'/{Journal.name}/endpoints', methods=['GET'])
def endpoints():
    """
        Accepts GET request and returns a json body describing the registered
    fabric endpoints (and the fabric_uuid).
    Returned body model:
    {
        'fab_uuid' : 'string',
        'timestamp': 'int', # from time.time_ns()
    # Revisit: fix this
        'endpoints': {
          {
            'id'           : 'string',
            'instance_uuid': 'string',
            'cclass'       : 'number',
            'mgr_uuid'     : 'string',
            'gcids'        : [ 'string' ],
            'fru_uuid'     : 'string',
            'max_data'     : 'number',
            'max_iface'    : 'number',
          }
        }
    }

    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab
    desc = {
        'fab_uuid': str(fab.fab_uuid),
        'timestamp': time.time_ns(),
        'endpoints': mainapp.llamas_callbacks
    }

    return flask.make_response(flask.jsonify(desc), 200)


@Journal.BP.route(f'/{Journal.name}/uep', methods=['POST'])
def uep():
    """
        Accepts POST request with a json body describing the UEP and the
    component that received it.
    Body model:
    {
        'GENZ_A_UEP_MGR_UUID'    : 'string',
        'GENZ_A_UEP_BRIDGE_GCID' : 'uint32',
        'GENZ_A_UEP_FLAGS'       : 'uint64',
        'GENZ_A_UEP_TS_SEC'      : 'uint64',
        'GENZ_A_UEP_TS_NSEC'     : 'uint64',
        'GENZ_A_UEP_REC'         : {
           'A':                  : 'uint',
           'Vers':               : 'uint',
           'CV':                 : 'uint',
           'SV':                 : 'uint',
           'GC':                 : 'uint',
           'IV':                 : 'uint',
           'Event':              : 'uint',
           'IfaceID':            : 'uint',
           'SCID':               : 'uint',
           'SSID':               : 'uint',
           'RCCID':              : 'uint',
           'RCSID':              : 'uint',
           'ES':                 : 'uint',
           'EventID':            : 'uint',
           'EventName':          : 'string',
        }
    }
    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab
    body = flask.request.get_json()

    if body is None:
        msg = { 'error ' : ''}
        return flask.make_response(flask.jsonify(msg), 400)

    # Revisit: validate json against schema
    resp = fab.handle_uep(body)
    return flask.make_response(flask.jsonify(resp), 200)


@Journal.BP.route('/%s/routes/add' % (Journal.name), methods=['POST'])
def routes_add():
    """
        Accepts POST request with a json body describing the routes to add.
    Body model:
    {
        'fab_uuid'    : 'string',
        'routes'      : {
              'From(SID:CID)->To(SID:CID)': [
                  'SID:CID.Iface->SID:CID.Iface',
                  ...
              ],
              ...
        }
    }
    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab
    body = flask.request.get_json()

    if body is None:
        msg = { 'error ' : ''}
        return flask.make_response(flask.jsonify(msg), 400)

    # Revisit: validate json against schema
    resp = fab.add_routes(body)
    return flask.make_response(flask.jsonify(resp), 200)


@Journal.BP.route('/%s/routes/remove' % (Journal.name), methods=['POST'])
def routes_remove():
    """
        Accepts POST request with a json body describing the routes to remove.
    Body model: See routes_add()
    """
    global Journal
    mainapp = Journal.mainapp
    fab = mainapp.conf.fab
    body = flask.request.get_json()

    if body is None:
        msg = { 'error ' : 'body is None'}
        return flask.make_response(flask.jsonify(msg), 400)

    # Revisit: validate json against schema
    resp = fab.remove_routes(body)
    return flask.make_response(flask.jsonify(resp), 200)


@Journal.BP.route(f'/{Journal.name}/routes/sfm_routes', methods=['POST'])
def sfm_routes():
    """
        Accepts POST request with a json body detailing the route changes
    that the PFM wants to alert the SFM about.
    POST body model:
    {
        'fabric_uuid' : 'string',
        'mgr_uuid'    : 'string',
        'operation'   : 'string',  # 'add' or 'remove'
        'routes': {
          # See routes_add()
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

    # Revisit: validate json against schema
    routes = body.get('routes', None)
    fabric_uuid = body.get('fabric_uuid', None)
    # Revisit: check mgr_uuid
    op = body.get('operation', None)

    # Check that the fabric_uuid matches ours
    if fabric_uuid != str(fab.fab_uuid):
        msg = { 'error' : f'Incorrect fabric_uuid: {fabric_uuid}.' }
        return flask.make_response(flask.jsonify(msg), 404)

    # Check for a valid operation
    if not op in [ 'add', 'remove' ]:
        msg = { 'error' : f'Unknown operation: {op}.' }
        return flask.make_response(flask.jsonify(msg), 404)
    set_trace() # Revisit: temp debug
    if op == 'add':
        response = fab.add_routes(routes, send=False)
    else: # op == 'remove'
        response = fab.remove_routes(routes, send=False)

    response['success'].append(f'{op}')
    return flask.make_response(flask.jsonify(response), 200)

@Journal.BP.route(f'/{Journal.name}/sfm_endpoints', methods=['POST'])
def sfm_endpoints():
    """
        Accepts POST request with a json body detailing the endpoint changes
    that the PFM wants to alert the SFM about.
    POST body model:
    {
        'fabric_uuid' : 'string',
        'mgr_uuid'    : 'string',
        'operation'   : 'string',  # 'add' or 'remove'
        'endpoints': {
          # Revisit: finish this
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

    # Revisit: validate json against schema
    routes = body.get('routes', None)
    fabric_uuid = body.get('fabric_uuid', None)
    # Revisit: check mgr_uuid
    op = body.get('operation', None)

    # Check that the fabric_uuid matches ours
    if fabric_uuid != str(fab.fab_uuid):
        msg = { 'error' : f'Incorrect fabric_uuid: {fabric_uuid}.' }
        return flask.make_response(flask.jsonify(msg), 404)

    # Check for a valid operation
    if not op in [ 'add', 'remove' ]:
        msg = { 'error' : f'Unknown operation: {op}.' }
        return flask.make_response(flask.jsonify(msg), 404)
    set_trace() # Revisit: temp debug
    if op == 'add':
        response = fab.add_routes(routes, send=False)
    else: # op == 'remove'
        response = fab.remove_routes(routes, send=False)

    response['success'].append(f'{op}')
    return flask.make_response(flask.jsonify(response), 200)
