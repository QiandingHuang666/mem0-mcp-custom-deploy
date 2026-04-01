#!/bin/bash
# 安装 mem0-stack 为 systemd service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 复制 env 模板（如果不存在）
if [ ! -f /etc/mem0-stack.env ]; then
    sudo cp "$SCRIPT_DIR/mem0-stack.env.example" /etc/mem0-stack.env
    echo "Created /etc/mem0-stack.env — please edit it before starting the service"
fi

# 安装 service
sudo cp "$SCRIPT_DIR/mem0-stack.service" /etc/systemd/system/
chmod +x "$SCRIPT_DIR/mem0-stack.sh"
sudo systemctl daemon-reload
sudo systemctl enable mem0-stack

echo "Service installed. Run: sudo systemctl start mem0-stack"
