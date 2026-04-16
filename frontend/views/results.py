import streamlit as st
import pandas as pd
from frontend import api_client


def _load_jobs() -> list[dict]:
    resp = api_client.get("/jobs", timeout=10)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def render() -> None:
    st.title("Transcoding Results")

    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("↻ Refresh", use_container_width=True):
            st.rerun()

    try:
        jobs = _load_jobs()
    except Exception as exc:
        st.error(f"Could not load jobs: {exc}")
        return

    if not jobs:
        st.info("No jobs found yet. Upload a video to get started.")
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    total    = len(jobs)
    done     = sum(1 for j in jobs if j.get("Status") == "COMPLETED")
    running  = sum(1 for j in jobs if j.get("Status") == "PROCESSING")
    failed   = sum(1 for j in jobs if j.get("Status") == "FAILED")
    pending  = sum(1 for j in jobs if j.get("Status") == "PENDING")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total jobs", total)
    c2.metric("Completed", done)
    c3.metric("Processing", running)
    c4.metric("Pending", pending)
    c5.metric("Failed", failed)

    st.divider()

    # ── Single vs Parallel comparison ────────────────────────────────────────
    completed = [j for j in jobs if j.get("Status") == "COMPLETED" and j.get("Mode") and j.get("DurationSeconds")]

    if completed:
        st.subheader("Single vs. Parallel — transcoding time")

        df = pd.DataFrame([
            {
                "Name":     j.get("Name", ""),
                "Mode":     j.get("Mode", ""),
                "Duration": _safe_float(j.get("DurationSeconds")),
                "Outputs":  len(j.get("Outputs", [])),
            }
            for j in completed
        ])

        names = sorted(df["Name"].unique())
        selected = st.selectbox("Select video to compare", names)
        subset = df[df["Name"] == selected]
        pivot = subset.groupby("Mode")["Duration"].mean()

        col1, col2 = st.columns([3, 1])
        with col1:
            st.bar_chart(pivot, y_label="Seconds", x_label="Mode")
        with col2:
            single_t   = pivot.get("Single", 0)
            parallel_t = pivot.get("Parallel", 0)
            st.metric("Single (avg)", f"{single_t:.1f}s")
            st.metric("Parallel (avg)", f"{parallel_t:.1f}s")
            if single_t > 0 and parallel_t > 0:
                st.metric("Speedup", f"{single_t / parallel_t:.2f}×", delta="faster")

        st.divider()

    # ── Job list ──────────────────────────────────────────────────────────────
    st.subheader("All jobs")

    status_filter = st.selectbox(
        "Filter by status",
        ["All", "COMPLETED", "PROCESSING", "PENDING", "FAILED"],
        label_visibility="collapsed",
    )

    visible = jobs if status_filter == "All" else [j for j in jobs if j.get("Status") == status_filter]
    visible = sorted(visible, key=lambda j: j.get("CreatedAt", ""), reverse=True)

    _ICON = {"COMPLETED": "✅", "PROCESSING": "⚙️", "PENDING": "🕐", "FAILED": "❌"}

    for job in visible:
        status  = job.get("Status", "UNKNOWN")
        icon    = _ICON.get(status, "❓")
        name    = job.get("Name", job["JobId"])
        mode    = job.get("Mode", "—")
        created = job.get("CreatedAt", "")[:10]
        dur     = f"{_safe_float(job.get('DurationSeconds')):.1f}s" if job.get("DurationSeconds") else "—"
        retries = int(job.get("RetryCount", 0))

        with st.expander(f"{icon} {name}  ·  {mode}  ·  {dur}  ·  {created}"):
            col1, col2 = st.columns(2)
            with col1:
                st.caption("Job ID")
                st.code(job["JobId"], language=None)
            with col2:
                renditions = job.get("Renditions", [])
                st.caption(f"Requested renditions ({len(renditions)})")
                for r in renditions:
                    st.write(f"• {r['resolution']} · {r['format']} · {r['codec']}")

            outputs = job.get("Outputs", [])
            if outputs:
                st.caption(f"Completed outputs ({len(outputs)})")
                st.dataframe(
                    pd.DataFrame([
                        {"Resolution": o.get("resolution"), "Format": o.get("format"), "HLS Key": o.get("hls_key")}
                        for o in outputs
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )

            if retries:
                st.warning(f"Retried {retries} time(s)")
            if job.get("LastError"):
                st.error(job["LastError"])
