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
    repo_url = hub.get_repo_url()
    return render_template('index.html', repo_url=repo_url)

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
    return jsonify(hub.viewModules(sort=sort))


@app.route('/search')
def handle_search():
    # TODO: santize/safeguard query
    query = request.args.get('q', '')
    sort = request.cookies.get('sort')
    results = hub.viewModules(query=query, sort=sort)
    return jsonify(results)

@app.route('/submit', methods=['GET', 'POST'])
def handle_submit():
    if request.method == 'POST':
        # Sanitize form input
        status = {
            'status': 'failed'
        }
        kwargs = {}

        # repo_id is mandatory, missing it will trigger a Bad Request
        repo_id = request.form['repoid']
        if len(repo_id) > 255:
            status['message'] = 'Repository ID is over 255 characters'
            return status
        match = re.search('^([a-z0-9._-]+)/([a-z0-9._-]+)$', repo_id)
        if not match:
            status['message'] = 'Repository ID is not in the pattern of "name/repository"'
            return status

        arg = request.form.get('authorid')
        arg = None if arg == '' else arg
        if arg:
            if len(arg) > 255:
                status['message'] = 'Author ID is over 255 characters'
                return status
        authors = []
        if arg and arg != '':
            authors.append(arg)
        kwargs['authors'] = authors

        arg = request.form['icon']
        arg = None if arg == '' else arg
        if arg:
            if not validators.url(arg):
                status['message'] = 'Icon is not a valid URL'
                return status
            kwargs['icon_url'] = arg

        arg = request.form['docs']
        arg = None if arg == '' else arg
        if arg:
            if not validators.url(arg):
                status['message'] = 'Documentation is not a valid URL'
                return status
            kwargs['docs_url'] = arg

        kwargs['certification'] = (request.form.get('certification') == 'on')

        # TODO: add more types of repos/authors/icon upload
        status = hub.submitModule(repo_id, **kwargs)
        return jsonify(status)
    elif request.method == 'GET':
        repo_id = request.args['id']
        status = hub.viewSubmissionStatus(repo_id)
        if status:
            return jsonify(status)
        else:
            return 'Submission not found', 404

@app.route('/sugget')
@app.route('/sugget/')
@app.route('/sugget/<string:query>')
def handle_suggetions(query=None):
    # TODO: sanitize query
    if query:
        return jsonify(hub.viewSearchSuggestions(query))
    else:
        return jsonify([])

if __name__ == '__main__':
    app.run()