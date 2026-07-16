# Cygnus GNU SH toolchain (cygnus-2.7-96Q3) container: dosemu2 + the
# DOS-hosted DJGPP/go32 compiler + modern sh-elf binutils.
#
# Secondary toolchain (Bucket 0 verdict): used only for the suspected
# GCC-family middleware pocket, not for the dominant SHC code population.
#
# Setup replicates xeeynamo/sotn-decomp's proven recipe. The compiler
# binaries are public mirrors, pinned by sha256 and parameterized below.
FROM ubuntu:noble

ARG DOSEMU_DEB_REPO=https://github.com/sozud/dosemu-deb.git
ARG CYGNUS_URL=https://github.com/Xeeynamo/sotn-decomp/releases/download/cc1-psx-26/cygnus-2.7-96Q3-bin.tar.gz
ARG CYGNUS_SHA256=04ea5aad6daac640c445e571453e7477896e2e3e1e4219787d268233fc9f4960

RUN apt-get update && apt-get install -y --no-install-recommends \
      wget ca-certificates git binutils-sh-elf && \
    rm -rf /var/lib/apt/lists/*

# dosemu2 + fdpp + comcom32 (prebuilt debs from the sotn-decomp/saturn-decomp
# community, same ones xeeynamo/sotn-decomp's own Dockerfile installs)
RUN git clone --depth 1 "$DOSEMU_DEB_REPO" /tmp/dosemu-deb && \
    (dpkg -i /tmp/dosemu-deb/fdpp_1.6-1_amd64.deb || true) && \
    (dpkg -i /tmp/dosemu-deb/fdpp-dev_1.6-1_amd64.deb || true) && \
    (dpkg -i /tmp/dosemu-deb/comcom32_0.1~alpha3-1_all.deb || true) && \
    (dpkg -i /tmp/dosemu-deb/dosemu2_2.0~pre9-1_amd64.deb || true) && \
    apt-get update && apt-get install -f -y && \
    rm -rf /tmp/dosemu-deb /var/lib/apt/lists/*

RUN mkdir -p /opt/GCCSH && \
    wget -q -O /tmp/cygnus.tar.gz "$CYGNUS_URL" && \
    echo "$CYGNUS_SHA256  /tmp/cygnus.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/cygnus.tar.gz -C /opt/GCCSH && \
    rm /tmp/cygnus.tar.gz

# dosemu2 refuses to run as root; the container is always run with
# `--user $(id -u):$(id -g)` (see run.sh), with a tmpfs at /whome owned by
# the invoking uid for dosemu's dot-files.
ENV HOME=/whome

WORKDIR /work
ENTRYPOINT ["/bin/bash"]
