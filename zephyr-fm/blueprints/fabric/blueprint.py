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

@Journal.BP.route('/%s/topology' % (Journal.name), methods=['GET'])
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

    return flask.make_response(fab.to_json(), 200)


@Journal.BP.route('/%s/routes' % (Journal.name), methods=['GET'])
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

    return flask.make_response(fab.routes.to_json(), 200)


@Journal.BP.route('/%s/uep' % (Journal.name), methods=['POST'])
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
        'GENZ_A_UEP_PKT'         : {
           'name':               : 'string',
           'OCL':                : 'uint',
           'OpCode':             : 'uint',
           'LEN':                : 'uint',
           'VC':                 : 'uint',
           'PCRC':               : 'uint',
           'DCID':               : 'uint',
           'SCID':               : 'uint',
           'AKey':               : 'uint',
           'Deadline':           : 'uint',
           'ECN':                : 'uint',
           'GC':                 : 'uint',
           'NH':                 : 'uint',
           'PM':                 : 'uint',
           'Event':              : 'uint',
           'EventName':          : 'string',
           'CV':                 : 'uint',
           'SV':                 : 'uint',
           'IV':                 : 'uint',
           'RCCID':              : 'uint',
           'RCSID':              : 'uint',
           'IfaceID':            : 'uint',
           'EventID':            : 'uint',
           'ES':                 : 'uint',
           'ECRC':               : 'uint',
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
