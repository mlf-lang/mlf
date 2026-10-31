# Reproducible Linux environment for the GHC / MLF compiler shape benchmark.
#
# The benchmark needs process-group sampling through /proc, which macOS shells
# running under a restricted sandbox may deny. This image gives a Linux host with
# the same pinned toolchain the CI smoke job uses, so a full matrix can be
# measured on a Mac without weakening any resource guard.
#
#   docker build -f tools/performance/compiler-shapes/linux-environment.dockerfile \
#     -t mlf-compiler-shapes:9.14.1 tools/performance/compiler-shapes
#   docker run --rm -v "$PWD:/work" -w /work mlf-compiler-shapes:9.14.1 \
#     bash -lc 'python3 -B tools/performance/compiler-shapes/bench.py list'
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential clang libgc-dev libgmp-dev libnuma-dev libncurses-dev \
        pkg-config curl xz-utils git python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ARG GHC_VERSION=9.14.1
RUN set -eux; \
    curl -fsSL "https://downloads.haskell.org/~ghc/${GHC_VERSION}/ghc-${GHC_VERSION}-aarch64-deb12-linux.tar.xz" -o /tmp/ghc.tar.xz; \
    tar -xJf /tmp/ghc.tar.xz -C /tmp; \
    cd /tmp/ghc-${GHC_VERSION}-aarch64-unknown-linux; \
    ./configure --prefix=/opt/ghc >/dev/null; \
    make install >/dev/null; \
    rm -rf /tmp/ghc*; \
    /opt/ghc/bin/ghc --numeric-version
ENV PATH=/opt/ghc/bin:$PATH
WORKDIR /work
