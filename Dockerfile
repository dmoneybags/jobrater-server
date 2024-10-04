#(c) 2024 Daniel DeMoney. All rights reserved.

# Use a lightweight Python image as the base
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

RUN apt-get update && apt-get install -y wget bzip2 libaugeas0 libxtst6 libgtk-3-0 libx11-xcb-dev libdbus-glib-1-2 libxt6 libpci-dev && rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.35.0/geckodriver-v0.35.0-linux64.tar.gz && \
    tar -xvzf geckodriver-v0.35.0-linux64.tar.gz && \
    rm geckodriver-v0.35.0-linux64.tar.gz
ENV PATH=/geckodriver:$PATH

#Create a directory to store APT repository keys if it doesn't exist:
#Get the signing key
RUN install -d -m 0755 /etc/apt/keyrings && \
    wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O /etc/apt/keyrings/packages.mozilla.org.asc && \
    echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list && \
    apt-get update && apt-get install -y --no-install-recommends firefox && \
    rm -rf /var/lib/apt/lists/*

# Update package list and create the directory for JDK
RUN wget https://download.oracle.com/java/17/latest/jdk-17_linux-x64_bin.tar.gz && \
    tar -xvzf jdk-17_linux-x64_bin.tar.gz && \
    rm jdk-17_linux-x64_bin.tar.gz && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# Set JAVA_HOME and update PATH
ENV JAVA_HOME=/app/jdk-17.0.12
ENV PATH=$JAVA_HOME/bin:$PATH

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install dependencies
COPY requirements.txt .
# Install Python dependencies without cache and ensure no unnecessary packages remain
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3 -m nltk.downloader stopwords

# Copy the entire project directory into the container
COPY . .

# Set the command to run your app

CMD ["sh", "-c", "PYTHONPATH=src/background gunicorn -w 3 -b 0.0.0.0:5001 --certfile=fullchain.pem --keyfile=privkey.pem --log-level=info database_server:app"]
