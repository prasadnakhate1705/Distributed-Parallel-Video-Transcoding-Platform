import time
import streamlit as st
from frontend import api_client
from frontend.config import FORMATS, RESOLUTIONS, CODECS, MODES

_STATUS_ICON = {
    "PENDING":    "🕐 Pending",
    "PROCESSING": "⚙️ Processing",
    "COMPLETED":  "✅ Completed",
    "FAILED":     "❌ Failed",
}
_TERMINAL = {"COMPLETED", "FAILED"}


def _fetch_job(job_id: str) -> dict | None:
    try:
        resp = api_client.get(f"/jobs/{job_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _show_status(job: dict) -> None:
    status = job.get("Status", "UNKNOWN")
    label = _STATUS_ICON.get(status, status)
    retries = int(job.get("RetryCount", 0))

    cols = st.columns([2, 1, 1, 1])
    cols[0].markdown(f"**{label}**")
    cols[1].caption(f"Mode: {job.get('Mode', '—')}")
    cols[2].caption(f"Retries: {retries}")
    cols[3].caption(f"Created: {job.get('CreatedAt', '')[:10]}")

    if status == "COMPLETED":
        outputs = job.get("Outputs", [])
        if outputs:
            st.markdown("**Outputs ready:**")
            for o in outputs:
                st.success(f"{o['resolution']} · {o['format']} → `{o['hls_key']}`")

    elif status == "FAILED":
        st.error(f"Error: {job.get('LastError', 'Unknown error')}")

    elif status == "PROCESSING":
        duration = job.get("DurationSeconds")
        if duration:
            st.caption(f"Running for {float(duration):.0f}s")


def render() -> None:
    st.title("Upload Video")
    st.caption("Choose your settings, upload a file, and monitor transcoding progress below.")

    st.divider()

    # ── Settings ──────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox(
            "Processing mode",
            MODES,
            format_func=str.capitalize,
            help="Single: sequential on one node. Parallel: distributed across Spark workers.",
        )
        fmt = st.selectbox("Output format", FORMATS)
    with col2:
        codec = st.selectbox(
            "Video codec",
            CODECS,
            help="libx264 is fastest. libx265 / VP9 / AV1 give better compression at higher CPU cost.",
        )
        resolutions = st.multiselect(
            "Output resolutions",
            RESOLUTIONS,
            default=["1280x720"],
            help="Each resolution produces a separate HLS output. Select multiple for an ABR ladder.",
        )

    if not resolutions:
        st.warning("Select at least one resolution.")

    # ── File upload ───────────────────────────────────────────────────────────
    st.divider()
    uploaded = st.file_uploader(
        "Video file",
        type=["mp4", "mov", "avi"],
        label_visibility="collapsed",
    )

    submit_disabled = not (uploaded and resolutions)
    if st.button("Upload & Transcode", type="primary", disabled=submit_disabled):
        with st.spinner("Uploading to S3…"):
            try:
                data = [("mode", mode), ("format", fmt), ("codec", codec)] + \
                       [("resolutions", r) for r in resolutions]
                resp = api_client.post(
                    "/upload",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    data=data,
                    timeout=60,
                )
                if resp.status_code == 202:
                    body = resp.json()
                    st.session_state["tracking_job_id"] = body["job_id"]
                    st.session_state["tracking_done"] = False
                    st.success(f"Queued — Job ID: `{body['job_id']}`")
                else:
                    st.error(f"Upload failed ({resp.status_code}): {resp.text}")
            except Exception as exc:
                st.error(f"Could not reach API: {exc}")

    # ── Live status tracker ───────────────────────────────────────────────────
    job_id = st.session_state.get("tracking_job_id")
    already_done = st.session_state.get("tracking_done", False)

    if job_id:
        st.divider()
        st.subheader("Job Status")

        job = _fetch_job(job_id)
        if job:
            _show_status(job)
            status = job.get("Status", "")
            if status in _TERMINAL:
                st.session_state["tracking_done"] = True
            elif not already_done:
                # Schedule a rerun in 3s to poll again
                time.sleep(3)
                st.rerun()
        else:
            st.warning("Could not fetch job status — API may be unreachable.")

        if st.button("Track a different job", key="reset_tracking"):
            del st.session_state["tracking_job_id"]
            st.session_state["tracking_done"] = False
            st.rerun()
