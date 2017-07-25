import os
import sys
import json
import github
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash
from flask_bootstrap import Bootstrap

scheduler = BackgroundScheduler()
app = Flask(__name__)
Bootstrap(app)

# Load modules catalog
sys.stdout.write('Loading modules catalog... ')
with open('modules.json') as fp:
    modules = json.load(fp)
sys.stdout.write('finished!\n')
sys.stdout.flush()

# Populates modules catalog with GitHub repositories stats
@scheduler.scheduled_job('interval', max_instances=1, hours=4)
def getGitHubReposStats():
    # github.enable_console_debug_logging()
    g = github.Github('d885b41760b9026320eed0c7086b085c7608afe5')
    sys.stdout.write('Fetching GitHub repositories stats...\n')
    sys.stdout.flush()
    for module in modules:
        if 'repository' in module and \
            'type' in module['repository'] and \
            module['repository']['type'] == 'github' and \
            'name' in module['repository']:
            mr = module['repository']
            sys.stdout.write('Fetching stats for {}...'.format(mr['name']))
            gr = g.get_repo(mr['name'])
            mr['stargazers_count'] = gr.stargazers_count
            mr['forks_count'] = gr.forks_count
            # last_modified = gr.pushed_at
            # last_modified = datetime.today() - last_modified
            # mr['last_modified'] = last_modified.days
            sys.stdout.write('done!\n')
            sys.stdout.flush()

@app.route('/')
def homepage():
    return render_template('index.html', modules=modules)

if __name__ == 'app' or __name__ == '__main__':
    sys.stdout.write('Starting app')
    sys.stdout.flush()
    scheduler.add_job(getGitHubReposStats)  # run immediately once    
    scheduler.start()
    app.run()
