# UAS/UTM Service Quick Start

## PowerShell

```powershell
.\scripts\run_uas_utm_service.ps1
```

Open:

- http://127.0.0.1:8080
- http://127.0.0.1:8080/api/summary
- http://127.0.0.1:8080/api/protocol

## Docker

Docker Desktop must be running.

```bash
docker build -t dah-uas-utm-service .
docker run --rm -p 8080:8080 dah-uas-utm-service
```

## Docker Compose

```bash
docker compose up --build
```
