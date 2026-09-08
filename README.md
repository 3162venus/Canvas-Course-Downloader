# Canvas Course Downloader

A fast, automated script to download and organize all files from your Canvas courses. It walks through your course modules, extracts embedded files from Pages, and neatly organizes everything into folders on your local machine.

## Features

- **Organized Structure:** Saves files directly into their respective `Course/Module/` folders.
- **Smart Fallback:** Any files not attached to a specific module are caught and saved to an `_unorganized_files` folder.
- **Deep Searching:** Extracts and downloads files linked inside Canvas Pages.
- **Fast:** Uses connection pooling (`requests.Session()`) to significantly speed up downloads.
- **Resumable:** Safe to stop and re-run. It checks existing files and skips duplicates (by file ID and path) so you never download the same file twice.
- **Secure:** Prompts for your API token at runtime so you don't have to hardcode your credentials.

## Setup

1. **Get your Canvas API token:** In Canvas, go to Account → Settings → New Access Token.
2. **Set your save location:** Open the script and edit `OUTPUT_DIR` to your preferred download path.
3. **Add your courses:** Find your course IDs in the Canvas URL (e.g., `.../courses/12345`) and update the `COURSES` dictionary in the script:

```python
COURSES = {
    "Calculus": 12345,
    "Computers and algo": 67890,
}
```

## Run

Install the required `requests` library and run the script:

```bash
pip install requests
python canvas_downloader.py
```
*Note: If you leave the `TOKEN` variable blank in the script, it will securely prompt you to paste it in the terminal when you run it.*

## Output Structure

```text
OUTPUT_DIR/
  Calculus/
    Week 1 Module/
      syllabus.pdf
      lecture_slides.pptx
    Week 2 Module/
      homework.docx
    _unorganized_files/
      random_image_from_homepage.png
  Computers and algo/
    ...
```

## Notes

- **External Tools:** Skips `ExternalUrl` and `ExternalTool` items, as these are not hosted on Canvas and cannot be downloaded directly.
- **Sanitization:** Filenames and module names are automatically sanitized to prevent file-system errors with illegal characters.
- **Permissions:** You must have an active enrollment and the necessary permissions in the course to download its files.
