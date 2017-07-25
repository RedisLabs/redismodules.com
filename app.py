import os
import json
import github
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash
from flask_bootstrap import Bootstrap

logging.basicConfig()
scheduler = BackgroundScheduler()
app = Flask(__name__)
Bootstrap(app)
app.config.from_object(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
))
app.config.from_envvar('REDISMODULES_SETTINGS', silent=True)

# Load modules catalog
print "Loading modules catalog"
with open('modules.json') as fp:
    modules = json.load(fp)

# Populates modules catalog with GitHub repositories stats
@scheduler.scheduled_job('interval', max_instances=1, hours=4)
def getGitHubReposStats():
    # github.enable_console_debug_logging()
    g = github.Github('d885b41760b9026320eed0c7086b085c7608afe5')
    print "Fetching GitHub repositories' stats"
    for module in modules:
        if 'repository' in module and \
            'type' in module['repository'] and \
            module['repository']['type'] == 'github' and \
            'name' in module['repository']:
            mr = module['repository']
            gr = g.get_repo(mr['name'])
            mr['stargazers_count'] = gr.stargazers_count
            mr['forks_count'] = gr.forks_count
            last_modified = datetime.today() - gr.pushed_at
            mr['last_modified'] = last_modified.days

@app.route('/')
def show_modules():
    return render_template('index.html', modules=modules)

if __name__ == '__main__':
    scheduler.add_job(getGitHubReposStats)  # run immediately once
    scheduler.start()
    app.run()