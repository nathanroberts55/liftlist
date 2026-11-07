# Kubernetes deployment

The app runs as a single-replica Deployment in the `liftlist` namespace and is
exposed through Traefik via `ingress.yaml`. The Cloudflare Tunnel points at
`http://localhost:80` on the host, so it reaches Traefik rather than the pods
directly.

## Files

| File | Purpose |
|---|---|
| `configmap.yaml` | Non-secret settings: `DJANGO_DEBUG`, hosts, CSRF origin, workers, timezone. |
| `deployment.yaml` | The app container, probes, resources, and `Recreate` rollout strategy. |
| `service.yaml` | ClusterIP Service on port 8000. |
| `ingress.yaml` | Routes `liftlist.naterobertstech.com` to the Service. No TLS block; Cloudflare terminates TLS. |
| `secret.example.yaml` | Committed template only. Its Secret is named `app-secrets-example` so it cannot overwrite the real one. |
| `secrets.yaml` | Local/server-only real Secret. Gitignored. |

## Secret workflow

```bash
cp k8s/secret.example.yaml k8s/secrets.yaml
# Edit k8s/secrets.yaml:
#   - change metadata.name to app-secrets
#   - fill in DJANGO_SECRET_KEY
#   - fill in DATABASE_URL, for example:
#       postgres://ll_user:PASSWORD@100.86.17.28:5432/liftlist
#   - optionally fill in DJANGO_SUPERUSER_* for the first start
chmod 600 k8s/secrets.yaml
```

`DATABASE_URL` is a standard libpq connection string. `postgres://` and
`postgresql://` both work, and query parameters such as
`?sslmode=prefer&connect_timeout=10` are accepted. URL-encode special
characters in the password, or use an alphanumeric password.

## Apply

Create the namespace first, then apply the real secret and the workloads:

```bash
kubectl create namespace liftlist
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml
```

Do not run `kubectl apply -f k8s/`; apply the files explicitly so the example
Secret and any local-only files are never applied by accident.

## Why the probes set a Host header

Kubernetes HTTP probes use the pod IP as the `Host` header. Django only accepts
`liftlist.naterobertstech.com`, so a probe without the header gets a 400 and
the pod never becomes ready. Both probes therefore send:

```yaml
httpHeaders:
  - name: Host
    value: liftlist.naterobertstech.com
```

## Rollout

```bash
kubectl -n liftlist rollout status deployment/liftlist
kubectl -n liftlist logs deployment/liftlist --tail=100
```

After a new image is published to `:latest`:

```bash
kubectl -n liftlist rollout restart deployment/liftlist
```

Changing `secrets.yaml` also requires a restart so the pods pick up the new
environment variables.
