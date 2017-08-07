#!/bin/bash
gunicorn web:app -k eventlet -t 5 --log-file -