import streamlit as st


def render() -> None:
    st.title("🎬 Transcodify")
    st.markdown("#### Cloud-native distributed video transcoding on Apache Spark")
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("##### 📤 Upload")
        st.write("Upload any MP4, MOV, or AVI. Choose output format, codec, and one or more resolutions.")
    with col2:
        st.markdown("##### ⚙️ Transcode")
        st.write("Jobs run on a Spark cluster across multiple EC2 nodes. Single-node mode available for comparison.")
    with col3:
        st.markdown("##### ▶️ Stream")
        st.write("Outputs are packaged as HLS and streamed directly from S3 with adaptive bitrate support.")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Supported codecs**")
        st.code("H.264 (libx264)\nH.265 (libx265)\nVP9 (libvpx-vp9)\nAV1 (libaom-av1)")
    with col_b:
        st.markdown("**Output resolutions**")
        st.code("360p  (640×360)\n720p  (1280×720)\n1080p (1920×1080)\n4K    (3840×2160)")

    st.divider()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Get Started →", type="primary", use_container_width=True):
            st.session_state.page = "📤  Upload"
            st.rerun()
