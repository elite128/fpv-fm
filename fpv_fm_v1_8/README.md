# FPV Frequency Manager (FPV-FM) v1.8

Local video transmitter frequency coordinator for FPV Freestyle and Racing events.

## Features

- **Daylight-Optimized Theme**: Radically high-contrast light theme enabled by default for maximum screen readability under direct bright sunlight, with toggle option back to dark mode.
- **WebSockets Live Sync**: Real-time state updates across all connected devices in the field without page refreshes.
- **Local HTTPS / SSL Support**: Runs securely with an auto-generated self-signed certificate.
- **Dynamic QR Code**: Generates connection links using hostnames or LAN IP addresses specified in `config.yaml`.
- **Telemetry Display Mode**: Clean TV/monitor dashboard layout located at `/display` with massive fonts for mirroring telemetry to field monitors.
- **Admin / Race Control Modus**: Manage the entire event from a password-secured panel.
- **Pilot Management**: Admin can manually add, edit, or delete pilot profiles.
- **Bulk Import**: Paste pilot data directly, e.g. `Jan,R2` or `Oliver DJI1`.
- **Channel Locks**: Instantly lock/unlock specific frequencies or bands.
- **Channel Recommendations**: Suggests free, conflict-free channels with the largest frequency spacing to other pilots.
- **Overlap Verification**: Shows instant visual alerts and confirmation prompts when selecting critical adjacent frequencies.
- **Band Presets**: Out-of-the-box support for DJI, DJI O3/O4, FatShark, Raceband, and Bands A, B, and E.

---

## Local Setup

Activate your virtual environment and install dependencies:

```bash
cd fpv-frequency-manager
python3 -m venv .venv
```

### Windows:

```bash
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux:

```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Running the Application

### Secure SSL / HTTPS Mode (Recommended)

To start the server securely using the pre-generated certificate:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Open in your browser:
- Main App: `https://localhost:8000`
- Telemetry Screen: `https://localhost:8000/display`

> [!NOTE]
> Since this runs with a self-signed certificate, your browser will display a safety warning. Click "Advanced" -> "Proceed to localhost (unsafe)" to open the app.

### HTTP Mode (Fallback)

If you wish to run without SSL, make sure to set `use_https: false` in `config.yaml` or set the environment variable `USE_HTTPS=false`. Then start with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open in your browser:
- Main App: `http://localhost:8000`
- Telemetry Screen: `http://localhost:8000/display`

---

## Configuration

All event parameters are configured inside `config.yaml`:

```yaml
event_name: "FPV Meetup"

server:
  public_hostname: "iMac-10.local"
  port: 8000
  use_https: true

admin:
  password: "propfest"

conflicts:
  warning_mhz: 25
  critical_mhz: 15

ui:
  primary_groups:
    - DJI_O3O4_25Mbps
    - Raceband
  secondary_groups:
    - DJI_V1_25Mbps
```

---

## FQDN / Network Routing

To make the hostname (e.g. `iMac-10.local`) accessible to other devices (smartphones, tablets) connected to the local event Wi-Fi:
- Ensure mDNS/Bonjour is enabled on your network (standard on most modern routers).
- Alternatively, write your laptop's current local IP address (e.g., `192.168.178.50`) in the `public_hostname` field.

---

## Admin / Race Control

Default admin password is defined under the `admin.password` property in `config.yaml`.
Make sure to change the password before hosting public events.

---

## Bulk Import

Inside the Admin panel, you can import multiple pilots at once. Format:
```text
Jan,R2
Oliver,DJIO3O4_1
Chris,A3
```
or space-separated:
```text
Jan R2
Oliver DJIO3O4_1
Chris A3
```
