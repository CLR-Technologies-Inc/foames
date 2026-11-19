# OpenFOAM worker image for the foames-openfoam runner.
#
# SCAFFOLD: the base image tag must be verified against OpenFOAM's published
# v2606 packages before use (see docs/vendors/openfoam/README.md). OpenFOAM is
# GPL; its binaries live ONLY in this worker image and are never bundled into
# the Apache-2.0 FoaMES package. The runner talks to the solver through its
# command-line tools as a separate process — no linking, no source inclusion.
#
# Build:  docker build -t foames-openfoam-worker:2606 bridges/openfoam/worker
# Run:    docker run --rm -v /var/lib/foames-openfoam:/work -p 8765:8765 \
#           -e FOAMES_OPENFOAM_TOKEN=... foames-openfoam-worker:2606 serve

ARG OPENFOAM_IMAGE=openfoam/openfoam2606:2606
FROM ${OPENFOAM_IMAGE}

# The runner itself is standard-library Python; install it without dependencies.
COPY bridges/openfoam /opt/foames-openfoam
RUN python3 -m pip install --no-deps /opt/foames-openfoam

# Non-root execution: the solver never needs root.
RUN useradd --create-home --uid 10001 foames && chown -R foames /work 2>/dev/null || true
USER foames

ENV FOAM_TUTORIALS=/opt/openfoam*/tutorials
WORKDIR /work
EXPOSE 8765

ENTRYPOINT ["python3", "-m", "foames_openfoam"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
