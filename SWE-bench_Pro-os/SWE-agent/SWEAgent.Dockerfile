# SWE Agent Dockerfile
# This Dockerfile sets up the SWE Agent environment with all necessary dependencies
# and installs the required swerex patch.
FROM python:3.11

WORKDIR /app

COPY . /app

RUN pip install -e .

# Install swerex from official SWE-Agent repo at version 1.2.0
RUN git clone https://github.com/SWE-Agent/SWE-ReX.git /SWE-ReX
WORKDIR /SWE-ReX
RUN git checkout v1.2.0
RUN pip install -e .

# Apply local SWE-Rex patches
WORKDIR /app
RUN python swerex_patches/patch.py --yes

WORKDIR /app

CMD ["/bin/bash"]