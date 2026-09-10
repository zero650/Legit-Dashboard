# Operations

## Health checks

```bash
docker compose ps
curl -k --fail --silent --show-error https://localhost/accounts/login/ > /dev/null
```

PostgreSQL, Django, and Caddy each define a Docker health check. Investigate any service marked `unhealthy` with `docker compose logs SERVICE`.

## Backups

Back up both PostgreSQL and customer-uploaded media. Store backups outside this repository and protect them as sensitive data because they may contain passport details and documents.

```bash
mkdir -p backups
docker compose exec -T db pg_dump -U legit -d legit_dashboard -Fc > backups/legit-dashboard.dump
tar -czf backups/legit-dashboard-media.tgz media
```

Periodically test restoration into a disposable database. Restoring replaces database contents, so stop the web service first and verify the target database before running `pg_restore`.

## Credentials

- Use a long, unique `DJANGO_SECRET_KEY` and PostgreSQL password in production.
- Keep `DJANGO_CREATE_SUPERUSER=0` after creating the first administrator.
- Rotate bootstrap credentials immediately if they were ever shared.
- Put Cloudflare Access with MFA and login rate limiting in front of the production site.

## Certificate recovery

The local Caddy CA is stored in the `caddy_data` volume. Upgrade Caddy first. If local certificates remain invalid, recreate only the Caddy volumes after confirming that no custom certificates are stored there; do not remove the PostgreSQL volume.
