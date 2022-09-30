# Base the image off the python image
FROM python:3.10-slim-bullseye

# install some OS dependencies
RUN apt-get update && \
    apt-get upgrade -y

# upgrade pip
RUN python3 -m pip install --upgrade pip

# install some python dependencies
ADD requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# make the directory that will home the project
RUN mkdir /app && \
    chmod -R 777 /app

# make the directory that will hold the configuration
RUN mkdir /config && \
    chmod -R 777 /config

ADD api/*.py /app/

# copy in the start script
ADD start /start
RUN chmod +x /start

# run our entrypoint
CMD /start

