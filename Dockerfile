FROM python:3.8.10

# optional labels to provide metadata for the Docker image
# (source: address to the repository, description: human-readable description)
LABEL org.opencontainers.image.source https://github.com/mehdiattar-lab/NetworkStatePredictor.git
LABEL org.opencontainers.image.description "Docker image for the Network State Predictor (NSP) component."

# create the required directories inside the Docker image
#
# the NetworkStatePredictor component has its own code in the NetworkStatePredictor
# directory and it uses code from the init, simulation-tools and domain-messages directories
# the logs directory is created for the logging output

RUN mkdir -p /NetworkStatePredictor
RUN mkdir -p /init
RUN mkdir -p /logs
RUN mkdir -p /simulation-tools
RUN mkdir -p /domain_messages

# install the python libraries inside the Docker image

COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip
RUN pip install -r /requirements.txt

# copy the required directories with their content to the Docker image

COPY NetworkStatePredictor/ /NetworkStatePredictor/
COPY init/ /init/
COPY simulation-tools/ /simulation-tools/
COPY domain_messages/ /domain_messages/

# set the working directory inside the Docker image
WORKDIR /

# start command that is run when a Docker container using the image is started
#
# in this case, "component" module in the "NSP" directory is started

CMD [ "python3", "-u", "-m", "NetworkStatePredictor.component" ]