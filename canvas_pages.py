import requests
import os
import re

TOKEN = "YOUR TOKEN"
BASE_URL = "https://aui.instructure.com/api/v1"
OUTPUT_DIR = "/Users/______"
COURSES = {
    "name of file": id
}
headers = {"Authorization": f"Bearer {TOKEN}"}

def get_all_pages(url):
    results = []
    while url:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            break
        data = r.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            break
        url = r.links.get("next", {}).get("url")
    return results

def sanitize(name):
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in str(name).strip())

def download_file(url, path):
    r = requests.get(url, headers=headers, stream=True, allow_redirects=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def get_file_info(course_id, file_id):
    for u in [f"{BASE_URL}/courses/{course_id}/files/{file_id}", f"{BASE_URL}/files/{file_id}"]:
        r = requests.get(u, headers=headers)
        if r.status_code == 200:
            return r.json()
    return None

def save_file(course_name, subfolder, file_info, seen):
    fid = file_info["id"]
    if fid in seen:
        return
    seen.add(fid)
    filename = sanitize(file_info["display_name"])
    path = os.path.join(OUTPUT_DIR, course_name, subfolder, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        print(f"Skip: {filename}")
        return
    try:
        download_file(file_info["url"], path)
        print(f"Saved: {filename}")
    except Exception as e:
        print(f"Failed: {filename} — {e}")

for course_name, course_id in COURSES.items():
    seen = set()

    # 1. all files in course (catches files endpoint if enabled)
    files = get_all_pages(f"{BASE_URL}/courses/{course_id}/files?per_page=100")
    for f in files:
        save_file(course_name, "_all_files", f, seen)

    # 2. walk modules
    modules = get_all_pages(f"{BASE_URL}/courses/{course_id}/modules?per_page=100")
    for module in modules:
        module_name = sanitize(module["name"])
        items = get_all_pages(module["items_url"] + "?per_page=100")
        for item in items:
            t = item.get("type")

            if t == "File":
                fid = item.get("content_id")
                info = get_file_info(course_id, fid)
                if info:
                    save_file(course_name, module_name, info, seen)

            elif t == "Page":
                purl = item.get("url")
                if not purl:
                    continue
                page = requests.get(purl, headers=headers).json()
                body = page.get("body", "") or ""
                for fid in set(re.findall(r'/files/(\d+)', body)):
                    info = get_file_info(course_id, fid)
                    if info:
                        save_file(course_name, module_name, info, seen)

            # ExternalUrl / ExternalTool skipped — not hosted on Canvas

print("Done.")