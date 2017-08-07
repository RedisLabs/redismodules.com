FROM ubuntu:latest
LABEL Name=redismodules.com-app Version=0.0.1 

RUN apt-get -y update
RUN apt-get install -y \
    python python-pip

ADD ./requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

ADD . /app
