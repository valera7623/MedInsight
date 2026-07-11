# VPS Deployment

Step-by-step guide for Ubuntu/Debian VPS.

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 2 GB | 4 GB + swap |
| CPU | 1 vCPU | 2 vCPU |
| Disk | 20 GB | 40 GB SSD |
| OS | Ubuntu 22.04+ | |

## 1. Server preparation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git docker.io docker-compose-plugin curl
sudo usermod -aG docker $USER
```

## 2. SSH key for GitHub Actions

On your local machine:

```bash
ssh-keygen -t ed25519 -f medinsight_deploy -N ""
```

Public key → `~/.ssh/authorized_keys` on VPS.  
Private key → GitHub Secret `VPS_SSH_KEY`.

## 3. Clone

```bash
ssh user@your-vps
git clone https://github.com/valera7623/MedInsight.git ~/medinsight
cd ~/medinsight
```

## 4. Configuration

```bash
cp .env.example .env.production
nano .env.production
```

Required:

- `SECRET_KEY` — `openssl rand -hex 32`
- `ENVIRONMENT=production`
- `POSTGRES_PASSWORD` (deploy.sh builds `DATABASE_URL`)
- `CORS_ORIGINS` and `FRONTEND_URL` — your HTTPS domain
- `MFA_ENFORCED=true` (or `false` temporarily for maintenance)

After repo updates, sync new keys:

```bash
python scripts/sync_env_from_example.py
```

## 5. First deploy

```bash
chmod +x deploy.sh scripts/*.sh
./deploy.sh production
```

## 6. Reverse proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name medinsight.example.com;

    ssl_certificate     /etc/letsencrypt/live/medinsight.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/medinsight.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    client_max_body_size 500M;
}
```

Certbot:

```bash
sudo certbot --nginx -d medinsight.example.com
```

## 7. Swap (optional)

```bash
sudo SWAP_SIZE_GB=4 ./scripts/setup_swap.sh
```

## 8. Cron

```bash
# Weekly Docker cleanup (Sunday 3:00)
0 3 * * 0 /home/user/medinsight/scripts/docker_cleanup.sh weekly >> /var/log/medinsight-cleanup.log 2>&1
```

## 9. Verification

```bash
curl -s localhost:8000/health/ready
curl -s https://medinsight.example.com/health/ready
```

## Updates

Automatically via GitHub Actions (push to `main`) or manually:

```bash
cd ~/medinsight && git pull && ./deploy.sh production
```

If you changed only `.env`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate app celery_worker
```

## SSH alias

`~/.ssh/config`:

```
Host medinsight-vps
    HostName your-vps-ip
    User smdg
    IdentityFile ~/.ssh/medinsight_deploy
```
