<div align="center">

# 🎋 Bambusleitung

**iperf3 Speedtest Scheduler mit Web-Dashboard**

[![Docker Build](https://github.com/Panda260/bambusleitung/actions/workflows/docker-build.yml/badge.svg)](https://github.com/Panda260/bambusleitung/actions/workflows/docker-build.yml)
[![Image](https://ghcr.io/Panda260/bambusleitung)](https://github.com/Panda260/bambusleitung/pkgs/container/bambusleitung)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

Bambusleitung ist ein containerisierter **iperf3-Client** der automatisch oder manuell Geschwindigkeitstests gegen einen entfernten iperf3-Server durchführt. Alle Ergebnisse werden in einer SQLite-Datenbank gespeichert und über ein modernes Web-Dashboard angezeigt.

## Features

| Feature | Beschreibung |
|---|---|
| 📡 **iperf3 Client** | Misst Download **und** Upload gegen einen iperf3-Server |
| ⏱ **Intervall-Tests** | Konfigurierbarer Scheduler (Standard: 15 Min) |
| 🚀 **Manueller Test** | Per Knopfdruck sofortigen Test starten |
| 🔒 **Mutex-Schutz** | Kein Doppel-Run: Auto wartet, Manuell schlägt fehl mit Meldung |
| 📊 **Live-Anzeige** | Echtzeit Download/Upload via WebSocket während des Tests |
| 📈 **History-Graph** | Chart.js Zeitreihen-Diagramm für alle vergangenen Tests |
| 📋 **History-Tabelle** | Vollständige Testliste mit Timestamps, Typ und Ergebnissen |
| 📥 **Excel-Export** | Formatierte `.xlsx`-Datei mit einem Klick |
| 🔐 **Optionaler Login** | Passwort-Schutz per ENV-Variable (kein Passwort = kein Login) |
| 🐳 **Docker-ready** | Multi-stage Build, non-root User, Healthcheck, persistente Daten |

---

## Schnellstart

### Voraussetzungen

- Docker + Docker Compose
- iperf3-Server am anderen Ende (Gegenstelle)

### Starten

```bash
# 1. compose-Datei herunterladen
curl -O https://raw.githubusercontent.com/Panda260/bambusleitung/main/docker-compose.yml

# 2. IP des iperf3-Servers eintragen (oder direkt in der Web-UI)
nano docker-compose.yml  # → IPERF_TARGET_IP anpassen

# 3. Starten
docker compose up -d

# 4. Web-UI öffnen
open http://localhost:5000
```

### Iperf3-Server einrichten (Gegenstelle)

```bash
# Einmalig starten
iperf3 -s -p 5201

# Als systemd-Service (dauerhaft)
cat > /etc/systemd/system/iperf3.service << 'EOF'
[Unit]
Description=iperf3 Server
After=network.target

[Service]
ExecStart=/usr/bin/iperf3 -s -p 5201
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now iperf3
```

---

## Konfiguration

Alle Einstellungen können über die Web-UI geändert werden. Die ENV-Variablen dienen als **Startwerte** beim ersten Start.

> [!NOTE]
> Änderungen über die Web-UI werden in `/data/config.json` (im Volume) gespeichert und haben Vorrang gegenüber den ENV-Werten.

### Alle Umgebungsvariablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `PORT` | `5000` | Port der Web-UI |
| `DATA_DIR` | `/data` | Pfad für Datenbank + Config |
| `FLASK_ENV` | `production` | `development` für Debug-Modus |
| `IPERF_TARGET_IP` | *(leer)* | IP/Hostname des iperf3-Servers |
| `IPERF_TARGET_PORT` | `5201` | Port des iperf3-Servers |
| `IPERF_INTERVAL_MINUTES` | `15` | Test-Intervall in Minuten |
| `IPERF_TEST_DURATION` | `10` | Testdauer pro Richtung (Sekunden) |
| `IPERF_ENABLED` | `false` | Auto-Tests beim Start aktiviert? |
| `UI_PASSWORD` | *(leer)* | Passwort für Web-UI – **leer = kein Schutz** |
| `SECRET_KEY` | *(auto)* | Flask Session-Key – wird auto-generiert wenn leer |

### docker-compose.yml (Beispiel)

```yaml
services:
  bambusleitung:
    image: ghcr.io/Panda260/bambusleitung:latest
    container_name: bambusleitung
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - bambusleitung_data:/data
    environment:
      - IPERF_TARGET_IP=192.168.1.100
      - IPERF_TARGET_PORT=5201
      - IPERF_INTERVAL_MINUTES=15
      - IPERF_ENABLED=true
      - UI_PASSWORD=meinGeheimesPasswort   # leer lassen = kein Login

volumes:
  bambusleitung_data:
```

---

## Web-UI Übersicht

```
┌─────────────────────────────────────────────────────┐
│  🎋 Bambusleitung          ● Verbunden   ⏱ 14:30   │
├───────────────────────┬─────────────────────────────┤
│  ⚙️ Konfiguration     │  🚀 Test starten            │
│  • Ziel-IP / Port     │                             │
│  • Intervall          │      ╔═══════════╗          │
│  • Testdauer          │      ║     ▶     ║          │
│  • Auto-Tests Toggle  │      ║ Jetzt     ║          │
│  [ 💾 Speichern ]     │      ║ messen    ║          │
│                       │      ╚═══════════╝          │
├───────────────────────┴─────────────────────────────┤
│  📡 Live-Test                              [LIVE]   │
│  ⬇ Download: 842.3 Mbit/s  ⬆ Upload: 756.1 Mbit/s  │
│  Jitter: 0.21ms  Verlust: 0.0%  Dauer: 10.0s       │
├─────────────────────────────────────────────────────┤
│  📊 Verlauf (Download ── Upload ─ ─)                │
│  [Chart.js Zeitreihen-Graph]                        │
├─────────────────────────────────────────────────────┤
│  📋 History                        [ 📥 Excel ]    │
│  Zeit         Typ      Ziel       ↓ Mbit ↑ Mbit    │
│  19.04 13:30  Auto     10.0.0.1   842.3  756.1      │
│  19.04 13:15  Manuell  10.0.0.1   838.7  741.2      │
└─────────────────────────────────────────────────────┘
```

---

## Passwort-Schutz

Der Login ist **optional** und wird nur aktiv wenn `UI_PASSWORD` gesetzt ist.

```bash
# Mit Passwort-Schutz
docker run -d -p 5000:5000 \
  -e UI_PASSWORD=meinPasswort \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  ghcr.io/Panda260/bambusleitung:latest

# Ohne Passwort-Schutz (Standard)
docker run -d -p 5000:5000 \
  ghcr.io/Panda260/bambusleitung:latest
```

> [!IMPORTANT]
> Setze immer einen eigenen `SECRET_KEY` wenn du `UI_PASSWORD` verwendest, damit Sessions nach einem Neustart gültig bleiben.

---

## Mutex-Schutz (Test-Kollisionen)

| Situation | Verhalten |
|---|---|
| Manueller Test läuft + Auto-Job feuert | Auto überspringt diesen Slot, kein Fehler |
| Automatischer Test läuft + Manuell-Button | Fehler: *"Ein automatischer Test läuft bereits"* |
| Test läuft + nochmal Manuell | Fehler: *"Ein manueller Test läuft bereits"* |

---

## GitHub Actions

### CI: Docker Build & Push zu GHCR

Wird bei jedem Push auf `main` und bei Pull Requests ausgeführt.

- Baut Multi-Plattform Image (`linux/amd64` + `linux/arm64`)
- Pusht zu `ghcr.io/Panda260/bambusleitung`
- Tags: `latest`, `sha-<commit>`, Semantic Versioning bei Tags (`v1.2.3`)
- Nutzt GitHub Actions Cache für schnelle Builds

### CD: SSH-Deploy

Manuell auslösen oder automatisch bei Push auf `main`.

Benötigte Repository-Secrets:

| Secret | Beispiel |
|---|---|
| `DEPLOY_SSH_HOST` | `1.2.3.4` |
| `DEPLOY_SSH_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | *(privater SSH-Key, PEM)* |
| `DEPLOY_SSH_PORT` | `22` |
| `DEPLOY_PATH` | `/opt/bambusleitung` |

---

## Architektur

```
Browser
  │
  ├─── HTTP REST (/api/*) ──────────────────────┐
  │                                             │
  └─── WebSocket (Socket.IO) ──────────────────►│
                                                │
                                          Flask + Eventlet
                                                │
                              ┌─────────────────┼─────────────────┐
                              │                 │                 │
                        APScheduler      threading.Lock     SQLite DB
                        (Intervall)       (Mutex)          (/data/*.db)
                              │                 │
                              └────────►  iperf3 CLI
                                        (subprocess)
```

---

## API-Referenz

| Method | Endpunkt | Auth | Beschreibung |
|---|---|---|---|
| `GET` | `/api/auth/status` | ✗ | Auth-Status prüfen |
| `POST` | `/api/auth/login` | ✗ | Anmelden |
| `POST` | `/api/auth/logout` | ✗ | Abmelden |
| `GET` | `/api/status` | ✗ | Test-Status (Healthcheck) |
| `GET` | `/api/config` | ✓ | Konfiguration lesen |
| `POST` | `/api/config` | ✓ | Konfiguration speichern |
| `POST` | `/api/run` | ✓ | Manuellen Test starten |
| `GET` | `/api/history` | ✓ | History abrufen |
| `GET` | `/api/export` | ✓ | Excel-Export herunterladen |

*Auth-Spalte: ✓ = login erforderlich wenn UI_PASSWORD gesetzt*

---

## Lizenz

MIT © 2024 Panda260

---

<div align="center">

*🤖 Dieses Projekt wurde vollständig mit Hilfe von KI entwickelt.*

</div>

