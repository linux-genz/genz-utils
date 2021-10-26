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
