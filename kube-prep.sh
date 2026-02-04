#!/bin/sh

set -e

# install kubectl
curl -L -o /usr/local/bin/kubectl https://dl.k8s.io/release/v1.33.1/bin/linux/amd64/kubectl
chmod +x /usr/local/bin/kubectl


INGRESS_NS="${INGRESS_NS:-nok-bng}"
INGRESS_SVC="${INGRESS_SVC:-nok-apps-ingress}"
SCRIPT_DIR="${SCRIPT_DIR:-/opt/scripts}"

# get external IP or hostname of ingress controller
IP=$(kubectl -n $INGRESS_NS get ingress $INGRESS_SVC -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
FQDN=$(kubectl -n $INGRESS_NS get ingress $INGRESS_SVC -o jsonpath='{.spec.rules[0].host}}')

if [ -z "$IP" ] && [ -z "$FQDN" ]; then
  echo "ERROR: ingress controller has no external IP/hostname"
  exit 1
fi

TARGET="$IP"
if [ -z "$TARGET" ]; then TARGET="$FQDN"; fi

# get Corefile, patch in hosts entry
kubectl -n kube-system get cm coredns -o yaml > /tmp/coredns.yaml
python3 "$SCRIPT_DIR/coredns_editor.py" /tmp/coredns.yaml --ip $IP --hostname $FQDN -i
kubectl -n kube-system replace cm coredns -f  /tmp/coredns.yaml
kubectl -n kube-system rollout restart deployment/coredns