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

@Journal.BP.route(f'/{Journal.name}/llamas', methods=['POST'])
def subscribe_llamas():
    """
        Subscribe llamas endpoints.
    @param req.body: {
        'callbacks'    : {'name': <endpoint>},
        'alias'        : <value>, # unused
        'bridges'      : <List[cuuid:serial]>,
    }
    """
    response = {}
    status = 'nothing'
    code = 200
    body = flask.request.get_json()
    if not body:
        body = flask.request.form

    callback_endpoints = body.get('callbacks', None)
    endpoint_alias = body.get('alias', None)
    bridges = body.get('bridges', [])

    if callback_endpoints is None:
        response['error'] = f'No callbacks in body!\n{body}'
        status = 'error'
        code = 400
    elif len(bridges) == 0:
        response['error'] = f'No bridges in body!\n{body}'
        status = 'error'
        code = 400
    else:
        if callback_endpoints in Journal.mainapp.callbacks.values():
            status = f'Endpoints "{callback_endpoints}" already in the list'
            code = 403
        else:
            status = f'Callback endpoints "{callback_endpoints}" added'

            # save callback endpoints and move local bridges
            fab = Journal.mainapp.conf.fab
            for br in bridges:
                Journal.mainapp.callbacks[br] = callback_endpoints
                resp = send_move_local_bridge(fab, br, callback_endpoints['local_bridge'])
                log.debug(f'send_move_local_bridge resp={resp}')

            # send resources
            for br in bridges:
                try:
                    add = Journal.mainapp.conf.get_resources(br)
                except KeyError:
                    log.debug(f'bridge {br} has no Conf resources')
                    continue
                for res in add:
                    resp = send_resource(res, [callback_endpoints['add']])
                    # Revisit: do something with resp
                # end for res
            # end for br
        # end if

    log.info(f'subscribe/llamas: {status}')
    response['status'] = status

    return flask.make_response(flask.jsonify(response), code)


def send_move_local_bridge(fab, br_cuuid_serial, endpoint):
    try:
        br = fab.cuuid_serial[br_cuuid_serial]
    except KeyError:
        log.warning(f'bridge {br_cuuid_serial} not found')
        return None
    # Revisit: other checks, like valid gcid, status is C-Up?
    data = {
        'gcid'        : br.gcid.val,
        'cuuid_serial': br_cuuid_serial,
        'mgr_uuid'    : str(fab.mgr_uuid),
    }
    try:
        log.debug(f'Sending {data} to {endpoint}')
        msg = HTTP_REQUESTS.post(endpoint, json=data)
        resp = msg.json()
        fab.set_comp_name(br, resp['name'])
        if not msg.ok:
            log.warning(f'send_move_local_bridge HTTP status {msg.status_code}')
        return resp
    except Exception as err:
        return None
