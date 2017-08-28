FROM debian
LABEL Name=rmhub-app Version=0.0.1 

RUN apt-get -y update
RUN apt-get install -y \
    python python-pip
RUN pip install --upgrade pip

WORKDIR /rmhub
ADD ./requirements.txt /rmhub/requirements.txt
RUN pip install -r requirements.txt

ADD . /rmhub
RUN pip install .
