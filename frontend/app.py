import streamlit as st

st.set_page_config(
    page_title="Transcodify",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.views import home, upload, stream, results  # noqa: E402 — must follow set_page_config

PAGES = {
    "🏠  Home":    home.render,
    "📤  Upload":  upload.render,
    "▶️  Stream":  stream.render,
    "📊  Results": results.render,
}

if "page" not in st.session_state:
    st.session_state.page = "🏠  Home"

st.sidebar.title("Transcodify")
st.sidebar.caption("Distributed video transcoding")
st.sidebar.divider()

selected = st.sidebar.radio("", list(PAGES.keys()), index=list(PAGES.keys()).index(st.session_state.page))
if selected != st.session_state.page:
    st.session_state.page = selected

st.sidebar.divider()
st.sidebar.caption("Built with Apache Spark · AWS · FFmpeg")

PAGES[st.session_state.page]()
