import re
import os
import sys
import requests
from html import unescape

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ==========================================
# CONFIGURATION
# ==========================================
TOKEN = ""  # paste your token here
BASE_URL = "https://aui.instructure.com/api/v1"
OUTPUT_DIR = "./Canvas_Downloads" # Will create this folder in your current directory

# Add your courses here. Format: {"Folder Name": course_id}
COURSES = {
    "My_Course_Name": 123456
}
# ==========================================


def sanitize(name):
    """Removes illegal characters from folder and file names."""
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", str(name).strip())
    return clean_name or "untitled"


def html_to_text(html_content):
    """Converts HTML content into clean readable plain text with preserved Markdown links."""
    if not html_content:
        return ""

    if BeautifulSoup:
        soup = BeautifulSoup(html_content, "html.parser")
        for a in soup.find_all('a', href=True):
            link_text = a.get_text(strip=True) or a['href']
            a.replace_with(f" [{link_text}]({a['href']}) ")
        for img in soup.find_all('img'):
            src = img.get('src', '')
            alt = img.get('alt', 'Image')
            if src:
                img.replace_with(f" ![Image: {alt}]({src}) ")
        text = soup.get_text()
    else:
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r' \2 (\1) ', html_content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        text = unescape(text)

    lines = [line.strip() for line in text.splitlines()]
    return '\n'.join(line for line in lines if line)


def get_all_pages(session, url):
    """Handles Canvas API pagination to fetch all items."""
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
        url = response.links.get("next", {}).get("url")
    return results


def get_file_info(session, course_id, file_id):
    """Fetches metadata for a specific Canvas file."""
    urls_to_try = [
        f"{BASE_URL}/courses/{course_id}/files/{file_id}",
        f"{BASE_URL}/files/{file_id}"
    ]
    for url in urls_to_try:
        response = session.get(url)
        if response.status_code == 200:
            return response.json()
    return None


def download_file(session, url, destination_path):
    """Streams large files (videos, PDFs, zip) directly to disk."""
    response = session.get(url, stream=True, allow_redirects=True)
    response.raise_for_status()
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    with open(destination_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def save_file(session, course_folder, subfolder, file_info, seen):
    """Handles file deduplication and file downloading."""
    file_id = file_info.get("id")
    if file_id in seen:
        return
    seen.add(file_id)

    filename = sanitize(file_info.get("display_name", f"file_{file_id}"))
    file_url = file_info.get("url")
    if not file_url:
        return

    path = os.path.join(OUTPUT_DIR, course_folder, subfolder, filename)

    if os.path.exists(path):
        print(f"  [-] Skipped (already exists): {filename}")
        return

    try:
        print(f"  [+] Downloading File/Video: {filename} -> {subfolder}/")
        download_file(session, file_url, path)
    except Exception as e:
        print(f"  [!] Failed to download {filename}: {e}")


def save_text_file(course_folder, subfolder, title, content):
    """Saves text content into a .txt file."""
    filename = sanitize(f"{title}.txt")
    path = os.path.join(OUTPUT_DIR, course_folder, subfolder, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        return

    print(f"  [+] Writing Text Document: {filename} -> {subfolder}/")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_and_download_embedded_media(session, course_id, course_folder, subfolder, body_html, seen):
    """Extracts direct file downloads, video links, and iframe embeds in Canvas HTML content."""
    if not body_html:
        return

    # 1. Canvas File IDs
    embedded_file_ids = set(re.findall(r'/files/(\d+)', body_html))
    for file_id in embedded_file_ids:
        file_info = get_file_info(session, course_id, file_id)
        if file_info:
            save_file(session, course_folder, subfolder, file_info, seen)

    # 2. Direct Video/Audio Source URLs (.mp4, .webm, .m4v, .mov, .mp3, etc.)
    media_urls = re.findall(r'src=["\'](https?://[^"\']+\.(?:mp4|webm|ogg|mov|m4v|mp3|wav)[^"\']*)["\']', body_html, re.IGNORECASE)
    for media_url in set(media_urls):
        media_name = sanitize(media_url.split("/")[-1].split("?")[0])
        path = os.path.join(OUTPUT_DIR, course_folder, subfolder, media_name)
        if not os.path.exists(path):
            try:
                print(f"  [+] Downloading Direct Video Media: {media_name}")
                download_file(session, media_url, path)
            except Exception as e:
                print(f"  [!] Failed to download media link {media_url}: {e}")

    # 3. Stream / External Embedded Videos (Kaltura, Panopto, YouTube, Canvas Studio)
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', body_html, re.IGNORECASE)
    if iframes:
        external_links = "\n".join([f"- {url}" for url in set(iframes)])
        save_text_file(
            course_folder, 
            subfolder, 
            "_embedded_video_links", 
            f"Embedded Video/Stream Links found:\n\n{external_links}"
        )


def process_media_objects(session, course_id, course_folder, seen):
    """Fetches Canvas native media objects (uploaded via media tool)."""
    media_url = f"{BASE_URL}/courses/{course_id}/media_objects"
    media_list = get_all_pages(session, media_url)

    for media in media_list:
        media_id = media.get("media_id") or media.get("id")
        title = sanitize(media.get("title") or media.get("display_name") or f"video_{media_id}")
        
        # Check available media tracks / download URLs
        sources = media.get("media_sources", [])
        for src in sources:
            src_url = src.get("url")
            ext = src.get("fileext", "mp4")
            if src_url:
                filename = f"{title}.{ext}"
                path = os.path.join(OUTPUT_DIR, course_folder, "Media_Videos", filename)
                if not os.path.exists(path) and media_id not in seen:
                    seen.add(media_id)
                    try:
                        print(f"  [+] Downloading Canvas Media Object: {filename}")
                        download_file(session, src_url, path)
                    except Exception as e:
                        print(f"  [!] Failed to download Canvas media {filename}: {e}")


def process_discussions(session, course_id, course_folder, seen):
    """Downloads all discussion topics and reply threads into text files."""
    discussions_url = f"{BASE_URL}/courses/{course_id}/discussion_topics?per_page=100"
    topics = get_all_pages(session, discussions_url)

    for topic in topics:
        topic_id = topic["id"]
        title = topic.get("title", f"Discussion_{topic_id}")
        raw_message = topic.get("message", "")
        message = html_to_text(raw_message)
        user = topic.get("user_name", "Unknown")
        posted_at = topic.get("posted_at", "")

        content = f"Title: {title}\nAuthor: {user}\nDate: {posted_at}\n"
        content += "=" * 50 + "\n\n"
        content += f"{message}\n\n"
        content += "=" * 50 + "\nREPLIES:\n" + "=" * 50 + "\n\n"

        extract_and_download_embedded_media(session, course_id, course_folder, "Discussions", raw_message, seen)

        view_url = f"{BASE_URL}/courses/{course_id}/discussion_topics/{topic_id}/view"
        resp = session.get(view_url)
        if resp.status_code == 200:
            view_data = resp.json()
            participants = {p["id"]: p.get("display_name", "Unknown") for p in view_data.get("participants", [])}
            
            def parse_entries(entries, indent=0):
                text_out = ""
                for entry in entries:
                    author_id = entry.get("user_id")
                    author = participants.get(author_id, "Unknown")
                    created = entry.get("created_at", "")
                    entry_html = entry.get("message", "")
                    entry_text = html_to_text(entry_html)
                    
                    extract_and_download_embedded_media(session, course_id, course_folder, "Discussions", entry_html, seen)

                    prefix = "  " * indent
                    text_out += f"{prefix}[{author} - {created}]\n"
                    text_out += f"{prefix}{entry_text}\n"
                    text_out += f"{prefix}{'-' * 30}\n"
                    
                    if "replies" in entry:
                        text_out += parse_entries(entry["replies"], indent + 1)
                return text_out

            content += parse_entries(view_data.get("view", []))

        save_text_file(course_folder, "Discussions", title, content)


def process_assignments(session, course_id, course_folder, seen):
    """Downloads assignment instructions, due dates, points, and embedded media."""
    assignments_url = f"{BASE_URL}/courses/{course_id}/assignments?per_page=100"
    assignments = get_all_pages(session, assignments_url)

    for assignment in assignments:
        title = assignment.get("name", "Untitled Assignment")
        due_at = assignment.get("due_at", "N/A")
        points = assignment.get("points_possible", "N/A")
        raw_description = assignment.get("description", "") or ""
        
        description = html_to_text(raw_description)

        content = f"Assignment: {title}\n"
        content += f"Due Date: {due_at}\n"
        content += f"Points Possible: {points}\n"
        content += "=" * 50 + "\n\n"
        content += f"{description}\n"

        if "rubric" in assignment:
            content += "\n\n" + "=" * 50 + "\nRUBRIC:\n" + "=" * 50 + "\n"
            for criterion in assignment["rubric"]:
                c_title = criterion.get("description", "")
                c_points = criterion.get("points", "")
                content += f"- {c_title} ({c_points} pts)\n"

        save_text_file(course_folder, "Assignments", title, content)
        extract_and_download_embedded_media(session, course_id, course_folder, "Assignments", raw_description, seen)


def main():
    global TOKEN

    if not TOKEN:
        TOKEN = input("Enter your Canvas API Token: ").strip()
        if not TOKEN:
            print("Error: Token is required to access Canvas.")
            sys.exit(1)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {TOKEN}"})

    # Auto-fetch active courses if COURSES dictionary is empty
    if not COURSES:
        print("Fetching enrolled courses...")
        resp = session.get(f"{BASE_URL}/courses?enrollment_state=active")
        if resp.status_code == 200:
            for c in resp.json():
                if "name" in c and "id" in c:
                    COURSES[c["name"]] = c["id"]

    print(f"Starting downloads to: {os.path.abspath(OUTPUT_DIR)}\n")

    for course_name, course_id in COURSES.items():
        print(f"\n=== Processing Course: {course_name} (ID: {course_id}) ===")
        seen_files = set()
        course_folder = sanitize(course_name)

        # 1. PROCESS MODULES
        print(f"--- Fetching Modules for {course_name} ---")
        modules = get_all_pages(session, f"{BASE_URL}/courses/{course_id}/modules?per_page=100")

        for module in modules:
            module_name = sanitize(module["name"])
            items = get_all_pages(session, module["items_url"] + "?per_page=100")

            for item in items:
                item_type = item.get("type")

                if item_type == "File":
                    file_id = item.get("content_id")
                    file_info = get_file_info(session, course_id, file_id)
                    if file_info:
                        save_file(session, course_folder, module_name, file_info, seen_files)

                elif item_type == "Page":
                    page_url = item.get("url")
                    if not page_url:
                        continue
                    
                    page_resp = session.get(f"{BASE_URL}/courses/{course_id}/pages/{page_url}")
                    if page_resp.status_code == 200:
                        page_data = page_resp.json()
                        page_title = page_data.get("title", item.get("title", "Untitled Page"))
                        body_html = page_data.get("body", "") or ""

                        text_content = html_to_text(body_html)
                        if text_content:
                            save_text_file(course_folder, module_name, page_title, text_content)

                        extract_and_download_embedded_media(session, course_id, course_folder, module_name, body_html, seen_files)

        # 2. PROCESS ASSIGNMENTS
        print(f"--- Fetching Assignments for {course_name} ---")
        process_assignments(session, course_id, course_folder, seen_files)

        # 3. PROCESS DISCUSSIONS
        print(f"--- Fetching Discussions for {course_name} ---")
        process_discussions(session, course_id, course_folder, seen_files)

        # 4. PROCESS CANVAS NATIVE MEDIA OBJECTS
        print(f"--- Fetching Canvas Media Objects for {course_name} ---")
        process_media_objects(session, course_id, course_folder, seen_files)

        # 5. UNORGANIZED FILES & VIDEOS
        print(f"--- Checking remaining files in {course_name} ---")
        all_files = get_all_pages(session, f"{BASE_URL}/courses/{course_id}/files?per_page=100")
        for file_info in all_files:
            save_file(session, course_folder, "_unorganized_files", file_info, seen_files)

        print(f"Finished course: {course_name}")

    print("\nAll downloads complete.")


if __name__ == "__main__":
    main()
