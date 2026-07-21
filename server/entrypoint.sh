#!/bin/sh
set -e

KEY_FILE=/data/encryption.key

mkdir -p /data

if [ ! -f "$KEY_FILE" ]; then
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > "$KEY_FILE"
    echo "[resumorph] Generated new encryption key at $KEY_FILE"
fi

export MASTER_ENCRYPTION_KEY=$(cat "$KEY_FILE")

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
