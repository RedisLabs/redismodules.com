import json
import os
import re
import sys
import markdown
import StringIO
import validators

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for, Markup)
from flask_bootstrap import Bootstrap
from flask_cache import Cache
from rmhub import Hub, GithubRepository, GithubAuthor, logger

hub = None

cache = Cache(config={
    'CACHE_TYPE': 'redis',
    'CACHE_KEY_PREFIX': 'webcache:',
    'CACHE_REDIS_URL': os.environ['CACHE_REDIS_URL'],
})

app = Flask(__name__)
cache.init_app(app)
Bootstrap(app)

@app.before_first_request
def startTheWebz():
    logger.info('Starting the webz')
    global hub
    hub = Hub()
    # DANGER: Flask-Cache's Redis.clear() uses `KEYS`
    # TODO: a) an urgent PR to change it to `SCAN` when supported, b) another FR to use a set to keep track of keys c) use `UNLINK` instead of `DEL` if possible
    cache.clear()

@app.route('/')
@cache.cached(timeout=0)
def handle_homepage():
    return render_template('index.html')

@app.route('/moar/<string:topic>')
@cache.cached(timeout=0)
def handle_moar(topic):
    topic = str(topic)
    filename = topic.lower().replace(' ', '_')
    label = 'modal{}Label'.format(topic.replace(' ', ''))
    dir_path = os.path.dirname(os.path.realpath(__file__))
    full_path = '{}/static/markdown/{}.md'.format(dir_path, filename)
    if os.path.isfile(full_path):
        md = StringIO.StringIO()
        markdown.markdownFromFile(input=full_path, output=md)
        moar = Markup(md.getvalue())
        md.close()
    else:
        moar = "That's odd, there doesn't seem to be anything moar about {}".format(topic)
    return render_template('moar.html', label=label, topic=topic, moar=moar)

@app.route('/modules')
@app.route('/modules/<int:page>')
def handle_modules(page=0):
    # TODO: paging
    sort = request.cookies.get('sort')
    return jsonify(hub.getModules(sort=sort))


@app.route('/search')
def handle_search():
    # TODO: santize/safeguard query
    query = request.args.get('q', '')
    sort = request.cookies.get('sort')
    results = hub.getModules(query=query, sort=sort)
    return jsonify(results)

@app.route('/submit', methods=['GET', 'POST'])
def handle_submit():
    if request.method == 'POST':
        # Sanitize form input
        status = {
            'status': 'failed'
        }
        r = request.form['repoid']
        if r is None:
            status['message'] = 'Repository ID is mandatory'
            return status
        else:
            if len(r) > 255:
                status['message'] = 'Repository ID is over 255 characters'
                return status
            m = re.search('^([a-z0-9._-]+)/([a-z0-9._-]+)$', r)
            if not m:
                status['message'] = 'Repository ID is not in the pattern of "name/repository"'
                return status

        a = request.form['authorid']
        if len(a) > 255:
            status['message'] = 'Author ID is over 255 characters'
            return status

        i = request.form['icon']
        if i and not validators.url(i):
            status['message'] = 'Icon is not a valid URL'
            return status

        # TODO: add more types of repos/authors/icon upload
        status = hub.submitModule(r, a, i)
        return jsonify(status)
    elif request.method == 'GET':
        jobid = request.args['jobid']
        status = hub.getSubmissionStatus(jobid)
        return jsonify(status)


@app.route('/sugget')
@app.route('/sugget/')
@app.route('/sugget/<string:query>')
def handle_suggetions(query=None):
    # TODO: Sanitize input
    if query:
        return jsonify(hub.getSearchSuggestions(query))
    else:
        return jsonify([])