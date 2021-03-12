#!/usr/bin/python3
import flask
import requests as HTTP_REQUESTS
import socket
from pdb import set_trace

import flask_fat

Journal = self = flask_fat.Journal(__file__)

""" ----------------------- ROUTES --------------------- """

@Journal.BP.route('/help', methods=['GET'])
def register_external_api():
    global Journal
    app = Journal.mainapp.app
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        route = { rule.rule : list(rule.methods) }
        routes.append(route)
    return flask.make_response(flask.jsonify(routes), 200)
