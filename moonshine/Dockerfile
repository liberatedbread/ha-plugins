ARG TARGETARCH
FROM ghcr.io/home-assistant/amd64-base-debian:bookworm AS amd64
FROM ghcr.io/home-assistant/aarch64-base-debian:bookworm AS arm64

FROM ${TARGETARCH}

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
# Needed to allow us to pip install over system packages, this makes sense since it's a single purpose container.
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Set Python 3 as default python
RUN echo 'alias python=python3' >> ~/.bashrc && \
    echo 'alias pip=pip3' >> ~/.bashrc

# Make sure we have build tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential netcat-traditional git cmake patchelf \
        python3 python3-full python3-dev python3-pip && \
    apt-get clean && \
    pip install --no-cache-dir "wyoming[zeroconf]==1.8.0" 'transformers==4.52.4' 'onnx-asr[cpu,hub]==0.7.0' && \
    pip install --no-cache-dir --index-url 'https://download.pytorch.org/whl/cpu' 'torch==2.6.0' && \
    rm -rf /var/lib/apt/lists/*

# Install moonshine voice seperately for caching
RUN pip install moonshine-voice

# Insall the moonshine binding. ARG/VERSION here since it doesn't impact above.
ARG VERSION
ENV MOONSHINE_VERSION=${VERSION}

RUN git clone --depth 1 https://github.com/holdenk/wyoming-moonshine-ext.git --branch ${MOONSHINE_VERSION} && \
    pip install -e ./wyoming-moonshine-ext


WORKDIR /
COPY rootfs /

HEALTHCHECK --start-period=10m \
    CMD echo '{ "type": "describe" }' \
        | nc -w 1 localhost 10300 \
        | grep -q "moonshine" \
        || exit 1
