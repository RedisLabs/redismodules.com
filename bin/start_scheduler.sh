#!/bin/bash
rqscheduler --interval 60 --url $QUEUE_REDIS_URL
