FROM mcr.microsoft.com/devcontainers/python:3.14

# Install GDB
RUN apt-get update && \
    apt-get install -y --no-install-recommends gdb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch to non-root user and install Python packages
USER vscode
RUN python -m pip install black flake8 tox