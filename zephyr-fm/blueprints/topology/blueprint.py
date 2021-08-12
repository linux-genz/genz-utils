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
