# ETG / RateHawk — static egress via forward proxy

ETG whitelists the **public IP your backend uses when calling** `api-sandbox.worldota.net` / production WorldOTA hosts. Noma’s `noma_prod` Lambda uses **dynamic** AWS egress unless you add VPC+NAT or a **forward proxy with a static IP**.

This guide covers the **proxy** approach: only RateHawk/ETG HTTP traffic goes through the proxy; DynamoDB, Cognito, S3, OpenAI, etc. stay on the normal Lambda path.

## How Noma is structured today

```text
┌─────────────────┐     HTTPS (Cognito JWT)      ┌──────────────────────────┐
│  NOMA web app   │ ───────────────────────────► │  API Gateway (REST)      │
│  app.travel…    │   /_schd/{pf}/{org}/call/…   │  us-east-1 (Zappa)       │
└─────────────────┘                              └────────────┬─────────────┘
                                                              │
                                                              ▼
                                                   ┌──────────────────────────┐
                                                   │  Lambda: noma_prod       │
                                                   │  (Flask / renglo-api)    │
                                                   │  handlers in backend pkg │
                                                   └────────────┬─────────────┘
                                                                │
                    ┌───────────────────────────────────────────┼───────────────────────────┐
                    │                                           │                           │
                    ▼                                           ▼                           ▼
            ┌───────────────┐                          ┌────────────────┐          ┌──────────────┐
            │ DynamoDB, S3, │                          │ ratehawk_*     │          │ ETG webhook  │
            │ Cognito, etc. │                          │ handlers       │          │ (inbound)    │
            │ direct HTTPS  │                          │ requests → ETG │          │ API Gateway  │
            └───────────────┘                          └───────┬────────┘          └──────────────┘
                                                               │
                                                               │  (after proxy setup)
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │ Forward proxy        │
                                                    │ (static Elastic IP)  │
                                                    └──────────┬───────────┘
                                                               │
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │ ETG / worldota.net   │
                                                    └──────────────────────┘
```

**Important directions**

| Direction | Who initiates | IP ETG cares about |
|-----------|---------------|-------------------|
| Search, prebook, booking | Lambda → ETG | **Proxy egress IP** (whitelist this) |
| Booking status webhook | ETG → your API | Your **API Gateway URL** (not egress IP) |

Handlers live under `extensions/backend/package/noma/handlers/ratehawk_*.py`. The frontend never calls ETG directly; it calls `POST …/_schd/…/call/noma/ratehawk_*`.

Credentials and base URL come from the org **`noma_config`** document (`ratehawk_base_url`, `ratehawk_key_id`, `ratehawk_api_key`).

## Code support (selective proxy)

`ratehawk_http.py` provides `etg_get` / `etg_post`, which attach a proxy only for ETG calls when configured.

**Configuration (pick one or both):**

1. **Lambda environment** (recommended for production secrets):

   ```text
   RATEHAWK_HTTPS_PROXY=http://USER:PASS@your-proxy-host:9293
   ```

   Add to `zappa_settings.json` → `noma_prod.environment_variables`, or GitHub Actions secret / AWS Console.

2. **Per-org `noma_config`** field `ratehawk_https_proxy` (same URL format). Useful for sandbox vs prod if you ever split proxies.

**Do not** set global `HTTPS_PROXY` on Lambda — that would send DynamoDB and all other traffic through the proxy.

## Option A — Managed static-IP proxy (fastest if new to this)

Providers aimed at Heroku/Lambda (examples, not endorsements):

- [QuotaGuard Static](https://www.quotaguard.com/products/quotaguard-static/)
- [Fixie](https://usefixie.com/)
- Similar “static outbound proxy” SaaS

Typical flow:

1. Sign up; choose region **us-east-1** (same as Lambda).
2. They give you a URL like `http://username:password@us-east-static-xx.example.com:9293` and the **static IP** to send ETG.
3. Set `RATEHAWK_HTTPS_PROXY` in Lambda (see above).
4. Deploy backend (`./zappa_update.sh noma_prod update`).
5. Trigger a hotel search; check CloudWatch for `[ratehawk_http] POST via proxy …`.
6. Email ETG the **static IP** from the provider dashboard (not the proxy hostname).

**Pros:** No Squid/VPC to operate. **Cons:** Monthly fee per static IP.

## Option B — Self-hosted Squid on EC2 + Elastic IP

Use when you want full control and lower recurring cost (you operate the box).

### B1. Launch proxy EC2

1. **EC2** → Launch instance: Amazon Linux 2023, `t3.nano` or `t3.micro`, **us-east-1**.
2. **Elastic IP** → Allocate → Associate with the instance. **This IP goes to ETG.**
3. Security group **inbound**: TCP **3128** (or your port) from `0.0.0.0/0` only if Lambda has no fixed egress — better: restrict to [AWS Lambda IP ranges](https://ip-ranges.amazonaws.com/ip-ranges.json) for `us-east-1` (large list; many teams use `0.0.0.0/0` + proxy auth instead).
4. Security group **outbound**: allow HTTPS `443` to `0.0.0.0/0`.

### B2. Install Squid (on the instance)

```bash
sudo dnf install -y squid
sudo tee /etc/squid/squid.conf <<'EOF'
acl SSL_ports port 443
acl Safe_ports port 443
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
auth_param basic program /usr/lib64/squid/basic_ncsa_auth /etc/squid/passwd
auth_param basic realm ETG Proxy
acl authenticated proxy_auth REQUIRED
http_access allow authenticated
http_access deny all
http_port 3128
EOF

# Replace 'etgproxy' / 'CHOOSE_A_STRONG_PASSWORD'
sudo htpasswd -cb /etc/squid/passwd etgproxy 'CHOOSE_A_STRONG_PASSWORD'
sudo systemctl enable --now squid
```

### B3. Configure Noma

```text
RATEHAWK_HTTPS_PROXY=http://etgproxy:CHOOSE_A_STRONG_PASSWORD@<ELASTIC_IP>:3128
```

Redeploy Lambda; verify search works; send **Elastic IP** to ETG.

### B4. Hardening (before production)

- Restrict inbound 3128 to known sources if possible.
- Rotate proxy password; store only in secrets manager / Zappa secrets.
- Enable CloudWatch agent or health check on the instance.
- Patch OS monthly.

## Verify end-to-end

1. Deploy with `RATEHAWK_HTTPS_PROXY` set.
2. Run `search_hotels_unified` or `ratehawk_geosearch` from the app.
3. CloudWatch: log line `[ratehawk_http] POST via proxy http://etgproxy:***@…`
4. On the proxy host: `sudo tail -f /var/log/squid/access.log` should show CONNECT to `api-sandbox.worldota.net`.
5. If ETG returns connection errors, confirm whitelist matches proxy **Elastic IP** (not Lambda IP).

## What to send ETG

```text
Outbound API integration (sandbox + production):
Static egress IP: x.x.x.x
Region: us-east-1 (AWS)
Note: Traffic is forwarded via authenticated HTTP proxy; whitelisted IP is the proxy egress.
```

## Local development

Your laptop has a different public IP than Lambda. Either:

- Point `RATEHAWK_HTTPS_PROXY` at the same proxy URL in `env.development`, or
- Ask ETG to whitelist your office IP temporarily for manual tests (not a substitute for prod).

## Related files

- `extensions/backend/package/noma/handlers/ratehawk_http.py` — proxy-aware client
- `extensions/backend/blueprints/noma_config.json` — optional `ratehawk_https_proxy` field
- `system/zappa_settings.json` — Lambda env for `RATEHAWK_HTTPS_PROXY`
