#!/bin/bash
set -euxo pipefail

export HOME=/root
WORKDIR=/opt/medallion-analytics
mkdir -p "$WORKDIR"
cd "$WORKDIR"

cat > .env <<EOF
POSTGRES_PASSWORD=${postgres_password}
SUPERSET_SECRET_KEY=${superset_secret_key}
SUPERSET_ADMIN_PASSWORD=${superset_admin_password}
EOF

cat > docker-compose.yml <<'COMPOSE_EOF'
${docker_compose_content}
COMPOSE_EOF

# Amazon Linux 2023
dnf update -y
dnf install -y docker
systemctl enable docker
systemctl start docker

# t3.micro needs extra memory for Postgres + Superset
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

curl -L "https://github.com/docker/compose/releases/download/v2.27.1/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

docker-compose pull
docker-compose up -d

echo "Medallion analytics stack started" > "$WORKDIR/bootstrap.done"
