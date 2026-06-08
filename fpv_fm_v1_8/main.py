import base64
import io
import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import qrcode
import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

APP_VERSION = "1.8"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
PERSISTENCE_PATH = BASE_DIR / "data.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg
    return {}


CONFIG: dict = {}
EVENT_NAME: str = "FPV Meetup"
PUBLIC_HOSTNAME: str = "rotorhazard.localdomain"
PUBLIC_PORT: int = 8000
USE_HTTPS: bool = False
ADMIN_PASSWORD: str = "fpvrace"
YELLOW_SPACING_MHZ: int = 25
RED_SPACING_MHZ: int = 15
CLEANUP_ENABLED: bool = True
AUTO_CLEANUP_SECONDS: int = 21600

PRIMARY_GROUPS: List[str] = ["DJI", "Raceband"]
SECONDARY_GROUPS: List[str] = ["BandA"]
ADMIN_ONLY_GROUPS: List[str] = []
VISIBLE_GROUPS: List[str] = PRIMARY_GROUPS + SECONDARY_GROUPS
ALL_GROUPS: dict = {}

CHANNELS: Dict[str, int] = {}
CHANNEL_TO_GROUP: Dict[str, str] = {}


def reload_config_in_memory(cfg: dict) -> None:
    global CONFIG, EVENT_NAME, PUBLIC_HOSTNAME, PUBLIC_PORT, USE_HTTPS, ADMIN_PASSWORD
    global YELLOW_SPACING_MHZ, RED_SPACING_MHZ, CLEANUP_ENABLED, AUTO_CLEANUP_SECONDS
    global PRIMARY_GROUPS, SECONDARY_GROUPS, ADMIN_ONLY_GROUPS, VISIBLE_GROUPS, ALL_GROUPS
    global CHANNELS, CHANNEL_TO_GROUP

    CONFIG = cfg
    EVENT_NAME = CONFIG.get("event_name", "FPV Meetup")
    host_env = os.environ.get("PUBLIC_HOSTNAME", "").strip()
    PUBLIC_HOSTNAME = host_env if host_env else CONFIG.get("server", {}).get("public_hostname", "rotorhazard.localdomain")

    port_env = os.environ.get("PORT", "").strip()
    PUBLIC_PORT = int(port_env) if port_env else int(CONFIG.get("server", {}).get("port", 8000))

    https_env = os.environ.get("USE_HTTPS", "").strip()
    if https_env:
        USE_HTTPS = https_env.lower() in ("true", "1", "yes")
    else:
        USE_HTTPS = bool(CONFIG.get("server", {}).get("use_https", False))
    ADMIN_PASSWORD = str(CONFIG.get("admin", {}).get("password", "fpvrace"))
    YELLOW_SPACING_MHZ = int(CONFIG.get("conflicts", {}).get("warning_mhz", 25))
    RED_SPACING_MHZ = int(CONFIG.get("conflicts", {}).get("critical_mhz", 15))
    CLEANUP_ENABLED = bool(CONFIG.get("cleanup", {}).get("enabled", True))
    AUTO_CLEANUP_SECONDS = int(float(CONFIG.get("cleanup", {}).get("inactive_hours", 6)) * 3600)

    ui_cfg = CONFIG.get("ui", {})
    PRIMARY_GROUPS = ui_cfg.get("primary_groups", ["DJI", "Raceband"])
    SECONDARY_GROUPS = ui_cfg.get("secondary_groups", ["BandA"])
    ADMIN_ONLY_GROUPS = ui_cfg.get("admin_only_groups", [])
    VISIBLE_GROUPS = PRIMARY_GROUPS + SECONDARY_GROUPS
    ALL_GROUPS = CONFIG.get("channel_groups", {})

    CHANNELS.clear()
    CHANNEL_TO_GROUP.clear()
    for group_name, group_channels in ALL_GROUPS.items():
        for channel_name, frequency in group_channels.items():
            ch = str(channel_name).upper()
            CHANNELS[ch] = int(frequency)
            CHANNEL_TO_GROUP[ch] = str(group_name)


# Load initial config
reload_config_in_memory(load_config())



@dataclass
class Pilot:
    name: str
    channel: Optional[str] = None
    frequency: Optional[int] = None
    created_by: str = "self"  # self/admin/import
    updated_at: float = 0.0
    ip_address: Optional[str] = None


pilots: Dict[str, Pilot] = {}
locked_channels: Set[str] = set()
connections: List[WebSocket] = []


def save_persistence() -> None:
    try:
        data = {
            "pilots": {name: asdict(p) for name, p in pilots.items()},
            "locked_channels": list(locked_channels)
        }
        with PERSISTENCE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving persistence: {e}")


def load_persistence() -> None:
    global pilots, locked_channels
    if not PERSISTENCE_PATH.exists():
        return
    try:
        with PERSISTENCE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            raw_pilots = data.get("pilots", {})
            for name, p in raw_pilots.items():
                pilots[name] = Pilot(
                    name=p["name"],
                    channel=p.get("channel"),
                    frequency=p.get("frequency"),
                    created_by=p.get("created_by", "self"),
                    updated_at=p.get("updated_at", 0.0),
                    ip_address=p.get("ip_address")
                )
            locked_channels = set(data.get("locked_channels", []))
    except Exception as e:
        print(f"Error loading persistence: {e}")


def check_ip_limit(name: str, client_ip: Optional[str]) -> None:
    if not client_ip:
        return
    # Check if this IP has already registered a DIFFERENT pilot name
    for p in pilots.values():
        if p.ip_address == client_ip and p.name != name:
            raise HTTPException(
                status_code=403,
                detail=f"Registration denied: Only 1 pilot per device/IP allowed (already occupied by '{p.name}')."
            )


# Load persistence immediately on module load
load_persistence()


app = FastAPI(title="FPV Frequency Manager", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class JoinRequest(BaseModel):
    name: str


class ChannelRequest(BaseModel):
    name: str
    channel: Optional[str] = None
    force: bool = False


class AdminRequest(BaseModel):
    password: str


class GetConfigRequest(AdminRequest):
    pass


class SaveConfigRequest(AdminRequest):
    yaml_text: str


class AdminPilotRequest(AdminRequest):
    name: str
    channel: Optional[str] = None
    force: bool = True


class AdminUpdatePilotRequest(AdminRequest):
    old_name: str
    name: Optional[str] = None
    channel: Optional[str] = None
    force: bool = True


class AdminChannelRequest(AdminRequest):
    channel: str


class BulkImportRequest(AdminRequest):
    text: str
    force: bool = True


def normalize_name(name: str) -> str:
    return " ".join(str(name).strip().split())[:40]


def normalize_channel(channel: Optional[str]) -> Optional[str]:
    if channel is None:
        return None
    ch = str(channel).strip().upper()
    return ch or None


def server_url() -> str:
    host = PUBLIC_HOSTNAME.strip() if PUBLIC_HOSTNAME else get_lan_ip()
    scheme = "https" if USE_HTTPS else "http"
    return f"{scheme}://{host}:{PUBLIC_PORT}"


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def make_qr_data_url(url: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def cleanup_old_pilots() -> None:
    if not CLEANUP_ENABLED:
        return
    now = time.time()
    stale = [name for name, p in pilots.items() if p.updated_at and now - p.updated_at > AUTO_CLEANUP_SECONDS]
    if stale:
        for name in stale:
            del pilots[name]
        save_persistence()


def conflicts_for(freq: int, ignore_name: Optional[str] = None) -> List[dict]:
    result = []
    for p in pilots.values():
        if ignore_name and p.name == ignore_name:
            continue
        if not p.frequency:
            continue
        diff = abs(freq - p.frequency)
        if diff < YELLOW_SPACING_MHZ:
            result.append({
                "pilot": p.name,
                "channel": p.channel,
                "frequency": p.frequency,
                "diff": diff,
                "severity": "red" if diff < RED_SPACING_MHZ else "yellow",
            })
    return sorted(result, key=lambda x: x["diff"])


def pilot_status(pilot: Pilot) -> dict:
    if not pilot.frequency:
        return {"severity": "none", "conflicts": []}
    c = conflicts_for(pilot.frequency, ignore_name=pilot.name)
    if any(x["severity"] == "red" for x in c):
        sev = "red"
    elif c:
        sev = "yellow"
    else:
        sev = "green"
    return {"severity": sev, "conflicts": c}


def score_channel(freq: int, current_user: Optional[str] = None) -> int:
    active = [p.frequency for p in pilots.values() if p.frequency and p.name != current_user]
    if not active:
        return 1000
    distances = [abs(freq - f) for f in active]
    return min(distances) * 10 + int(sum(distances) / len(distances))


def channel_status(channel: str, current_user: Optional[str] = None) -> dict:
    freq = CHANNELS[channel]
    owner = next((p.name for p in pilots.values() if p.channel == channel), None)
    conflicts = conflicts_for(freq, ignore_name=current_user)
    severity = "red" if any(c["severity"] == "red" for c in conflicts) else "yellow" if conflicts else "green"
    return {
        "name": channel,
        "frequency": freq,
        "group": CHANNEL_TO_GROUP.get(channel, "Other"),
        "owner": owner,
        "locked": channel in locked_channels,
        "severity": severity,
        "conflicts": conflicts,
        "score": score_channel(freq, current_user),
    }


def recommendations(current_user: Optional[str] = None, limit: int = 6) -> List[dict]:
    used = {p.channel for p in pilots.values() if p.channel and p.name != current_user}
    free = []
    for ch, freq in CHANNELS.items():
        if CHANNEL_TO_GROUP.get(ch) not in VISIBLE_GROUPS:
            continue
        if ch in used or ch in locked_channels:
            continue
        status = channel_status(ch, current_user)
        if status["severity"] == "red":
            continue
        free.append(status)
    free.sort(key=lambda x: (-x["score"], x["frequency"], x["name"]))
    return free[:limit]


def grouped_channels(current_user: Optional[str] = None, groups: Optional[List[str]] = None) -> List[dict]:
    group_names = groups or VISIBLE_GROUPS
    result = []
    for group in group_names:
        if group not in ALL_GROUPS:
            continue
        channels = []
        for ch in ALL_GROUPS[group]:
            ch = str(ch).upper()
            if ch in CHANNELS:
                channels.append(channel_status(ch, current_user))
        result.append({"name": group, "channels": channels})
    return result


def pilot_rows() -> List[dict]:
    rows = []
    for p in pilots.values():
        row = asdict(p)
        row.update(pilot_status(p))
        rows.append(row)
    rows.sort(key=lambda p: (p["frequency"] if p["frequency"] is not None else 99999, p["name"].lower()))
    return rows


def get_raw_config_yaml() -> str:
    try:
        if CONFIG_PATH.exists():
            return CONFIG_PATH.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading raw config: {e}")
    return ""


def state(current_user: Optional[str] = None) -> dict:
    cleanup_old_pilots()
    rows = pilot_rows()
    return {
        "version": APP_VERSION,
        "event_name": EVENT_NAME,
        "server_url": server_url(),
        "display_url": f"{server_url()}/display",
        "qr": make_qr_data_url(server_url()),
        "visible_groups": VISIBLE_GROUPS,
        "admin_only_groups": ADMIN_ONLY_GROUPS,
        "channel_groups": grouped_channels(current_user),
        "all_channel_groups": grouped_channels(current_user, list(ALL_GROUPS.keys())),
        "channels_flat": [channel_status(ch, current_user) for ch in sorted(CHANNELS, key=lambda c: (CHANNELS[c], c))],
        "pilots": rows,
        "recommendations": recommendations(current_user),
        "stats": {
            "pilots": len(pilots),
            "used_channels": len([p for p in pilots.values() if p.channel]),
            "conflicts": len([p for p in rows if p["severity"] in ["yellow", "red"]]),
            "locked": len(locked_channels),
        },
        "yellow_spacing_mhz": YELLOW_SPACING_MHZ,
        "red_spacing_mhz": RED_SPACING_MHZ,
    }


async def broadcast() -> None:
    dead = []
    for ws in connections:
        try:
            await ws.send_json({"type": "state", "state": state()})
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


def require_admin(password: str) -> None:
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Incorrect admin password")


def set_pilot_channel(name: str, channel: Optional[str], created_by: str = "self", force: bool = False) -> Optional[dict]:
    ch = normalize_channel(channel)
    if ch is None:
        p = pilots.get(name, Pilot(name=name, created_by=created_by))
        p.channel = None
        p.frequency = None
        p.updated_at = time.time()
        pilots[name] = p
        save_persistence()
        return None
    if ch not in CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {ch}")
    if ch in locked_channels:
        raise HTTPException(status_code=409, detail=f"{ch} is locked")
    owner = next((p.name for p in pilots.values() if p.channel == ch and p.name != name), None)
    if owner:
        raise HTTPException(status_code=409, detail=f"{ch} is already occupied by {owner}")
    freq = CHANNELS[ch]
    conflicts = conflicts_for(freq, ignore_name=name)
    if conflicts and not force:
        return {"needs_confirm": True, "conflicts": conflicts, "channel": ch, "frequency": freq}
    p = pilots.get(name, Pilot(name=name, created_by=created_by))
    p.channel = ch
    p.frequency = freq
    p.created_by = created_by if p.created_by == "self" and created_by != "self" else p.created_by
    p.updated_at = time.time()
    pilots[name] = p
    save_persistence()
    return None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/display", response_class=HTMLResponse)
async def display(request: Request):
    return templates.TemplateResponse(request, "display.html", {"request": request})


@app.get("/sw.js")
async def serve_sw():
    return FileResponse(BASE_DIR / "static/sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(BASE_DIR / "static/manifest.json", media_type="application/json")


@app.get("/api/state")
async def get_state(current_user: Optional[str] = None):
    return state(current_user)


@app.post("/api/join")
async def join(req: JoinRequest, request: Request):
    name = normalize_name(req.name)
    if not name:
        raise HTTPException(status_code=400, detail="Name missing")
    client_ip = request.client.host if request.client else None
    check_ip_limit(name, client_ip)
    if name not in pilots:
        pilots[name] = Pilot(name=name, updated_at=time.time(), ip_address=client_ip)
    else:
        pilots[name].updated_at = time.time()
        if not pilots[name].ip_address:
            pilots[name].ip_address = client_ip
    save_persistence()
    await broadcast()
    return {"ok": True, "name": name, "state": state(name)}


@app.post("/api/select-channel")
async def select_channel(req: ChannelRequest, request: Request):
    name = normalize_name(req.name)
    if not name:
        raise HTTPException(status_code=400, detail="Name missing")
    client_ip = request.client.host if request.client else None
    check_ip_limit(name, client_ip)
    if name not in pilots:
        pilots[name] = Pilot(name=name, updated_at=time.time(), ip_address=client_ip)
    else:
        pilots[name].updated_at = time.time()
        if not pilots[name].ip_address:
            pilots[name].ip_address = client_ip
    maybe = set_pilot_channel(name, req.channel, created_by="self", force=req.force)
    if maybe:
        return {"ok": False, **maybe}
    await broadcast()
    return {"ok": True, "state": state(name)}


@app.post("/api/admin/add-pilot")
async def admin_add_pilot(req: AdminPilotRequest):
    require_admin(req.password)
    name = normalize_name(req.name)
    if not name:
        raise HTTPException(status_code=400, detail="Name missing")
    if name not in pilots:
        pilots[name] = Pilot(name=name, created_by="admin", updated_at=time.time())
    maybe = set_pilot_channel(name, req.channel, created_by="admin", force=req.force)
    if maybe:
        return {"ok": False, **maybe}
    await broadcast()
    return {"ok": True}


@app.post("/api/admin/update-pilot")
async def admin_update_pilot(req: AdminUpdatePilotRequest):
    require_admin(req.password)
    old = normalize_name(req.old_name)
    if old not in pilots:
        raise HTTPException(status_code=404, detail="Pilot not found")
    new = normalize_name(req.name) if req.name is not None else old
    if not new:
        raise HTTPException(status_code=400, detail="Name missing")
    p = pilots.pop(old)
    p.name = new
    p.created_by = p.created_by or "admin"
    pilots[new] = p
    maybe = set_pilot_channel(new, req.channel, created_by="admin", force=req.force)
    if maybe:
        return {"ok": False, **maybe}
    await broadcast()
    return {"ok": True}


@app.post("/api/admin/remove-pilot")
async def admin_remove_pilot(req: AdminPilotRequest):
    require_admin(req.password)
    name = normalize_name(req.name)
    pilots.pop(name, None)
    save_persistence()
    await broadcast()
    return {"ok": True}


@app.post("/api/admin/toggle-lock")
async def admin_toggle_lock(req: AdminChannelRequest):
    require_admin(req.password)
    ch = normalize_channel(req.channel)
    if ch not in CHANNELS:
        raise HTTPException(status_code=400, detail="Unknown channel")
    if ch in locked_channels:
        locked_channels.remove(ch)
    else:
        locked_channels.add(ch)
    save_persistence()
    await broadcast()
    return {"ok": True, "locked": ch in locked_channels}


@app.post("/api/admin/bulk-import")
async def admin_bulk_import(req: BulkImportRequest):
    require_admin(req.password)
    added = []
    errors = []
    for line_no, raw in enumerate(req.text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            name_part, channel_part = [x.strip() for x in line.split(",", 1)]
        else:
            parts = line.split()
            name_part = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
            channel_part = parts[-1] if len(parts) > 1 else ""
        name = normalize_name(name_part)
        ch = normalize_channel(channel_part)
        try:
            if not name:
                raise ValueError("Name missing")
            if name not in pilots:
                pilots[name] = Pilot(name=name, created_by="import", updated_at=time.time())
            set_pilot_channel(name, ch, created_by="import", force=req.force)
            added.append(name)
        except Exception as e:
            errors.append(f"Line {line_no}: {e}")
    save_persistence()
    await broadcast()
    return {"ok": not errors, "added": added, "errors": errors}


@app.post("/api/admin/get-config")
async def admin_get_config(req: GetConfigRequest):
    require_admin(req.password)
    return {"ok": True, "yaml_text": get_raw_config_yaml()}


@app.post("/api/admin/save-config")
async def admin_save_config(req: SaveConfigRequest):
    require_admin(req.password)
    try:
        parsed = yaml.safe_load(req.yaml_text)
        if not isinstance(parsed, dict):
            raise ValueError("YAML must be a dictionary at the top level.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YAML syntax error: {e}")
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            f.write(req.yaml_text)
        reload_config_in_memory(parsed)
        save_persistence()
        await broadcast()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {e}")


@app.post("/api/admin/reset")
async def admin_reset(req: AdminRequest):
    require_admin(req.password)
    pilots.clear()
    locked_channels.clear()
    save_persistence()
    await broadcast()
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    try:
        await websocket.send_json({"type": "state", "state": state()})
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "hello":
                await websocket.send_json({"type": "state", "state": state(msg.get("name"))})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connections:
            connections.remove(websocket)
