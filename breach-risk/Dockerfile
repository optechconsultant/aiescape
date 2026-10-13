# Image for REAL-model runs. Build once on a machine that can pull from Docker Hub:
#   docker build -t breach-agent:latest .
FROM python:3.12-slim
RUN useradd -m agent && mkdir -p /workspace /restricted && chown agent:agent /workspace
USER agent
WORKDIR /workspace
