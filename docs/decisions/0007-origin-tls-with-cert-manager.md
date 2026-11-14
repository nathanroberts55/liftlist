# 0007 – Origin TLS with cert-manager

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Public traffic reaches Lift List through a Cloudflare Tunnel: `cloudflared` on the
host forwards to Traefik on `http://localhost:80`, and Cloudflare terminates TLS.
The cluster already has cert-manager and an `acme-issuer` ClusterIssuer that
solves ACME DNS-01 through Cloudflare, and the same setup is used by the owner's
other projects.

That left the origin unencrypted: anyone on the LAN hitting
`http(s)://<node-ip>` got plain HTTP, and Traefik answered 443 with its default
self-signed certificate. A publicly trusted certificate at the origin also keeps
the door open to pointing the tunnel at `https://localhost:443` later without
reworking the cluster.

## Decision

- **The Ingress has a `tls` block** for `<public-host>` with
  `secretName: liftlist` and `ingressClassName: traefik`.
- **A standalone `certificate.yaml`** requests a 90-day Let's Encrypt
  certificate for the host from the `acme-issuer` ClusterIssuer. Traefik loads
  the resulting secret because the Ingress references it.
- **DNS-01 stays the solver.** The tunnel only accepts inbound traffic for the
  configured hostname, so an HTTP-01 challenge would depend on proxy behaviour;
  DNS-01 needs no inbound challenge route.
- **The tunnel target is unchanged** (`http://localhost:80`). Cloudflare remains
  the public TLS terminator; the origin certificate covers direct access to
  Traefik on 443.
- **cert-manager renews the certificate**, roughly 30 days before expiry. No
  cron job or manual step is added.

## Alternatives considered

- **Keep the origin HTTP-only.** Rejected: direct LAN access stayed plaintext and
  443 kept serving Traefik's self-signed default certificate.
- **HTTP-01 with a Traefik solver Ingress.** Rejected: challenge traffic would
  have to traverse Cloudflare and the tunnel, making issuance dependent on proxy
  rules and redirects. DNS-01 is already configured and proven.
- **Use Traefik's default certificate.** Rejected: browsers warn on the
  self-signed cert and it expires every year without automation.
- **Point the tunnel at `https://localhost:443` now.** Rejected for now: it adds
  a hop and a dependency on renewal health without changing what public visitors
  see. It remains a one-line change later because the origin cert is trusted.

## Consequences

- The origin serves a valid Let's Encrypt certificate on 443; public visitors
  still see Cloudflare's edge certificate.
- Renewal depends on the Cloudflare API token in the `cert-manager-secrets`
  Secret. A failed renewal appears as `Ready=False` on the `Certificate`, so
  `kubectl -n liftlist get certificate` is the check to run if HTTPS at the
  origin breaks.
- `certificate.yaml` must be applied on a fresh cluster after the ClusterIssuer
  exists and before (or alongside) `ingress.yaml`.
- `k8s/README.md`, the root README, and TECH_SPEC §2/§10 now describe public
  Cloudflare termination plus origin TLS instead of claiming the origin has no
  TLS block.
