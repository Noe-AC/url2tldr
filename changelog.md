## 0.1.3 (2025-10-02)

- Added `yt-dlp` in the `README`.

## 0.1.2 (2025-10-02)

- Renamed the function `extract_comments` to `extract_reddit_comments`.
- New function `extract_reddit_metadata`.
- The function `generate_reddit_prompt` has a new parameter `meta` and the generated prompt integrates this metadata.
- The library `yt-dlp` is added in `requirements.txt`.
- New function `fetch_youtube_metadata`.
- The function `generate_youtube_prompt` has a new parameter `meta` and the generated prompt integrates this metadata.
- The callback now integrates the two new functions `extract_reddit_metadata` and `fetch_youtube_metadata`.
- Improved the layout. Now the app is in a rectangle with rounded corners in front of a grey backtround.
- New screenshot shown in the `README`.

## 0.1.1 (2025-10-01)

- Added a `changelog.md`. file.
- Added a `requirements.txt` file.
- Added a `app.py` file with the content of the app.
- Improved the `README.md` file.
- New folder `assets`.
- New file `assets/style.css`.
- New file `assets/favicon.ico`.
- New file `assets/URL2TLDR_1024x1024.png`.
- New folder `screenshots`.
- New file `screenshots/screenshot.png`.
