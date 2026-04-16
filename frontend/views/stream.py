import streamlit as st
import streamlit.components.v1 as components
from frontend import api_client


def _parse_label(key: str) -> str:
    """Turn 'transcoded/uuid_filename_1280x720.mp4' into 'filename · 1280x720 · mp4'."""
    name  = key.split("/")[-1]
    name  = name.split("_", 1)[-1]
    parts = name.rsplit(".", 1)
    body  = parts[0]
    ext   = parts[1] if len(parts) > 1 else ""
    return f"{body} · {ext}" if ext else body


def _hls_player(url: str, height: int = 480) -> None:
    """Embed an HLS.js player for cross-browser HLS support (Chrome/Firefox/Safari)."""
    html = f"""
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <video id="video" controls style="width:100%;max-height:{height}px;background:#000"></video>
    <script>
      var video = document.getElementById('video');
      var src   = {repr(url)};
      if (Hls.isSupported()) {{
        var hls = new Hls();
        hls.loadSource(src);
        hls.attachMedia(video);
      }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
        video.src = src;
      }}
    </script>
    """
    components.html(html, height=height + 20)


def render() -> None:
    st.title("Stream Video")
    st.caption("Select a transcoded output and play it directly from S3.")

    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("↻ Refresh", use_container_width=True):
            st.rerun()

    st.divider()

    try:
        resp = api_client.get("/videos", timeout=10)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception as exc:
        st.error(f"Could not reach API: {exc}")
        return

    if not videos:
        st.info("No transcoded videos yet. Upload one first.")
        return

    m3u8_files = [v for v in videos if v.endswith(".m3u8")]
    mp4_files  = [v for v in videos if v.endswith((".mp4", ".mov", ".avi"))]
    choices    = m3u8_files if m3u8_files else mp4_files

    # Deduplicate labels so selectbox and reverse-lookup stay consistent
    labels = {}
    seen   = {}
    for key in choices:
        label = _parse_label(key)
        if label in seen:
            label = f"{label} ({key.split('/')[-1]})"
        seen[label] = key
        labels[key] = label

    selected_label = st.selectbox(
        "Select output",
        options=list(labels.values()),
        help="HLS playlists (.m3u8) enable adaptive bitrate streaming",
    )

    selected_key = next((k for k, v in labels.items() if v == selected_label), None)
    if not selected_key:
        st.warning("Could not resolve selected video key.")
        return

    try:
        r = api_client.get("/stream", params={"key": selected_key}, timeout=10)
        r.raise_for_status()
        url = r.json()["url"]
    except Exception as exc:
        st.error(f"Could not generate stream URL: {exc}")
        return

    if selected_key.endswith(".m3u8"):
        _hls_player(url)
    else:
        st.video(url)

    with st.expander("S3 details"):
        st.code(selected_key)
        st.caption("Presigned URL valid for 1 hour")
