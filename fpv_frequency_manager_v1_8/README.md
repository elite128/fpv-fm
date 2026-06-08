# FPV Frequency Manager v1.7

Lokaler Frequency Manager für FPV Freestyle- und Racing-Events.

## Features

- Helles Tageslicht-Theme
- WebSockets: Live-Updates ohne Refresh
- QR-Code mit FQDN aus `config.yaml`
- Display-Modus unter `/display`
- Admin-/Race-Director-Modus
- Admin kann Piloten manuell hinzufügen, bearbeiten und entfernen
- Bulk-Import, z. B. `Jan,R2`
- Kanäle sperren/freigeben
- Kanalempfehlungen
- Konfliktwarnung vor Kanalwahl
- Schlanke Standardansicht: DJI, Raceband und Band A
- Zusätzliche Bänder in YAML vorbereitet: B, E, FatShark

## Start

```bash
cd fpv_frequency_manager_v1_7
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Aufrufen

Teilnehmer:

```text
http://rotorhazard.localdomain:8000
```

Display-Modus:

```text
http://rotorhazard.localdomain:8000/display
```

## Konfiguration

Alle wichtigen Einstellungen stehen in `config.yaml`:

```yaml
event_name: "FPV Meetup"

server:
  public_hostname: "rotorhazard.localdomain"
  port: 8000

admin:
  password: "fpvrace"

conflicts:
  warning_mhz: 25
  critical_mhz: 15

ui:
  primary_groups:
    - DJI
    - Raceband
  secondary_groups:
    - BandA
```

Der QR-Code nutzt automatisch:

```text
http://<public_hostname>:<port>
```

## Hinweise zum FQDN

Damit `rotorhazard.localdomain` auf Handys funktioniert, muss der Name im Event-WLAN auf deinen Laptop zeigen. Mögliche Wege:

- Router/DNS-Eintrag setzen
- mDNS/Bonjour verwenden, falls euer Netzwerk das unterstützt
- alternativ in `config.yaml` direkt die Laptop-IP eintragen, z. B. `192.168.178.50`

## Admin-Modus

Standard-Passwort:

```text
fpvrace
```

Bitte vor echten Events in `config.yaml` ändern.

## Bulk-Import

Im Admin-Modus kannst du mehrere Piloten einfügen:

```text
Jan,R2
Oliver,DJI1
Chris,A3
```

oder:

```text
Jan R2
Oliver DJI1
Chris A3
```
