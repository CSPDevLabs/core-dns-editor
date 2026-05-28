FROM python:3.12-slim

ENV KUBECTL_VERSION=v1.33.1
ENV SCRIPT_DIR=/core-dns-editor
ENV INGRESS_NS=nok-bng
ENV INGRESS_SVC=nok-apps-ingress

WORKDIR ${SCRIPT_DIR}

# Install required OS packages
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -L -o /usr/local/bin/kubectl \
    https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    chmod +x /usr/local/bin/kubectl

COPY coredns_editor.py .
COPY update-coredns.sh .

RUN chmod +x update-coredns.sh