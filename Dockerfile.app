FROM debian
LABEL Name=rmhub-app Version=0.0.1 

RUN apt-get -y update
RUN apt-get install -y \
    python python-pip
RUN pip install --upgrade pip

WORKDIR /rmhub
ADD . /rmhub

RUN pip install .
