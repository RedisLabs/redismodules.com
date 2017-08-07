import json
import logging
import os
import sys
from datetime import datetime

import github
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_bootstrap import Bootstrap
from flask_socketio import SocketIO

from catalog import Catalog

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

catalog = Catalog()

app = Flask(__name__)
socketio = SocketIO(app)
Bootstrap(app)

@socketio.on('search')
def handle_search(query):
    logger.info(query)

@app.route('/')
def homepage():
    return render_template('index.html')

@app.route('/modules')
@app.route('/modules/<int:page>')
def modules(page=0):
    return json.dumps(catalog.getAllModules())

if __name__ == '__main__':
    socketio.run()
