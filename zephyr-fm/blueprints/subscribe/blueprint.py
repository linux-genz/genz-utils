#!/usr/bin/python3
import json
import logging
import os
import time
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
    mgr_type = body.get('mgr_type', 'llamas')

    if callback_endpoints is None:
        response['error'] = f'No callbacks in body!\n{body}'
        status = 'error'
        code = 400
    elif len(bridges) == 0:
        response['error'] = f'No bridges in body!\n{body}'
        status = 'error'
        code = 400
    else:
        if Journal.mainapp.callbacks.match(mgr_type, callback_endpoints):
            status = f'Endpoints "{callback_endpoints}" already in the list'
            code = 403
        else:
            status = f'Callback endpoints "{callback_endpoints}" added'

            # save callback endpoints and move local bridges
            fab = Journal.mainapp.conf.fab
            for br in bridges:
                callback_dict = { 'mgr_type'  : mgr_type,
                                  'callbacks' : callback_endpoints }
                Journal.mainapp.callbacks.set_endpoints(br, callback_dict)
                resp = send_move_local_bridge(fab, br, callback_endpoints['local_bridge'])
                log.debug(f'send_move_local_bridge resp={resp}')
                Journal.mainapp.callbacks.send_endpoints_update(
                    fab, br, op='add', mgr_type=mgr_type)
            # end for br

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

@Journal.BP.route(f'/{Journal.name}/sfm', methods=['POST'])
def subscribe_sfm():
    """
        Subscribe Secondary Fabric Manager (SFM) endpoints.
    @param req.body: {
        'callbacks'    : {'name': <endpoint_url>},
        'alias'        : <value>, # unused
        'bridges'      : <List[cuuid:serial]>, # required if SFM
        'mgr_type'     : 'string', # 'sfm' or any other string != 'llamas'
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
    mgr_type = body.get('mgr_type', None)

    if callback_endpoints is None:
        response['error'] = f'No callbacks in body!\n{body}'
        status = 'error'
        code = 400
    elif mgr_type is None:
        response['error'] = f'Missing required mgr_type!'
        status = 'error'
        code = 400
    elif len(bridges) != 1 and mgr_type == 'sfm':
        response['error'] = f'One SFM bridge required in body!\n{body}'
        status = 'error'
        code = 400
    elif len(bridges) < 1:
        response['error'] = f'One or more SFM bridges (or instance_uuid) required in body!\n{body}'
        status = 'error'
        code = 400
    else:
        status = f'SFM callback endpoints "{callback_endpoints}" added'

        # save callback endpoints and enable SFM (if mgr_type is 'sfm')
        fab = Journal.mainapp.conf.fab
        for br in bridges:
            callback_dict = { 'mgr_type'  : mgr_type,
                              'callbacks' : callback_endpoints }
            Journal.mainapp.callbacks.set_endpoints(br, callback_dict)
            if mgr_type == 'sfm':
                resp = enable_sfm(fab, br)
                log.debug(f'enable_sfm resp={resp}')
            Journal.mainapp.callbacks.send_endpoints_update(fab, br, op='add',
                                                            mgr_type=mgr_type)
        # end for br

    log.info(f'subscribe/sfm: {status}')
    response['status'] = status

    return flask.make_response(flask.jsonify(response), code)

def enable_sfm(fab, br_cuuid_serial):
    try:
        br = fab.cuuid_serial[br_cuuid_serial]
    except KeyError:
        log.warning(f'bridge {br_cuuid_serial} not found')
        return None
    resp = fab.enable_sfm(br)
    return resp

@Journal.BP.route(f'/{Journal.name}/unsubscribe', methods=['POST'])
def unsubscribe():
    """
        Unsubscribe manager endpoints.
    @param req.body: {
        'callbacks'    : {'name': <endpoint_url>},
        'alias'        : <value>, # unused
        'bridges'      : <List[cuuid:serial]>, # required if SFM
        'mgr_type'     : 'string', # 'sfm', 'llamas' or any other string
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
    mgr_type = body.get('mgr_type', None)

    if callback_endpoints is None:
        response['error'] = f'No callbacks in body!\n{body}'
        status = 'error'
        code = 400
    elif mgr_type is None:
        response['error'] = f'Missing required mgr_type!'
        status = 'error'
        code = 400
    elif len(bridges) != 1 and mgr_type == 'sfm':
        response['error'] = f'One SFM bridge required in body!\n{body}'
        status = 'error'
        code = 400
    elif len(bridges) < 1:
        response['error'] = f'One or more SFM bridges (or instance_uuid) required in body!\n{body}'
        status = 'error'
        code = 400
    else:
        status = f'Manager callback endpoints "{callback_endpoints}" removed'

        # remove callback endpoints and disable SFM (if mgr_type is 'sfm')
        fab = Journal.mainapp.conf.fab
        for br in bridges:
            Journal.mainapp.callbacks.send_endpoints_update(
                fab, br, op='remove', mgr_type=mgr_type)
            if mgr_type == 'sfm':
                resp = disable_sfm(fab, br)
                log.debug(f'disable_sfm resp={resp}')
            callback_dict = { 'mgr_type'  : mgr_type,
                              'callbacks' : callback_endpoints }
            Journal.mainapp.callbacks.remove_endpoints(br, callback_dict)
        # end for br

    log.info(f'subscribe/unsubscribe: {status}')
    response['status'] = status

    return flask.make_response(flask.jsonify(response), code)

def disable_sfm(fab, br_cuuid_serial):
    try:
        br = fab.cuuid_serial[br_cuuid_serial]
    except KeyError:
        log.warning(f'bridge {br_cuuid_serial} not found')
        return None
    resp = fab.disable_sfm(br)
    return resp
