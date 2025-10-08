# Changelog

## 0.1.10 (2025-10-07)

- Updated the screenshot in the `README`.

## 0.1.9 (2025-10-07)

- Reduced the padding of the app to make it smaller. The max width is now `1000px`.
- The function `create_dash_app` has a new parameter `url`.
- The function `create_layout` has a new parameter `url`.
- The function `create_url_layout` has a new parameter `url`.
- Now, when the captions of the YouTube videos are retrieved of the comments of the Reddit thread retrieved succesfully no success message is shown because it was taking a lot of vertical space.
- Added support for passing a YouTube or Reddit URL as an argument to the url2tldr command. When provided, the app launches with the URL input field pre-filled.

## 0.1.8 (2025-10-06)

- New folder `src`.
- New folder `src/url2tldr`.
- Moved the file `app.py` to the folder `src/url2tldr`.
- New file `__init__.py` in the folder `src/url2tldr`.
- New file `pyproject.toml`.
- The file `requirements.txt` is removed because the requirements are now in the file `pyproject.toml`.
- Moved the folder `assets` to the folder `src/url2tldr`.
- Updated the installation text in the `README`.
- Now it is possible to do `pip install .` so that the command `url2tldr` opens the app with a Terminal from anywhere in the computer without `cd` to the directory of the project.

## 0.1.7 (2025-10-05)

- Improved the `README` to make it more explicit that Ollama is integrated in the app.

## 0.1.6 (2025-10-05)

- Shortened the text in the *Generate prompt* button.
- The header of the app is now a link to the github of the project.
- Fixed the height of the main div that was too long.
- New button to copy Ollama's result to the clipboard.
- The triple *list ollama models button* + *choose ollama model dropdown* + *run ollama button* is now centered and the *copy ollama' result to clipboard button* is to the right.
- New spinner running while the Ollama models are being retried.
- New screenshot in the `README`.

## 0.1.5 (2025-10-04)

- New screenshot in the `README`.

## 0.1.4 (2025-10-04)

- Reorganized the header of the app and removed the textual description of the app.
- The generate prompt button is now to the right of the URL.
- The size of the copy to clipboard button is now constant.
- New requirement for the library `ollama`.
- New button *Wake Ollama* to wake up Ollama and list the available models.
- New dropdown for the list of available Ollama models.
- New button *Run Ollama*.
- New text box the the result of Ollama.

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
