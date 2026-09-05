# from pathlib import Path
# from playwright.sync_api import sync_playwright

# html_file = Path(r"D:\GX1\generated_ui\BRD_HRM_Employee_Registration.pdf_20260721_203317.html").resolve()

# with sync_playwright() as p:
#     browser = p.chromium.launch()
#     page = browser.new_page()

#     page.goto(f"file:///{html_file.as_posix()}")
#     page.screenshot(path="salary.png", full_page=True)

#     browser.close()

"""
Upload an image into a Penpot file via Penpot's RPC API.

Requirements:
    pip install requests

Setup:
    1. In Penpot, go to Your account > Access tokens > "Generate new token".
       (This requires the server/account to have access tokens enabled.
       On design.penpot.app this is enabled for you already.)
    2. Set the PENPOT_ACCESS_TOKEN and PENPOT_FILE_ID env vars (or edit below).

Notes:
    - Auth uses `Authorization: Token <access_token>` (NOT "Bearer").
    - This uses the "upload from URL" command, which is the simplest path
      when your image already has a public URL (e.g. Cloudinary).
    - If you instead want to upload local bytes, see upload_local_file()
      below, which posts multipart/form-data to create-file-media-object.
    - Exact param names can drift between Penpot versions. If a call fails,
      check https://<your-penpot-host>/api/doc for the live RPC schema
      (requires enable-backend-api-doc on self-hosted instances).
"""

import os
import uuid
import requests
import json

PENPOT_API_URL = os.environ.get("PENPOT_API_URL", "https://design.penpot.app")
PENPOT_ACCESS_TOKEN = os.environ.get("PENPOT_ACCESS_TOKEN", "eyJhbGciOiJBMjU2S1ciLCJlbmMiOiJBMjU2R0NNIn0.mciVK7yfF6VjIa5qGqAnrBZqAY2Q9FRAp2AzNpRr_dkUKTvgM_G3QQ.S5Oxagb6Qy5yMI9S.TSyTUywjSw2EOEnMu7qe8MOPxFBm46m9yMKSPAeuJrhnAkSHkrRsvWAioZlM6i7_FQ5UHW7uqy9DFQleUb7a53TKFU9XvHUgwuYCPJ3ZJu6m3paIPAZoiSxx6HXR0tY65godfoc3xrxnXsEiE5bEqJaCxZpSlULTkL0E4_l5ZKYhnaGjZPBXycTnjbikoFaMGCsClHO01sd3.YQWYz7HKMjaRPWEqIlmAZg")
PENPOT_FILE_ID = os.environ.get("PENPOT_FILE_ID", "")
PENPOT_PROJECT_NAME = os.environ.get("PENPOT_PROJECT_NAME", "API Uploads")
PENPOT_FILE_NAME = os.environ.get("PENPOT_FILE_NAME", "Uploaded via API")
 


IMAGE_URL = "https://res.cloudinary.com/dtkxm4abz/image/upload/v1784722644/gx1_ui_previews/ui_6a60b08002ec028a79d392c9.png"
  
 
def _headers():
    return {
        "Authorization": f"Token {PENPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
 
 
def upload_from_url(file_id: str, image_url: str, name: str = "uploaded-image") -> dict:
    """Upload an image into a Penpot file directly from a public URL."""
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/create-file-media-object-from-url"
    payload = {
        "file-id": file_id,
        "url": image_url,
        "name": name,
        "is-local": True,
    }
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("upload_from_url error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def upload_local_file(file_id: str, local_path: str, name: str = "uploaded-image") -> dict:
    """Upload an image into a Penpot file from local bytes (multipart)."""
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/create-file-media-object"
    headers = {
        "Authorization": f"Token {PENPOT_ACCESS_TOKEN}",
        "Accept": "application/json",
    }
    with open(local_path, "rb") as f:
        files = {"file": (os.path.basename(local_path), f, "image/png")}
        data = {"file-id": file_id, "name": name, "is-local": "true"}
        resp = requests.post(endpoint, headers=headers, data=data, files=files)
    if not resp.ok:
        print("upload_local_file error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def get_default_team_id() -> str:
    """Fetch the account's teams and return the id of the default one."""
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/get-teams"
    resp = requests.post(endpoint, json={}, headers=_headers())
    if not resp.ok:
        print("get-teams error:", resp.status_code, resp.text)
    resp.raise_for_status()
    teams = resp.json()
    if not teams:
        raise RuntimeError("Account has no teams")
    default_team = next((t for t in teams if t.get("is-default")), teams[0])
    return default_team["id"]
 
 
def create_project(name: str, team_id: str | None = None) -> dict:
    """Create a new project inside a team (uses the default team if not given)."""
    if team_id is None:
        team_id = get_default_team_id()
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/create-project"
    payload = {"team-id": team_id, "name": name}
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("create-project error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def create_file(project_id: str, name: str) -> dict:
    """Create a new file inside a project. Returns the file object (includes 'id')."""
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/create-file"
    payload = {"project-id": project_id, "name": name}
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("create-file error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def ensure_file_id() -> str:
    """
    Return PENPOT_FILE_ID if set; otherwise create a fresh project + file
    and return the new file's id. Prints the new id so you can pin it via
    the PENPOT_FILE_ID env var on future runs if you want to reuse the file.
    """
    if PENPOT_FILE_ID:
        return PENPOT_FILE_ID
 
    print(f"No PENPOT_FILE_ID set — creating project '{PENPOT_PROJECT_NAME}'...")
    project = create_project(PENPOT_PROJECT_NAME)
    project_id = project["id"]
 
    print(f"Creating file '{PENPOT_FILE_NAME}' in project {project_id}...")
    file = create_file(project_id, PENPOT_FILE_NAME)
    file_id = file["id"]
 
    print(f"Created file id: {file_id}  (set PENPOT_FILE_ID={file_id} to reuse it)")
    return file_id
 
 
def get_file_data(file_id: str) -> dict:
    """Fetch the full file document (includes revn/vern and page data)."""
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/get-file"
    resp = requests.post(endpoint, json={"id": file_id}, headers=_headers())
    if not resp.ok:
        print("get-file error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def get_file_revn_vern(file_id: str) -> tuple:
    """Fetch the file's current revn and vern (they are tracked independently)."""
    data = get_file_data(file_id)
    return data.get("revn", 0), data.get("vern", 0)
 
 
def get_first_page_id(file_id: str) -> str:
    """Fetch the file's data and return the id of its first page."""
    data = get_file_data(file_id)
    pages = data["data"]["pages"]
    if not pages:
        raise RuntimeError("File has no pages")
    return pages[0]
 
 
def add_media_to_file(file_id: str, media_object: dict) -> dict:
    """
    Register the uploaded media object into the file's media library so it
    shows up as an asset (uses the generic update-file 'add-media' change).
    This does NOT place it on the canvas — see place_image_on_canvas for that.
    """
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/update-file"
    current_revn, current_vern = get_file_revn_vern(file_id)
    payload = {
        "id": file_id,
        "session-id": str(uuid.uuid4()),
        "revn": current_revn,
        "vern": current_vern,
        "changes": [
            {
                "type": "add-media",
                "object": media_object,
            }
        ],
    }
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("update-file (add-media) error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def place_image_on_canvas(
    file_id: str,
    media_object: dict,
    page_id: str | None = None,
    x: float = 0,
    y: float = 0,
    width: float | None = None,
    height: float | None = None,
) -> dict:
    """
    Add an actual image shape onto a page, referencing the already-uploaded
    media_object (the dict returned by upload_from_url / upload_local_file).
 
    If page_id is not given, uses the file's first page.
    """
    if page_id is None:
        page_id = get_first_page_id(file_id)
 
    # The root frame of a page always has this nil-uuid id in Penpot.
    root_frame_id = "00000000-0000-0000-0000-000000000000"
 
    w = width or media_object.get("width", 512)
    h = height or media_object.get("height", 512)
 
    shape_id = str(uuid.uuid4())
    selrect = {"x": x, "y": y, "width": w, "height": h,
               "x1": x, "y1": y, "x2": x + w, "y2": y + h}
    points = [
        {"x": x, "y": y},
        {"x": x + w, "y": y},
        {"x": x + w, "y": y + h},
        {"x": x, "y": y + h},
    ]
 
    obj = {
        "id": shape_id,
        "type": "image",
        "name": media_object.get("name", "image"),
        "page-id": page_id,
        "frame-id": root_frame_id,
        "parent-id": root_frame_id,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "selrect": selrect,
        "points": points,
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
        "transform-inverse": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
        "rotation": 0,
        "proportion": (w / h) if h else 1,
        "proportion-lock": False,
        "metadata": {
            "id": media_object["id"],
            "width": w,
            "height": h,
            "mtype": media_object.get("mtype", "image/png"),
        },
        "fills": [],
    }
 
    current_revn, current_vern = get_file_revn_vern(file_id)
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/update-file"
    payload = {
        "id": file_id,
        "session-id": str(uuid.uuid4()),
        "revn": current_revn,
        "vern": current_vern,
        "changes": [
            {
                "type": "add-obj",
                "id": shape_id,
                "page-id": page_id,
                "frame-id": root_frame_id,
                "parent-id": root_frame_id,
                "obj": obj,
            }
        ],
    }
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("update-file (add-obj) error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
def place_color_rect_on_canvas(
    file_id: str,
    color_hex: str,
    name: str,
    page_id: str | None = None,
    x: float = 0,
    y: float = 0,
    width: float = 100,
    height: float = 100,
) -> dict:
    """Add a colored rectangle shape onto a page representing a design token."""
    if page_id is None:
        page_id = get_first_page_id(file_id)

    root_frame_id = "00000000-0000-0000-0000-000000000000"

    shape_id = str(uuid.uuid4())
    selrect = {"x": x, "y": y, "width": width, "height": height,
               "x1": x, "y1": y, "x2": x + width, "y2": y + height}
    points = [
        {"x": x, "y": y},
        {"x": x + width, "y": y},
        {"x": x + width, "y": y + height},
        {"x": x, "y": y + height},
    ]

    fill = {
        "fill-color": color_hex,
        "fill-opacity": 1.0,
    }

    obj = {
        "id": shape_id,
        "type": "rect",
        "name": name,
        "page-id": page_id,
        "frame-id": root_frame_id,
        "parent-id": root_frame_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "selrect": selrect,
        "points": points,
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
        "transform-inverse": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 0, "f": 0},
        "rotation": 0,
        "proportion": 1.0,
        "proportion-lock": False,
        "fills": [fill],
    }

    current_revn, current_vern = get_file_revn_vern(file_id)
    endpoint = f"{PENPOT_API_URL}/api/rpc/command/update-file"
    payload = {
        "id": file_id,
        "session-id": str(uuid.uuid4()),
        "revn": current_revn,
        "vern": current_vern,
        "changes": [
            {
                "type": "add-obj",
                "id": shape_id,
                "page-id": page_id,
                "frame-id": root_frame_id,
                "parent-id": root_frame_id,
                "obj": obj,
            }
        ],
    }
    resp = requests.post(endpoint, json=payload, headers=_headers())
    if not resp.ok:
        print("update-file (add-obj rect) error:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()
 
 
if __name__ == "__main__":
    if PENPOT_ACCESS_TOKEN == "REPLACE_ME":
        raise SystemExit("Set PENPOT_ACCESS_TOKEN (env var) first.")
 
    file_id = ensure_file_id()  # creates a project+file for you if PENPOT_FILE_ID is unset
 
    print("Uploading image from URL...")
    media_object = upload_from_url(file_id, IMAGE_URL, name="gx1-ui-preview")
    print("Uploaded:", media_object)
 
    print("Registering media object in file library...")
    lib_result = add_media_to_file(file_id, media_object)
    print("Done:", lib_result)
 
    print("Placing 3 images side-by-side on canvas...")
    w = media_object.get("width", 1280)
    spacing = 50
    for i in range(3):
        x_pos = i * (w + spacing)
        print(f"Placing image {i+1} at x={x_pos}...")
        canvas_result = place_image_on_canvas(file_id, media_object, x=x_pos, y=0)
        print(f"Done placing image {i+1}:", canvas_result)

    # Load GX1 color tokens and display them on canvas
    tokens_path = os.path.join(os.path.dirname(__file__), "api", "gx1.json")
    try:
        with open(tokens_path, "r") as f:
            gx1_data = json.load(f)
            colors = gx1_data.get("colors", {})
    except Exception as e:
        print("Error loading gx1.json:", e)
        colors = {
            "brand_green": "#23B14D",
            "action_green": "#0F7A35",
            "brand_yellow": "#FFD500",
            "surface_canvas": "#F7F8F8",
            "text_primary": "#182229",
            "border_resting": "#8F999F",
            "info": "#2563EB",
            "ai_violet": "#6D4AFF",
            "caution": "#D97706",
            "error": "#C62828"
        }

    print("Placing GX1 Design System color tokens on canvas...")
    rect_y = 1200
    rect_size = 100
    rect_spacing = 30
    idx = 0
    for color_name, color_val in colors.items():
        if color_val.startswith("linear-gradient"):
            # Skip complex gradients or handle fallback color
            color_val = "#23B14D"
        rect_x = idx * (rect_size + rect_spacing)
        print(f"Placing token '{color_name}' ({color_val}) at x={rect_x}...")
        place_color_rect_on_canvas(file_id, color_val, f"Token: {color_name}", x=rect_x, y=rect_y, width=rect_size, height=rect_size)
        idx += 1
    print("Done placing design system color tokens.")