"""
URL2TLDR
Noé Aubin-Cadot

Steps to use the app:
1. Create a virtual environment (recommended):
    python3 -m venv venv
2. Activate the virtual environment:
    source venv/bin/activate
3. Install the requirements:
    pip install -r requirements.txt
4. Run the app:
    python app.py
5. Open a browser at:
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
from youtube_transcript_api import YouTubeTranscriptApi

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

def extract_comments(
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
    df: pd.DataFrame,
) -> str:
    """
    Generate a structured TL;DR prompt from a Reddit comments DataFrame.

    Args:
        df (pd.DataFrame): Flattened Reddit comments.

    Returns:
        str: Prompt ready to paste into a LLM.
    """
    if df.empty:
        return "No relevant comments found."
    
    text = "\n".join(df["body"].astype(str))
    
    prompt = (
        "You are an assistant that summarizes Reddit discussions.\n"
        "Please read the following comments from a Reddit thread and provide a concise summary.\n"
        "- Only include the most relevant information and opinions.\n"
        "- Format your output as clear bullet points.\n"
        "- Avoid unnecessary repetition or minor details.\n\n"
        "Reddit comments:\n\n"
        f"{text}"
    )
    
    return prompt[:100000]  # truncate if too long


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
    transcript: list,
) -> str:
    """
    Generate a TL;DR prompt from a YouTube transcript.

    Args:
        transcript (list): List of transcript entries.

    Returns:
        str: Prompt ready for a LLM.
    """
    if not transcript:
        return "No transcript available."

    # Combine all text
    text = "".join(entry["text"] for entry in transcript)

    prompt = (
        "You are an assistant that summarizes YouTube videos.\n"
        "Please read the following transcript and provide a concise summary.\n"
        "- Only include the most relevant information and insights.\n"
        "- Format your output as clear bullet points.\n"
        "- Avoid unnecessary repetition or minor details.\n\n"
        "Transcript:\n\n"
        f"{text}"
    )

    return prompt[:100000]  # truncate if too long

################################################################################
################################################################################
# Create the layout of the app

def create_layout():
    return dbc.Container(
        [
            # Header avec icône et titre centrés
            html.Div(
                [
                    html.Img(
                        src="/assets/URL2TLDR_1024x1024.png",
                        style={"height": "50px", "marginRight": "10px"}
                    ),
                    html.H1("URL2TLDR", style={"margin": 0})
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "marginBottom": "20px"
                }
            ),

            html.P(
                "Instant summaries of YouTube videos and Reddit threads. Paste a URL below to get started!",
                style={"textAlign": "center"}
            ),

            dcc.Input(
                id="url-input",
                type="text",
                placeholder="Paste YouTube or Reddit URL here...",
                value="",
                style={"width": "100%", "marginBottom": "10px"}
            ),
            html.Br(),

            dbc.Button("Generate TL;DR Prompt", id="generate-btn", color="primary", className="mb-3"),

            html.Div(id="status-message", style={"marginTop": "10px"}),

            html.H4("Generated TL;DR Prompt"),

            # Spinner autour du textarea
            dcc.Loading(
                id="loading-spinner",
                type="circle",
                children=[
                    dcc.Textarea(
                        id="prompt-output",
                        style={"width": "100%", "height": "300px"},
                        readOnly=True
                    ),
                    html.Br(),
                    dcc.Clipboard(
                        id="copy-btn",
                        target_id="prompt-output",
                        title="Click to copy the prompt to clipboard",
                        content="📋 Copy Prompt to Clipboard",
                        style={
                            "marginTop": "10px",
                            "backgroundColor": "#0d6efd",
                            "color": "white",
                            "border": "none",
                            "padding": "5px 10px",
                            "borderRadius": "5px",
                            "cursor": "pointer",
                            "display": "none"
                        },
                    )
                ],
                color="#0d6efd",
                fullscreen=False
            )
        ],
        fluid=True
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
        prevent_initial_call=True
    )
    def generate_prompt(n_clicks, url):
        if not url:
            return "", dbc.Alert("⚠️ Please enter a URL first.", color="warning")

        # --- Reddit case ---
        if "reddit.com" in url:
            try:
                data = fetch_reddit_json(url)
                if data:
                    df = extract_comments(data)
                    try:
                        prompt = generate_reddit_prompt(df)
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
                transcript = fetch_youtube_transcript(video_id)
            except Exception as e:
                return "", dbc.Alert(f"❌ Error fetching YouTube transcript: {e}", color="danger")

            try:
                prompt = generate_youtube_prompt(transcript)
                return prompt, dbc.Alert("✅ YouTube prompt generated!", color="success")
            except Exception as e:
                return "", dbc.Alert(f"❌ Error generating YouTube prompt: {e}", color="danger")

        # --- Unsupported URL ---
        else:
            return "", dbc.Alert("⚠️ Only Reddit or YouTube URLs are supported for now.", color="warning")


    @app.callback(
        Output("copy-btn", "style"),
        Input("prompt-output", "value")
    )
    def toggle_copy_button(prompt_text):
        base_style = {
            "marginTop": "10px",
            "backgroundColor": "#0d6efd",
            "color": "white",
            "border": "none",
            "padding": "5px 10px",
            "borderRadius": "5px",
            "cursor": "pointer",
        }
        if prompt_text and prompt_text.strip():
            base_style["display"] = "inline-block"
        else:
            base_style["display"] = "none"
        return base_style

################################################################################
################################################################################
# Create the app

def create_dash_app():

    # Instantiate a Dash app
    app = Dash(
        __name__,
        title         = "URL2TLDR",
        assets_folder = "assets",
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

def main():

    # Create the Dash App
    app = create_dash_app()

    # Run the app
    debug        = True
    use_reloader = True
    app.run(
        debug        = debug,
        use_reloader = use_reloader,
    )

if __name__ == "__main__":
    main()
