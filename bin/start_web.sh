#!/bin/bash
gunicorn rmhub.web:app -k eventlet -t 5 -b 0.0.0.0:8000 --log-file -
