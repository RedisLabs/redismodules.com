import os
import sys
import json
import github
import logging
from datetime import datetime
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash
from flask_bootstrap import Bootstrap
from flask_apscheduler import APScheduler

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class Config(object):
    JOBS = [
        {
            'id': 'startupstats',
            'func': 'app:getGitHubReposStats',
            'trigger': None
        },

        {
            'id': 'periodicstats',
            'func': 'app:getGitHubReposStats',
            'trigger': 'interval',
            'hours': 4
        }
    ]

    SCHEDULER_API_ENABLED = True

# Populates modules catalog with GitHub repositories stats
def getGitHubReposStats():
    # github.enable_console_debug_logging()
    g = github.Github(os.environ['GITHUB_TOKEN'])
    for module in modules:
        if 'repository' in module and \
            'type' in module['repository'] and \
            module['repository']['type'] == 'github' and \
            'name' in module['repository']:
            mr = module['repository']
            logger.info('Fetching stats for {}...'.format(mr['name']))
            gr = g.get_repo(mr['name'])
            mr['stargazers_count'] = gr.stargazers_count
            mr['forks_count'] = gr.forks_count
            last_modified = gr.pushed_at
            last_modified = datetime.today() - last_modified
            mr['last_modified'] = last_modified.days
            r = gr.get_releases()
            try:
                l = r[0]
                mr['last_release'] = {
                    'name': l.tag_name,
                    'url': l.url
                }
            except IndexError:
                pass

# Load modules catalog
def loadModulesCatalog():
    logger.info('Loading modules catalog... ')
    global modules
    with open('modules.json') as fp:
        modules = json.load(fp)
    logger.info('Modules catalog loading finished!')

modules = None
loadModulesCatalog()

app = Flask(__name__)
app.config.from_object(Config())

Bootstrap(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

@app.route('/')
def homepage():
    return render_template('index.html', modules=modules)

if __name__ == '__main__':
    app.run()
