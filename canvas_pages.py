import requests
import os
import re
import sys

# ==========================================
# CONFIGURATION
# ==========================================
TOKEN = ""  # Leave blank to be prompted, or paste your token here
BASE_URL = "https://aui.instructure.com/api/v1"
OUTPUT_DIR = "./Canvas_Downloads" # Will create this folder in your current directory

# Add your courses here. Format: {"Folder Name": course_id}
COURSES = {
    "My_Course_Name": 123456
}
# ==========================================

def sanitize(name):
    """Removes illegal characters from folder and file names."""
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in str(name).strip())

def get_all_pages(session, url):
    """Handles Canvas pagination to get all items."""
    results = []
    while url:
        response = session.get(url)
        if response.status_code != 200:
            break
        
        data = response.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            break
            
        # Get the next page URL from the headers
        url = response.links.get("next", {}).get("url")
    return results

def get_file_info(session, course_id, file_id):
    """Fetches metadata for a specific file."""
    urls_to_try = [
        f"{BASE_URL}/courses/{course_id}/files/{file_id}",
        f"{BASE_URL}/files/{file_id}"
    ]
    
    for url in urls_to_try:
        response = session.get(url)
        if response.status_code == 200:
            return response.json()
    return None

def download_file(session, url, path):
    """Streams a file to the local disk."""
    response = session.get(url, stream=True, allow_redirects=True)
    response.raise_for_status()
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk: 
                f.write(chunk)

def save_file(session, course_name, subfolder, file_info, seen):
    """Handles the deduplication and saving of a file."""
    file_id = file_info.get("id")
    
    # Skip if we've already downloaded this file in another module
    if file_id in seen:
        return
    seen.add(file_id)
    
    filename = sanitize(file_info.get("display_name", f"file_{file_id}"))
    path = os.path.join(OUTPUT_DIR, course_name, subfolder, filename)
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    if os.path.exists(path):
        print(f"[-] Skipped (already exists): {filename}")
        return
        
    try:
        print(f"[+] Downloading: {filename} -> {subfolder}/")
        download_file(session, file_info["url"], path)
    except Exception as e:
        print(f"[!] Failed to download {filename}: {e}")

def main():
    global TOKEN
    
    # Interactive prompt if token isn't hardcoded
    if not TOKEN:
        TOKEN = input("Enter your Canvas API Token: ").strip()
        if not TOKEN:
            print("Error: Token is required to access Canvas.")
            sys.exit(1)

    # Initialize a Session for faster, pooled connections
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {TOKEN}"})

    if not COURSES or list(COURSES.values())[0] == 123456:
        print("Please update the COURSES dictionary in the script with your actual course names and IDs.")
        sys.exit(1)

    print(f"Starting download to: {os.path.abspath(OUTPUT_DIR)}\n")

    for course_name, course_id in COURSES.items():
        print(f"=== Processing Course: {course_name} (ID: {course_id}) ===")
        seen_files = set()
        course_folder = sanitize(course_name)

        # 1. PROCESS MODULES FIRST (So files are neatly organized)
        modules_url = f"{BASE_URL}/courses/{course_id}/modules?per_page=100"
        modules = get_all_pages(session, modules_url)
        
        for module in modules:
            module_name = sanitize(module["name"])
            items = get_all_pages(session, module["items_url"] + "?per_page=100")
            
            for item in items:
                item_type = item.get("type")

                # Handle direct files in modules
                if item_type == "File":
                    file_id = item.get("content_id")
                    file_info = get_file_info(session, course_id, file_id)
                    if file_info:
                        save_file(session, course_folder, module_name, file_info, seen_files)

                # Handle files embedded inside Canvas Pages
                elif item_type == "Page":
                    page_url = item.get("url")
                    if not page_url:
                        continue
                    
                    page_data = session.get(page_url).json()
                    body = page_data.get("body", "") or ""
                    
                    # Find all file IDs embedded in the HTML
                    embedded_file_ids = set(re.findall(r'/files/(\d+)', body))
                    for file_id in embedded_file_ids:
                        file_info = get_file_info(session, course_id, file_id)
                        if file_info:
                            save_file(session, course_folder, module_name, file_info, seen_files)

        # 2. CATCH EVERYTHING ELSE
        # Now fetch all files to grab anything that wasn't assigned to a specific module
        print(f"--- Checking for unorganized files in {course_name} ---")
        all_files_url = f"{BASE_URL}/courses/{course_id}/files?per_page=100"
        all_files = get_all_pages(session, all_files_url)
        
        for file_info in all_files:
            save_file(session, course_folder, "_unorganized_files", file_info, seen_files)

        print(f"Finished course: {course_name}\n")

    print("All downloads complete.")

if __name__ == "__main__":
    main()
