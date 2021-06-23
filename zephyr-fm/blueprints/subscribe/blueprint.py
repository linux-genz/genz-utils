#!/usr/bin/python3
import json
import logging
import os
import uuid
from datetime import datetime
from pdb import set_trace
from pprint import pprint

import flask
import jsonschema
import requests as HTTP_REQUESTS

from blueprints.resource.blueprint import send_resource

import flask_fat

Journal = self = flask_fat.Journal(__file__)
log = logging.getLogger('zephyr')

""" ------------------------------- ROUTES ------------------------------- """

@Journal.BP.route('/%s/add_event' % (Journal.name), methods=['POST'])
def add_subscribe():
    """
        Subscribe to an Add event.
    """
    response = {}
    status = 'nothing'
    code = 200
    body = flask.request.get_json()
    if not body:
        body = flask.request.form

    callback_endpoint = body.get('callback', None)
    endpoint_alias = body.get('alias', None)
    bridges = body.get('bridges', [])
    if not endpoint_alias:
        endpoint_alias = callback_endpoint

    if callback_endpoint is None:
        response['error'] = 'No callback in body!\n%s' % body
        status = 'error'
        code = 400
    elif len(bridges) == 0:
        response['error'] = 'No bridges in body!\n%s' % body
        status = 'error'
        code = 400
    else:
        if endpoint_alias in Journal.mainapp.add_callback:
            status = 'Endpoint alias "%s" already in the list.' % endpoint_alias
            code = 403
        elif callback_endpoint in Journal.mainapp.add_callback.values():
            status = 'Endpoint "%s" already in the list.' % callback_endpoint
            code = 403
        else:
            status = 'Callback endpoint %s added' % callback_endpoint
            if endpoint_alias != callback_endpoint:
                status = '%s with the alias name "%s"' % (status, endpoint_alias)

            Journal.mainapp.add_callback[endpoint_alias] = callback_endpoint
            for br in bridges:
                Journal.mainapp.add_callback[br] = callback_endpoint
                try:
                    add = Journal.mainapp.conf.add[br]
                except KeyError:
                    log.debug('bridge {} has no Conf resources'.format(br))
                    continue
                for res in add:
                    resp = send_resource(res, [callback_endpoint])
                    # Revisit: do something with resp

        log.info('subscribe/add_event: %s' % status)
    response['status'] = status

    return flask.make_response(flask.jsonify(response), code)
