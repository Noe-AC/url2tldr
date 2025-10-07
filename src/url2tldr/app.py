"""
URL2TLDR
Noé Aubin-Cadot

Steps to use the app:
1. Install :
    pip install -e .
2. Run the app:
    url2tldr
A web browser should open with the app at:
    http://127.0.0.1:8050/
"""

################################################################################
################################################################################
# Import libraries

import dash
from dash import Dash, html, dcc, Input, Output, State
import dash_bootstrap_components as dbc
import requests
import pandas as pd
import re
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import subprocess # To wake up Ollama
import ollama
import webbrowser
import os

TEXTBOX_HEIGHT = "250px"
SPINNER_TYPE = "dot"

################################################################################
################################################################################
# Reddit utility functions

def fetch_reddit_json(
    url: str,
) -> dict:
    """
    Convert a Reddit URL to its JSON endpoint and fetch the JSON data.

    Args:
        url (str): Reddit thread URL.

    Returns:
        dict: Parsed JSON data if successful.

    Raises:
        RuntimeError: If the HTTP request fails.
    """
    reddit_json_url = url.rstrip("/") + ".json"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; my-script/1.0)"}

    try:
        response = requests.get(reddit_json_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            raise RuntimeError(f"HTTP error {response.status_code} for URL {reddit_json_url}")
    except Exception as e:
        raise RuntimeError(f"Could not fetch Reddit JSON: {e}")

def extract_reddit_metadata(
    data: dict,
) -> dict:
    """
    Extract basic metadata (title, subreddit, author, url) from Reddit JSON.

    Args:
        data (dict): JSON data from Reddit.

    Returns:
        dict: Metadata including title, subreddit, author, and permalink.
    """
    try:
        post_data = data[0]["data"]["children"][0]["data"]
        return {
            "title": post_data.get("title"),
            "subreddit": post_data.get("subreddit"),
            "author": post_data.get("author"),
            "score": post_data.get("score"),
            "num_comments": post_data.get("num_comments"),
            "permalink": "https://www.reddit.com" + post_data.get("permalink", "")
        }
    except Exception as e:
        raise RuntimeError(f"Could not extract metadata: {e}")

def extract_reddit_comments(
    data: dict,
) -> pd.DataFrame:
    """
    Flatten Reddit comments into a pandas DataFrame.

    Args:
        data (dict): JSON data from Reddit.

    Returns:
        pd.DataFrame: Flattened and filtered comments.
    """
    comments_data = []

    def recurse(children):
        for c in children:
            kind = c.get("kind")
            c_data = c.get("data", {})
            if kind == "t1":  # comment
                comments_data.append({
                    "author": c_data.get("author"),
                    "body": c_data.get("body"),
                    "score": c_data.get("score"),
                    "created_utc": c_data.get("created_utc"),
                    "id": c_data.get("id"),
                    "parent_id": c_data.get("parent_id")
                })
                replies = c_data.get("replies")
                if replies and isinstance(replies, dict):
                    recurse(replies["data"]["children"])

    root_comments = data[1]["data"]["children"]
    recurse(root_comments)
    df = pd.DataFrame(comments_data)

    # Clean up
    df = df[df["body"].str.len() > 10]  # remove very short comments
    df = df[df["score"] >= 1]  # remove low-score comments
    if not df.empty:
        link_id = df["parent_id"].iloc[0]
        df = df[df["parent_id"] == link_id]  # keep top-level comments
    df = df[~df["body"].str.contains(r"!\[img\]\(emote\|", regex=True)]  # remove image emotes
    df.sort_values(by="score", ascending=False, inplace=True)

    return df

def generate_reddit_prompt(
    meta: dict,
    df: pd.DataFrame,
) -> str:
    """
    Generate a structured TL;DR prompt from all Reddit comments
    and thread metadata.

    Args:
        meta (dict): Metadata with keys like title, subreddit, author, etc.
        df (pd.DataFrame): Flattened Reddit comments.

    Returns:N
        str: Prompt ready to paste into a LLM.
    """
    if df.empty:
        return "No relevant comments found."

    # Include all comments (already filtered in extract_comments)
    text = "\n".join(
        #f"- {row['author']}: {row['body']}"
        f"- {row['body']}"
        for _, row in df.iterrows()
    )

    # Thread context
    thread_info = (
        f"Subreddit: r/{meta.get('subreddit', 'unknown')}\n"
        f"Title: {meta.get('title', 'Untitled')}\n"
        f"Author: {meta.get('author', 'unknown')}\n"
        f"Post score: {meta.get('score', 'N/A')} | "
        f"Comments: {meta.get('num_comments', 'N/A')}\n"
        f"URL: {meta.get('permalink', '')}\n"
    )

    prompt = (
        "You are an assistant that summarizes Reddit discussions.\n"
        "Please analyze the following thread and provide a concise summary:\n"
        "- Only include the most relevant information and opinions.\n"
        "- Format your output as clear bullet points.\n"
        "- Avoid unnecessary repetition or minor details.\n\n"
        "Thread information:\n"
        f"{thread_info}\n"
        "Reddit comments:\n\n"
        f"{text}"
    )

    # Cap at ~100k chars to avoid excessive token length
    return prompt[:100000]

################################################################################
################################################################################
# YouTube utility functions

def extract_youtube_id(
    url: str,
) -> str:
    """
    Extract the video ID from a YouTube URL.

    Args:
        url (str): YouTube video URL.

    Returns:
        str: Video ID if found, else empty string.
    """
    # Support formats like:
    # https://www.youtube.com/watch?v=VIDEOID
    # https://youtu.be/VIDEOID
    # https://www.youtube.com/embed/VIDEOID
    regex_patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
    ]
    for pattern in regex_patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

def fetch_youtube_metadata(
    video_id: str,
) -> dict:
    """
    Fetch metadata for a given YouTube video using yt_dlp.

    Args:
        video_id (str): The unique identifier of the YouTube video (e.g. "yHnVGosfKM8").

    Returns:
        dict: A dictionary containing the following keys:
            - title (str): Title of the video
            - channel (str): Name of the uploader/channel
            - url (str): Full YouTube URL of the video
            - length_seconds (int): Duration of the video in seconds
            - publish_date (str): Upload date in YYYYMMDD format
            - views (int): View count
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {"quiet": True, "skip_download": True}
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    return {
        "title": info.get("title"),
        "channel": info.get("uploader"),
        "url": url,
        "length_seconds": info.get("duration"),
        "publish_date": info.get("upload_date"),
        "views": info.get("view_count"),
    }

def fetch_youtube_transcript(
    video_id: str,
) -> list[dict]:
    """
    Fetch the transcript for a YouTube video and return as a list of dicts.

    Each dict has keys: 'text', 'start', 'duration'.
    """
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        available_languages = [t.language_code for t in transcript_list]

        fetched_transcript = YouTubeTranscriptApi().fetch(video_id, languages=available_languages)

        # Convert FetchedTranscriptSnippet -> dict
        transcript = [
            {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
            for snippet in fetched_transcript.snippets
        ]

        return transcript

    except Exception as e:
        raise RuntimeError(f"Could not fetch YouTube transcript: {e}")

def generate_youtube_prompt(
    meta: dict,
    transcript: list,
) -> str:
    """
    Generate a summarization prompt for a YouTube video.

    Args:
        meta (dict): Metadata dictionary as returned by `fetch_youtube_metadata`.
        transcript (list): List of transcript entries.

    Returns:
        str: Prompt ready for a LLM.
    """
    if not transcript:
        return "No transcript available."

    # Combine all text
    text = " ".join(entry["text"] for entry in transcript)

    # Create the prompt
    prompt = (
        f"You are an assistant that summarizes YouTube videos.\n"
        f"Please read the following transcript and provide a concise summary:\n"
        f"- Only include the most relevant information and insights.\n"
        f"- Format your output as clear bullet points.\n"
        f"- Avoid unnecessary repetition or minor details.\n\n"
        f"Video information:\n"
        f"- Title: {meta['title']}\n"
        f"- Channel: {meta['channel']}\n"
        f"- URL: {meta['url']}\n"
        f"- Length (seconds): {meta['length_seconds']}\n"
        f"- Publish date: {meta['publish_date']}\n"
        f"- Views: {meta['views']}\n\n"
        f"Transcript:\n\n"
        f"{text}"
    )
    # Truncate if needed then return the prompt
    return prompt[:100000]

################################################################################
################################################################################
# Ollama utilities

def get_ollama_list():
    # Exécute la commande
    result = subprocess.run(
        ["ollama", "list"],
        capture_output = True,
        text           = True,
        check          = True,
    )
    
    # Sépare les lignes
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return pd.DataFrame()
    
    # Première ligne = en-têtes
    headers = re.split(r"\s{2,}", lines[0].strip())
    
    # Les lignes suivantes = données
    data = [re.split(r"\s{2,}", line.strip()) for line in lines[1:]]
    
    # Conversion en DataFrame
    df = pd.DataFrame(data, columns=headers)
    
    return df

################################################################################
################################################################################
# Create the layout of the app

def create_header():
    return html.A(
        href="https://github.com/Noe-AC/url2tldr",
        target="_blank",  # ouvre dans un nouvel onglet
        children=[
            html.Img(
                src="/assets/URL2TLDR_1024x1024.png",
                style={
                    "height": "40px",
                    "width": "40px",
                    "marginRight": "10px",
                    "display": "block",
                },
            ),
            html.H1(
                "URL2TLDR",
                style={
                    "fontSize": "24px",
                    "margin": 0,
                    "lineHeight": "40px",
                    "fontWeight": "600",
                },
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "marginBottom": "20px",
            "gap": "10px",
            "padding": "0",
            "textDecoration": "none",  # retire le soulignement
            "color": "inherit",         # garde la couleur du texte
            "cursor": "pointer",        # curseur main au survol
        },
    )

def create_url_layout():
    return html.Div(
        children=[
            dcc.Input(
                id          = "url-input",
                type        = "text",
                placeholder = "Paste YouTube or Reddit URL here...",
                value       = "",
                style       = {
                    "flex": "1",
                    "marginRight": "10px",
                    "height": "40px",
                    "padding": "0 10px",
                    "fontSize": "16px",
                    "border": "2px solid #0d6efd",  # contour plus visible (bleu)
                    "borderRadius": "5px",          # coins arrondis
                    "outline": "none",              # supprime le contour par défaut au focus
                },
            ),
            dbc.Button(
                "Generate prompt",
                id="generate-btn",
                color="primary",
                style={
                    "height": "40px",     # même hauteur que l'input
                    "flexShrink": 0,      # ne rétrécit pas si l'espace diminue
                },
            ),
        ],
        style={
            "display": "flex",
            "flexDirection": "row",
            "width": "100%",           # container prend toute la largeur
            "marginBottom": "10px",
        }
    )

def create_mid_buttons_layout():
    return html.Div(
        children=[
            html.Div(
                dcc.Clipboard(
                    id="prompt-to-clipboard-btn",
                    target_id="prompt-output",
                    title="Copy the prompt to the clipboard",
                    style={
                        "backgroundColor": "#0d6efd",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "5px",
                        "cursor": "pointer",
                        "display": "inline-block",
                        "width": "38px",
                        "height": "38px",
                        "textAlign": "center",
                        "lineHeight": "36px",
                        "padding": "0",
                    },
                ),
                style={
                    "flex": "0 0 auto",
                },
            ),
            html.Div(
                children=[
                    dbc.Button(
                        "Get Ollama models",
                        id="get-ollama-models-btn",
                        color="primary",
                        style={"marginRight": "10px"},
                    ),
                    dcc.Loading(
                        id="model-dropdown-spinner",
                        type=SPINNER_TYPE,
                        children=[
                            dcc.Dropdown(
                                id          = "model-dropdown",
                                options     = [],
                                value       = None,
                                clearable   = False,
                                placeholder = "Choose Ollama model",
                                style       = {
                                    "width": "200px",
                                    "height": "38px",
                                    "fontSize": "14px",
                                    "marginRight": "10px",
                                    "border": "none",           # désactive le border de react-select
                                    "borderRadius": "5px",
                                    "boxShadow": "0 0 0 2px #0d6efd inset",  # contour bleu
                                },
                            ),
                        ],
                        color="#0d6efd",
                        fullscreen=False
                    ),

                    dbc.Button(
                        "Run Ollama",
                        id="run-ollama-btn",
                        color="primary",
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "flex": "1",  # occupe tout l'espace central
                },
            ),

            html.Div(
                dcc.Clipboard(
                    id="ollama-to-clipboard-btn",
                    target_id="ollama-output",
                    title="Copy Ollama's result to the clipboard",
                    style={
                        "backgroundColor": "#0d6efd",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "5px",
                        "cursor": "pointer",
                        "display": "inline-block",
                        "width": "38px",
                        "height": "38px",
                        "textAlign": "center",
                        "lineHeight": "36px",
                        "padding": "0",
                    },
                ),
                style={"flex": "0 0 auto"},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "marginTop": "10px",
            "marginBottom": "10px",
            "width": "100%",
        },
    )


def create_layout():
    return html.Div(
        children = [
            html.Div(
                children = [
                    create_header(),
                    create_url_layout(),
                    html.Div(
                        id = "status-message",
                        style = {
                            "marginTop": "10px",
                        },
                    ),
                    dcc.Loading(
                        id="prompt-spinner",
                        type=SPINNER_TYPE,
                        children=[
                            dcc.Textarea(
                                value       = "The generated prompt will appear here.",
                                id          = "prompt-output",
                                placeholder = "Please generate a prompt",
                                style       = {
                                    "width": "100%",
                                    "height": TEXTBOX_HEIGHT,
                                    "border": "2px solid #0d6efd",
                                    "borderRadius": "5px",
                                    "outline": "none",
                                },
                                readOnly    = False, # Let the user edit the prompt if needed
                            ),
                        ],
                        color="#0d6efd",
                        fullscreen=False
                    ),
                    
                    create_mid_buttons_layout(),


                    dcc.Loading(
                        id="ollama-spinner",
                        type=SPINNER_TYPE,
                        children=[
                            dcc.Textarea(
                                value       = "Ollama's answer will appear here.",
                                id          = "ollama-output",
                                placeholder = "1. list Ollama models, 2. choose a model, 3. click the blue Run Ollama button",
                                style       = {
                                    "width": "100%",
                                    "height": TEXTBOX_HEIGHT,
                                    "border": "2px solid #0d6efd",
                                    "borderRadius": "5px",
                                    "outline": "none",
                                },
                                readOnly    = False, # Let the user edit the prompt if needed
                            ),
                        ],
                        color="#0d6efd",
                        fullscreen=False
                    ),
                ],
                style = {
                    "backgroundColor": "white",
                    "borderRadius": "15px",
                    "boxShadow": "0px 4px 15px rgba(0,0,0,0.2)",
                    "padding": "30px",
                    #"margin": "40px auto",
                    "boxSizing": "border-box",
                    "height": "auto",
                    "display": "flex",
                    "flexDirection": "column",
                    "justifyContent": "flex-start",
                },
            ),
        ],
        style = {
            "backgroundColor": "#777777",
            "minHeight": "100vh",
            "overflowY": "auto",
            "padding": "40px",
            "display": "block",
        }
    )

################################################################################
################################################################################
# Define the callbacks of the app

def register_callbacks(
    app,
):

    @app.callback(
        Output("prompt-output", "value"),
        Output("status-message", "children"),
        Input("generate-btn", "n_clicks"),
        State("url-input", "value"),
        prevent_initial_call=True,
    )
    def generate_prompt(n_clicks, url):
        if not url:
            return "", dbc.Alert("⚠️ Please enter a URL first.", color="warning")

        # --- Reddit case ---
        if "reddit.com" in url:
            try:
                data = fetch_reddit_json(url)
                if data:
                    # Extract the metadata
                    meta = extract_reddit_metadata(data)
                    # Extract the comments
                    df = extract_reddit_comments(data)
                    try:
                        # Generate the prompt
                        prompt = generate_reddit_prompt(
                            meta = meta,
                            df   = df,
                        )
                        return prompt, dbc.Alert("✅ Reddit prompt generated!", color="success")
                    except Exception as e:
                        return "", dbc.Alert(f"❌ Error generating Reddit prompt: {e}", color="danger")
            except Exception as e:
                return "", dbc.Alert(f"❌ Error fetching Reddit data: {e}", color="danger")

        # --- YouTube case ---
        elif "youtube.com" in url or "youtu.be" in url:
            video_id = extract_youtube_id(url)
            if not video_id:
                return "", dbc.Alert("❌ Could not extract YouTube video ID.", color="danger")
            try:
                # Fetch the metadata
                meta = fetch_youtube_metadata(video_id)
            except Exception as e:
                return "", dbc.Alert(f"❌ Error fetching YouTube metadata: {e}", color="danger")
            try:
                # Fetch the transcript
                transcript = fetch_youtube_transcript(video_id)
            except Exception as e:
                return "", dbc.Alert(f"❌ Error fetching YouTube transcript: {e}", color="danger")

            try:
                prompt = generate_youtube_prompt(
                    meta       = meta,
                    transcript = transcript,
                )
                return prompt, dbc.Alert("✅ YouTube prompt generated!", color="success")
            except Exception as e:
                return "", dbc.Alert(f"❌ Error generating YouTube prompt: {e}", color="danger")

        # --- Unsupported URL ---
        else:
            return "", dbc.Alert("⚠️ Only Reddit or YouTube URLs are supported for now.", color="warning")

    @app.callback(
        Output("model-dropdown", "options"),
        Output("model-dropdown", "value"),  # optionnel : sélectionne la première valeur
        Input("get-ollama-models-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def populate_model_dropdown(n_clicks):
        try:
            df = get_ollama_list()
            if df.empty:
                return [], None

            # Crée les options pour le dropdown
            options = [{"label": name, "value": name} for name in df["NAME"]]

            # Par défaut, on peut sélectionner le premier modèle
            first_value = options[0]["value"] if options else None

            return options, first_value

        except Exception as e:
            print("Erreur en récupérant la liste des modèles :", e)
            return [], None

    @app.callback(
        Output("ollama-output", "value"),
        Input("run-ollama-btn", "n_clicks"),
        State("model-dropdown", "value"),
        State("prompt-output", "value"),
        prevent_initial_call=True
    )
    def run_ollama(
        n_clicks,
        model_name,
        prompt_text,
    ):
        if not prompt_text:
            return "Please enter a prompt."
        if not model_name:
            return "Please list Ollama models then select a model."

        try:
            # Appel du modèle Ollama
            response = ollama.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt_text}]
            )

            # Extraire uniquement le texte
            if hasattr(response, "message") and hasattr(response.message, "content"):
                return response.message.content.strip()
            elif isinstance(response, dict) and "message" in response and "content" in response["message"]:
                return response["message"]["content"].strip()
            else:
                return str(response)

        except Exception as e:
            return f"Error while running Ollama: {e}"

################################################################################
################################################################################
# Create the app

def create_dash_app():

    # Absolute path to the assets folder inside the package
    assets_path = os.path.join(os.path.dirname(__file__), "assets")

    # Instantiate a Dash app
    app = Dash(
        __name__,
        title         = "URL2TLDR",
        assets_folder = assets_path,
        external_stylesheets = [
            dbc.themes.BOOTSTRAP,
        ]
    )

    # Create the layout
    app.layout = create_layout()

    # Register the callbacks
    register_callbacks(
        app = app,
    )

    # Return the app
    return app

################################################################################
################################################################################
# Execute the app

def main(
    turn_off_logs = True,
    open_browser  = True,
    debug         = False,
    use_reloader  = False,
):
    """
    Entry point of the app.
    """

    # Reduce the verbosity of Flask / Dash
    if turn_off_logs:
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    # Create the Dash App
    app = create_dash_app()

    # Open a browser
    if open_browser:
        webbrowser.open("http://127.0.0.1:8050")

    # Run the app
    app.run(
        debug        = debug,
        use_reloader = use_reloader,
        port         = 8050,
    )

if __name__ == "__main__":

    main(
        turn_off_logs = False, # Need logs for dev
        open_browser  = False, # No need to open a browser for dev
        debug         = True,  # Debug for dev
        use_reloader  = True,  # Reload for dev
    )

