#!/bin/bash
set -euo pipefail

KUBECTL_VERSION="${KUBECTL_VERSION:-v1.33.1}"
INGRESS_NS="${INGRESS_NS:-nok-bng}"
INGRESS_SVC="${INGRESS_SVC:-nok-apps-ingress}"
SCRIPT_DIR="${SCRIPT_DIR:-/core-dns-editor}"
CORE_DNS_CONFIG="${CORE_DNS_CONFIG:-/tmp/coredns.yaml}"

cd "$SCRIPT_DIR"

echo "Installing kubectl ${KUBECTL_VERSION}"
curl -L -o ./kubectl https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl
chmod +x ${SCRIPT_DIR}/kubectl

# install python dependencies
pip install -r "${SCRIPT_DIR}/requirements.txt"

# get external IP or hostname of ingress controller
IP=$(${SCRIPT_DIR}/kubectl -n $INGRESS_NS get ingress $INGRESS_SVC -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
FQDN=$(${SCRIPT_DIR}/kubectl -n $INGRESS_NS get ingress $INGRESS_SVC -o jsonpath='{.spec.rules[0].host}')

if [ -z "$IP" ] && [ -z "$FQDN" ]; then
  echo "ERROR: ingress controller has no external IP/hostname"
  exit 1
fi

TARGET="$IP"
if [ -z "$TARGET" ]; then TARGET="$FQDN"; fi

# get Corefile, patch in hosts entry
${SCRIPT_DIR}/kubectl -n kube-system get cm coredns -o yaml > ${CORE_DNS_CONFIG}
python3 ${SCRIPT_DIR}/coredns_editor.py ${CORE_DNS_CONFIG} --ip $IP --hostname $FQDN -i
${SCRIPT_DIR}/kubectl -n kube-system replace cm coredns -f  ${CORE_DNS_CONFIG}
${SCRIPT_DIR}/kubectl -n kube-system rollout restart deployment/coredns