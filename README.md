# Canvas download courses

Script pulls all files from Canvas courses. Grabs files endpoint + walks modules.

## What it does

- Loops through course list
- Downloads every file it can find
- Organizes into folders: `course_name/module_name/file`
- Skips duplicates (by file ID + existing path)
- Handles paginated Canvas API responses

## Setup

1. Get Canvas API token: Account → Settings → New Access Token
2. Fill in `TOKEN`
3. Set `OUTPUT_DIR` to where you want files saved
4. Fill `COURSES` dict: `{"folder_name": course_id}`

```python
COURSES = {
    "Calculus": 12345,
    "Computers and algo": 67890,
}
```

## Run

```bash
pip install requests
python canvas_downloader.py
```

## Output structure

```
OUTPUT_DIR/
  Calculus/
    _all_files/
    Week 1 Module/
    Week 2 Module/
  Computers and algo/
    ...
```

## Notes

- Skips ExternalUrl / ExternalTool items, not hosted on Canvas, can't download
- Safe to re-run, won't re-download existing files
- Filenames sanitized
- Needs valid token + course access permissions
