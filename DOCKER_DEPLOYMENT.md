# Local Docker Deployment with Cloudflare Tunnel

This setup runs the FastAPI app on your computer and lets Cloudflare Tunnel
connect to it. The app port is not published to your host or directly exposed
to the internet.

## Prerequisites

- Docker Engine with the Docker Compose plugin (`docker compose`)
- A Cloudflare account and a domain managed in Cloudflare
- A remotely-managed Cloudflare Tunnel token

## Configure the tunnel

1. In Cloudflare Zero Trust, create a remotely-managed tunnel and add a public
   hostname for the domain you want to use.
2. Set its service to `http://app:8000`. The `app` hostname resolves on the
   private Docker network shared with the `cloudflared` connector.
3. Copy `.env.example` to `.env` and replace the placeholder with the tunnel
   token. Keep `.env` private; it is ignored by Git and excluded from the image.

## Start and update

Start the application and connector:

```sh
docker compose up --build -d
```

Follow application logs:

```sh
docker compose logs -f app cloudflared
```

Update after changing code:

```sh
docker compose up --build -d
```

This is a production-style container command, so code is not bind-mounted and
Uvicorn reload is disabled. Rebuilding and recreating the container applies
changes.

## Data and shutdown

Generated student-name records are written to the `generated-names` volume at
`/runtime-data/generated_names.json`. It survives container replacement and
ordinary `docker compose down`; do not use `docker compose down -v` unless you
intend to delete this data.

The name registry contains personal data. Restrict access to the host and its
Docker volumes, and set an appropriate retention policy before using the app
with real student data.

## Local verification

The app health endpoint is available inside the Compose network at
`http://app:8000/health`. The public URL is the hostname configured in the
Cloudflare Tunnel dashboard. No router port-forwarding is required.