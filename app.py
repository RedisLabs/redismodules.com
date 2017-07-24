import os
import json
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash
from flask_bootstrap import Bootstrap

app = Flask(__name__)
Bootstrap(app)
app.config.from_object(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
))
app.config.from_envvar('REDISMODULES_SETTINGS', silent=True)

@app.route('/')
def show_modules():
    with open('modules.json') as fp:
        modules = json.load(fp)
    return render_template('index.html', modules=modules)

if __name__ == '__main__':
    app.run()