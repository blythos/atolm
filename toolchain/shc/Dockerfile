# SHC runtime container: Wine + sh-elf binutils, no compiler binaries baked in.
#
# The Hitachi SHC 5.0 (Release31) toolchain is proprietary and is NOT part of
# this image or this repo. `make setup` fetches and sha256-verifies it into
# toolchain/vendor/shc/ (gitignored), which is bind-mounted at /opt/shc when
# the container runs. See toolchain/fetch-shc.sh.
FROM ubuntu:noble

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      wine wine32:i386 wine64 binutils-sh-elf ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# The container is always run with `--user $(id -u):$(id -g)` (see run.sh) so
# build output is owned by the invoking user. That uid has no passwd entry or
# home dir in the image; run.sh mounts a tmpfs at /whome owned by the
# invoking uid for wine's prefix.
ENV HOME=/whome
ENV WINEPREFIX=/whome/wine

# SHC's required environment (trailing backslashes are load-bearing: omitting
# them causes error 3321 "Illegal environment variable"). Z: is wine's map of
# the container root, so Z:\opt\shc\ = /opt/shc (vendor mount) and
# Z:\work\ = /work (bind-mounted build dir).
ENV SHCPU=SH2
ENV SHC_LIB=Z:\\opt\\shc\\
ENV SHC_INC=Z:\\opt\\shc\\
ENV SHC_TMP=Z:\\tmp\\

WORKDIR /work
ENTRYPOINT ["/bin/bash"]
