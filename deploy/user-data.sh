#!/bin/bash
# EC2 인스턴스 생성 시 "사용자 데이터"에 붙여넣는 스크립트 (Ubuntu 24.04 LTS 기준).
# 도커·컴포즈·AWS CLI를 깔고 저장소를 받아두는 데까지만 한다.
# 실제 기동은 .env를 채워야 하므로 SSH로 붙어서 사람이 한다 — 절차는 docs/배포_AWS_v1.md.
#
# 로그: /var/log/cloud-init-output.log

set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git unzip

# 도커 공식 저장소 (배포판 기본 패키지는 버전이 뒤처진다)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
usermod -aG docker ubuntu   # 재로그인 후부터 sudo 없이 docker 사용

# AWS CLI v2 — ECR 로그인에 쓴다
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

# 배포 파일 받아두기
sudo -u ubuntu git clone https://github.com/dygksjohn/sorisaegim.git /home/ubuntu/sorisaegim

echo "user-data done"
