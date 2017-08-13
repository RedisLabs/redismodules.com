import logging
import json
import os
import sys
from datetime import datetime

import github
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for, jsonify)
from flask_cache import Cache
from flask_bootstrap import Bootstrap

from hub import Hub

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

cache = Cache(config={
    'CACHE_TYPE': 'redis',
    'CACHE_KEY_PREFIX': 'webcache',
    'CACHE_REDIS_URL': os.environ['CACHE_REDIS_URL']
})

hub = Hub(os.environ['DB_REDIS_URL'], os.environ['QUEUE_REDIS_URL'], os.environ['GITHUB_TOKEN'])

app = Flask(__name__)
cache.init_app(app)
Bootstrap(app)

@app.route('/')
@cache.cached(timeout=60)
def handle_homepage():
    return render_template('index.html')

@app.route('/modules')
@app.route('/modules/<int:page>')
def handle_modules(page=0):
    # TODO: paging
    sort = request.cookies.get('sort')
    return jsonify(hub.getModules(sort=sort))

@app.route('/sugget')
@app.route('/sugget/')
def handle_default_suggestions():
    # TODO: default suggestions can be based on searches popularity in a zset
    return jsonify([])

@app.route('/sugget/<string:query>')
def handle_suggetions(query=None):
    if query:
        return jsonify(hub.getSearchSuggestions(query))

@app.route('/search')
def handle_search():
    query = request.args.get('q', '')
    results = hub.getSearchResults(query)
    return jsonify(results)

if __name__ == '__main__':
    # socketio.run()
    app.run()