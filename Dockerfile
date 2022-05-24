FROM fedora
MAINTAINER https://github.com/SatelliteQE

RUN dnf -y install git python3-pip python3-devel && dnf clean all
WORKDIR /root/manifester
ENV MANIFESTER_DIRECTORY=/root/manifester/
COPY . /root/manifester/
RUN pip install .
RUN cp manifester_settings.yaml.example manifester_settings.yaml


ENTRYPOINT ["manifester"]
CMD ["--help"]
