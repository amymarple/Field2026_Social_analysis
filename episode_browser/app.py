"""Selected-episode-centered Streamlit browser for the bounded real route slice."""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from utils import (annotations, coverage, episode_io, load_layout, query,  # noqa: E402
                   video_preview, weather, wiser_tracks)
from utils.evidence import resolve_recording, route_from_episode  # noqa: E402
from utils.selection import build_context  # noqa: E402

MODE = os.environ.get("EPISODE_BROWSER_DATA_MODE", "real").strip().lower()
REAL_STORE = HERE / "data" / "real_episodes_20260630_2100_2115_v2.parquet"
REAL_EVIDENCE = HERE / "data" / "real_wiser_evidence_20260630_2100_2115_v2.parquet"
REAL_MANIFEST = HERE / "data" / "real_slice_manifest_20260630_2100_2115_v2.json"
DEMO_STORE = HERE / "data" / "synthetic_episodes.parquet"
STORE = DEMO_STORE if MODE == "demo" else Path(
    os.environ.get("EPISODE_BROWSER_STORE", REAL_STORE)
)
EVIDENCE_STORE = Path(os.environ.get("EPISODE_BROWSER_WISER_EVIDENCE", REAL_EVIDENCE))
LOCAL_TZ = "America/New_York"
SELECTED_COLOR = "#F4B942"
INK = "#17212B"
MUTED = "#657383"

st.set_page_config(page_title="Episode Browser", page_icon="E", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1rem; padding-bottom: 1.5rem; max-width: 1500px;}
      .app-head {display:flex;align-items:center;gap:12px;border-bottom:1px solid #d7dee7;
                 padding:0 0 10px;margin-bottom:12px;color:#17212b;}
      .app-title {font-size:21px;font-weight:750;letter-spacing:0;}
      .slice-badge {font-size:12px;font-weight:650;background:#eef2f5;color:#334155;
                    border:1px solid #d7dee7;padding:3px 8px;border-radius:4px;}
      .selected-head {border-left:5px solid #f4b942;background:#fffaf0;padding:10px 12px;
                      margin:8px 0 10px;display:flex;gap:14px;align-items:flex-start;}
      .selected-id {font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
                    font-size:15px;font-weight:700;color:#17212b;overflow-wrap:anywhere;}
      .selected-meta {font-size:12px;color:#526171;line-height:1.55;}
      .status-chip {display:inline-block;border:1px solid #d7dee7;border-radius:3px;
                    padding:2px 6px;margin:2px 4px 2px 0;font-size:11px;color:#334155;}
      .warn-chip {border-color:#f0c36a;background:#fff7df;color:#854d0e;}
      .metric-label {font-size:11px;color:#657383;text-transform:uppercase;font-weight:700;}
      .rail-rule {border-top:1px solid #e5e9ef;margin:10px 0;}
      div[data-testid="stDataFrame"] {border:1px solid #d7dee7;}
      div[data-testid="stMetricValue"] {font-size:18px;}
      @media (max-width: 900px) {
        div[data-testid="stHorizontalBlock"] {flex-direction:column;}
        div[data-testid="stColumn"] {width:100% !important;flex:1 1 100% !important;}
        .selected-head {display:block;}
        .selected-meta {margin-top:6px;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_manifest(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@st.cache_data(show_spinner=False)
def load_wiser_evidence(path: str) -> pd.DataFrame:
    p = Path(path)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_weather() -> pd.DataFrame:
    return weather.load_weather()


@st.cache_data(show_spinner=True, max_entries=32)
def cached_frames(path: str, start_s: float, end_s: float, n: int, width: int,
                  mtime: float):
    return video_preview.extract_frames(path, start_s, end_s, n=n, width=width)


def local_time(ms: int, with_date: bool = False) -> str:
    ts = pd.to_datetime(int(ms), unit="ms", utc=True).tz_convert(LOCAL_TZ)
    return ts.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


def local_naive(ms: int) -> pd.Timestamp:
    return pd.to_datetime(int(ms), unit="ms", utc=True).tz_convert(LOCAL_TZ).tz_localize(None)


def subject_text(values, names: dict[str, str]) -> str:
    return ", ".join(names.get(str(value), str(value)) for value in (values or [])) or "unknown"


def episode_subject_text(values, level=None, state_model_id=None) -> str:
    values = [str(value) for value in (values or [])]
    resolved = [names.get(value, value) for value in values]
    if (level == "pair" and state_model_id == "wiser_lagged_path_reuse_v1"
            and len(resolved) >= 2):
        return f"{resolved[0]} -> {resolved[1]}"
    return ", ".join(resolved) or "unknown"


def load_repository() -> episode_io.EpisodeRepository:
    return episode_io.EpisodeRepository(STORE)


repository = load_repository()
if not repository.exists():
    command = ("python build_real_slice.py" if MODE != "demo"
               else "python generate_synthetic_episodes.py")
    st.error(f"Episode store not found: `{STORE}`. Run `{command}` from `episode_browser/`.")
    st.stop()

repository_span = repository.record_span()
if repository_span is None:
    st.error("The configured episode store contains no episodes.")
    st.stop()

manifest = load_manifest(str(REAL_MANIFEST)) if MODE != "demo" else {}
manifest_span = manifest.get("window_utc_ms")
span = (tuple(int(value) for value in manifest_span)
        if isinstance(manifest_span, list) and len(manifest_span) == 2
        else repository_span)
names = load_layout.subject_name_map()
session_index = repository.query_window(*span)
fixes = load_wiser_evidence(str(EVIDENCE_STORE)) if MODE != "demo" else pd.DataFrame()
weather_df = load_weather()

for key, value in {
    "selected_episode_id": None,
    "nav": "Review",
    "session_tag": pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S"),
    "queue_page": 1,
}.items():
    st.session_state.setdefault(key, value)

all_ids = session_index["episode_id"].astype(str).tolist()
default_id = str(manifest.get("default_episode_id") or (all_ids[0] if all_ids else ""))
if st.session_state.selected_episode_id not in all_ids:
    st.session_state.selected_episode_id = default_id

mode_label = "DEMO - synthetic" if MODE == "demo" else "REAL - pre-night-rain integration slice"
st.markdown(
    f"<div class='app-head'><span class='app-title'>Episode Browser</span>"
    f"<span class='slice-badge'>{html.escape(mode_label)}</span>"
    f"<span style='margin-left:auto;font-size:12px;color:#657383'>"
    f"{local_time(span[0], True)}-{local_time(span[1])} EDT</span></div>",
    unsafe_allow_html=True,
)

options = query.available_values(session_index)
with st.sidebar:
    st.radio("View", ["Review", "Video", "Blind evaluation"], key="nav",
             label_visibility="collapsed")
    st.text_input("Annotator ID", key="annotator_id", placeholder="e.g. HC",
                  help="Required for every append-only judgment.")
    st.divider()
    search = st.text_input("Search candidates", placeholder="episode, rat, label, QC flag")
    level_filter = st.multiselect("Levels", options["levels"])
    label_filter = st.multiselect("Labels", options["labels"])
    subject_filter = st.multiselect(
        "Subjects", options["subjects"],
        format_func=lambda value: f"{names.get(str(value), value)} ({value})",
    )
    qc_filter = st.multiselect("QC flags", options["qc_flags"])
    page_size = st.select_slider("Rows per page", [25, 50, 100], value=50)
    st.caption("The queue is bounded to one real 15-minute integration slice.")

filtered = query.text_search(session_index, search, names)
filtered = query.filter_episodes(
    filtered,
    levels=level_filter or None,
    labels=label_filter or None,
    subjects=subject_filter or None,
    qc_flags=qc_filter or None,
)
page_count = max(1, (len(filtered) + page_size - 1) // page_size)
page = min(int(st.session_state.queue_page), page_count)
if page_count > 1:
    page = int(st.number_input("Queue page", 1, page_count, page, key="queue_page"))
start_row = (page - 1) * page_size
page_df = filtered.iloc[start_row:start_row + page_size].copy()


def table_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "Episode ID", "Level", "Animal / roles", "Labels", "Start", "End",
            "Duration", "Model", "QC",
        ])
    return pd.DataFrame({
        "Episode ID": df["episode_id"],
        "Level": df["level"],
        "Animal / roles": df.apply(
            lambda row: episode_subject_text(
                row["subject_ids"], row["level"], row["state_model_id"]
            ), axis=1,
        ),
        "Labels": df["labels"].map(lambda values: ", ".join(values or [])),
        "Start": df["t_start"].map(local_time),
        "End": df["t_end"].map(local_time),
        "Duration": ((df["t_end"] - df["t_start"]) / 1000).map(lambda value: f"{value:.1f}s"),
        "Model": df["state_model_id"],
        "QC": df["qc_flags"].map(lambda values: ", ".join(values or [])),
    })


if st.session_state.nav == "Review":
    queue_head, export_col = st.columns([5, 1])
    queue_head.markdown("### Candidate queue")
    export_frame = table_frame(filtered)
    export_col.download_button(
        "Export CSV",
        export_frame.to_csv(index=False),
        file_name="real_episode_candidates.csv",
        help="Lossy flat export of visible candidate metadata; not a re-import path.",
        use_container_width=True,
    )
    st.caption(
        f"{len(filtered)} of {len(session_index)} candidates. Select one row; rankings do not gate the repository."
    )
    if page_df.empty:
        st.info("No candidates match the current filters. Clear a filter to restore the queue.")
    else:
        event = st.dataframe(
            table_frame(page_df),
            hide_index=True,
            use_container_width=True,
            height=285,
            on_select="rerun",
            selection_mode="single-row",
            key="candidate_queue",
        )
        if event.selection.rows:
            selected = str(page_df.iloc[int(event.selection.rows[0])]["episode_id"])
            st.session_state.selected_episode_id = selected

selected_id = str(st.session_state.selected_episode_id or "")
selected_episode = repository.get_episode(selected_id)
context = build_context(selected_episode, padding_s=5.0)


def selected_header(ctx) -> None:
    if ctx is None:
        st.info("Select an episode from the candidate queue.")
        return
    ep = ctx.episode
    route = route_from_episode(ep)
    qc = ep.get("qc_flags") or []
    outside = selected_id not in set(filtered["episode_id"].astype(str))
    chips = [f"<span class='status-chip'>{html.escape(ep['state_model_id'])}</span>"]
    for label in ep.get("labels") or []:
        chips.append(f"<span class='status-chip'>{html.escape(str(label))}</span>")
    chips.append(f"<span class='status-chip warn-chip'>video {html.escape(route.status)}</span>")
    for flag in qc:
        chips.append(f"<span class='status-chip warn-chip'>{html.escape(str(flag))}</span>")
    if outside:
        chips.append("<span class='status-chip warn-chip'>outside current filters</span>")
    st.markdown(
        "<div class='selected-head'><div><div class='metric-label'>Selected episode</div>"
        f"<div class='selected-id'>{html.escape(ctx.episode_id)}</div></div>"
        f"<div class='selected-meta'><b>{html.escape(episode_subject_text(ep.get('subject_ids'), ep.get('level'), ep.get('state_model_id')))}</b>"
        f" &middot; {local_time(ctx.t_start, True)}-{local_time(ctx.t_end)} EDT"
        f" &middot; {(ctx.t_end - ctx.t_start) / 1000:.1f}s<br>{''.join(chips)}</div></div>",
        unsafe_allow_html=True,
    )


def coverage_chart(summary: coverage.CoverageSummary, subject: str) -> None:
    data_lane = summary.data_availability.get(subject)
    episode_lane = summary.episode_coverage.get(subject)
    if data_lane is None or episode_lane is None:
        st.info("Coverage is unavailable for the selected subject.")
        return
    rows = []
    for label, lane in (("Data availability", data_lane), ("Imported episodes", episode_lane)):
        for interval in lane.intervals:
            status = interval.reason if interval.kind == "gap" else interval.kind
            rows.append({
                "row": label,
                "start_min": (interval.t_start - summary.span[0]) / 60_000,
                "end_min": (interval.t_end - summary.span[0]) / 60_000,
                "status": status,
            })
    chart_df = pd.DataFrame(rows)
    colors = {
        "available": "#2A7F62",
        "tracking_lost": "#B91C1C",
        "no_data": "#6B7280",
        "episode": SELECTED_COLOR,
        "not_represented": "#E5E7EB",
    }
    chart = alt.Chart(chart_df).mark_rect().encode(
        x=alt.X("start_min:Q", title=f"minutes after {local_time(summary.span[0])} EDT",
                scale=alt.Scale(domain=[0, (summary.span[1] - summary.span[0]) / 60_000])),
        x2="end_min:Q",
        y=alt.Y("row:N", title=None, sort=["Data availability", "Imported episodes"]),
        color=alt.Color("status:N", scale=alt.Scale(
            domain=list(colors), range=list(colors.values())), legend=None),
        tooltip=["row", "status", "start_min", "end_min"],
    ).properties(height=100)
    st.altair_chart(chart, use_container_width=True)
    st.caption(
        f"Data availability {data_lane.pct:.1f}% - valid WISER fixes in 1 s bins. "
        f"Imported-episode coverage {episode_lane.pct:.1f}% - time represented by route bouts. "
        "Unrepresented time is not a tracking gap."
    )


def render_timeline(ctx) -> None:
    subject = ctx.subject_ids[0] if ctx.subject_ids else "unknown"
    subset = session_index[session_index["subject_ids"].map(
        lambda values: subject in {str(v) for v in (values or [])})]
    timeline = pd.DataFrame({
        "start_min": (subset["t_start"] - span[0]) / 60_000,
        "end_min": (subset["t_end"] - span[0]) / 60_000,
        "episode_id": subset["episode_id"],
        "selected": subset["episode_id"].astype(str) == ctx.episode_id,
        "lane": subject_text([subject], names),
    })
    bars = alt.Chart(timeline).mark_bar(height=12).encode(
        x=alt.X("start_min:Q", title=f"minutes after {local_time(span[0])} EDT",
                scale=alt.Scale(domain=[0, (span[1] - span[0]) / 60_000])),
        x2="end_min:Q",
        y=alt.Y("lane:N", title=None),
        color=alt.condition("datum.selected", alt.value(SELECTED_COLOR), alt.value("#AAB4C0")),
        tooltip=["episode_id", "start_min", "end_min"],
    ).properties(height=75)
    st.altair_chart(bars, use_container_width=True)


def selected_fixes(ctx) -> pd.DataFrame:
    if fixes.empty or not ctx.subject_ids:
        return pd.DataFrame()
    return fixes[
        fixes["shortid"].astype(str).isin(ctx.subject_ids)
        & (fixes["ts"] >= ctx.evidence_start)
        & (fixes["ts"] <= ctx.evidence_end)
    ].copy()


def render_wiser(ctx) -> None:
    window = selected_fixes(ctx)
    if window.empty:
        st.info("No bounded WISER evidence exists for this selected interval.")
        return
    window["elapsed_s"] = (window["ts"] - ctx.t_start) / 1000.0
    window["time_edt"] = window["ts"].map(local_time)
    assets = ctx.episode.get("linked_assets") or {}
    role_map = assets.get("role_map") if isinstance(assets.get("role_map"), dict) else {}
    subject_roles = {str(subject): str(role) for role, subject in role_map.items()}
    window["role"] = window["shortid"].astype(str).map(
        lambda subject: subject_roles.get(subject, names.get(subject, subject))
    )
    landmarks = wiser_tracks.load_landmarks()
    layers = []
    if not landmarks["rects"].empty:
        layers.append(alt.Chart(landmarks["rects"]).mark_rect(
            fill="#D7DEE7", fillOpacity=0.35, stroke="#657383").encode(
            x="x0:Q", x2="x1:Q", y="y0:Q", y2="y1:Q", tooltip=["name", "type"]))
    if not landmarks["points"].empty:
        layers.append(alt.Chart(landmarks["points"]).mark_point(
            shape="diamond", filled=True, size=55, color="#657383").encode(
            x="x:Q", y="y:Q", tooltip=["name", "type"]))
    trajectory_points = assets.get("trajectory_snippet") or []
    if trajectory_points:
        trajectory_df = pd.DataFrame(trajectory_points, columns=["x", "y"])
        trajectory_df["order"] = range(len(trajectory_df))
        layers.append(alt.Chart(trajectory_df).mark_line(
            color=SELECTED_COLOR, strokeWidth=3).encode(x="x:Q", y="y:Q", order="order:Q"))
    role_paths = assets.get("trajectory_snippets") or {}
    if isinstance(role_paths, dict):
        role_colors = {"leader": SELECTED_COLOR, "follower": "#2B8CBE"}
        for role, points in role_paths.items():
            if not points:
                continue
            role_df = pd.DataFrame(points, columns=["x", "y"])
            role_df["order"] = range(len(role_df))
            layers.append(alt.Chart(role_df).mark_line(
                color=role_colors.get(str(role), MUTED), strokeWidth=3
            ).encode(x="x:Q", y="y:Q", order="order:Q"))
    layers.append(alt.Chart(window).mark_circle(size=70, opacity=0.9).encode(
        x=alt.X("x:Q", title="x (WISER inches)"),
        y=alt.Y("y:Q", title="y (WISER inches)"),
        color=alt.Color("elapsed_s:Q", scale=alt.Scale(scheme="viridis"), title="seconds"),
        shape=alt.Shape("role:N", title="selected role"),
        tooltip=["rat", "role", "time_edt", "elapsed_s", "valid", "calc_err"],
    ))
    st.altair_chart(alt.layer(*layers).properties(height=390), use_container_width=True)
    if role_map:
        st.warning(
            "WISER positions are native inches with an unverified offset origin. "
            "Shape and path distinguish temporal leader/follower roles; Viridis shows time. "
            "Following remains a candidate interpretation."
        )
    else:
        st.warning(
            "WISER positions are native inches with an unverified offset origin. "
            "The amber path is the imported bout; the Viridis gradient shows time."
        )


def render_weather(ctx) -> None:
    if weather_df.empty:
        st.info("Weather data are unavailable. Set EPISODE_BROWSER_WEATHER_DIR.")
        return
    window = weather.slice_window(weather_df, local_naive(span[0]), local_naive(span[1]))
    nearest = weather.nearest(weather_df, local_naive(ctx.t_start))
    if nearest:
        st.caption(
            f"Nearest sample: {nearest.get('temp_c', 'n/a')} C - "
            f"{nearest.get('humidity_pct', 'n/a')}% RH - "
            f"rain {nearest.get('rain_mm_hr', 'n/a')} mm/hr"
        )
    if window.empty:
        st.info("No weather samples fall inside the 15-minute session window.")
        return
    window = window.assign(
        minute=(window["ts"] - local_naive(span[0])).dt.total_seconds() / 60.0
    )
    band = pd.DataFrame({
        "start_min": [(ctx.t_start - span[0]) / 60_000],
        "end_min": [(ctx.t_end - span[0]) / 60_000],
    })
    selection = alt.Chart(band).mark_rect(color=SELECTED_COLOR, opacity=0.25).encode(
        x="start_min:Q", x2="end_min:Q")
    base = alt.Chart(window).encode(
        x=alt.X("minute:Q", title=f"minutes after {local_time(span[0])} EDT",
                scale=alt.Scale(domain=[0, (span[1] - span[0]) / 60_000])))
    temp = base.mark_line(color="#B45309", point=True).encode(
        y=alt.Y("temp_c:Q", title="temperature C"))
    rain = base.mark_area(color="#3B82A0", opacity=0.3).encode(
        y=alt.Y("rain_mm_hr:Q", title="rain mm/hr"))
    st.altair_chart(alt.layer(selection, rain, temp).resolve_scale(y="independent")
                    .properties(height=260), use_container_width=True)
    st.warning("Weather is a wall-clock covariate with unverified cross-device alignment.")


def video_state(ctx, selected_channel: str | None = None):
    route = route_from_episode(ctx.episode)
    if not route.candidates:
        return route, None, None
    channel = selected_channel or route.candidates[0]
    recording = resolve_recording(channel, ctx.t_start)
    return route, channel, recording


def render_video(ctx, *, frame_count: int = 4, width: int = 320, key_prefix: str = "inline") -> None:
    route = route_from_episode(ctx.episode)
    if not route.candidates:
        st.info(f"Video unmapped: {route.reason}")
        return
    if len(route.candidates) > 1:
        channel = st.selectbox(
            "Camera candidate",
            route.candidates,
            key=f"{key_prefix}_camera_{ctx.episode_id}",
            help="The event crosses candidate coverage; choose a channel explicitly.",
        )
    else:
        channel = route.candidates[0]
        label = "Unverified candidate" if route.status == "unverified" else "Mapped"
        st.caption(f"{label}: **{channel}**")
    recording = resolve_recording(channel, ctx.t_start)
    if route.status == "unverified":
        st.warning(f"Camera routing unverified. {route.reason}")
    if recording is None:
        st.info(f"No closed {channel} recording resolves for the selected timestamp.")
        return
    path = recording["path"]
    start_s = max(0.0, float(recording["offset_s"]) - 5.0)
    end_s = start_s + (ctx.t_end - ctx.t_start) / 1000.0 + 10.0
    st.caption(f"`{path.name}` - candidate evidence only; no video was attached globally.")
    load_key = f"{key_prefix}_load_{ctx.episode_id}_{channel}"
    if st.button("Load subsampled frames", key=load_key, type="primary"):
        st.session_state[f"{load_key}_ready"] = True
    if st.session_state.get(f"{load_key}_ready"):
        frames = cached_frames(str(path), start_s, end_s, frame_count, width, path.stat().st_mtime)
        if not frames:
            st.error("No frames were extracted. Check ffmpeg and the recording path.")
            return
        columns = st.columns(len(frames))
        for column, frame in zip(columns, frames):
            column.image(frame["png"], caption=f"+{frame['t_s'] - recording['offset_s']:.1f}s",
                         use_container_width=True)


def evidence_statuses(ctx) -> list[tuple[str, str, str]]:
    wiser_status = "available" if not selected_fixes(ctx).empty else "missing"
    weather_status = "unverified" if not weather_df.empty else "missing"
    route = route_from_episode(ctx.episode)
    return [
        ("WISER", wiser_status, "bounded real fixes; native inch frame"),
        ("Weather", weather_status, "wall-clock covariate"),
        ("Video", route.status, route.reason),
        ("Thermal", "missing", "placeholder only; no real evidence linked"),
    ]


def render_judgment_rail(ctx) -> None:
    ep = ctx.episode
    st.markdown("### Evidence + judgment")
    st.markdown("**Provenance**")
    st.write(f"State model: `{ep.get('state_model_id')}`")
    st.write(f"Level: `{ep.get('level')}`")
    role_map = ((ep.get("linked_assets") or {}).get("role_map") or {})
    if role_map:
        leader = names.get(str(role_map.get("leader")), str(role_map.get("leader")))
        follower = names.get(str(role_map.get("follower")), str(role_map.get("follower")))
        st.caption(f"Temporal roles: {leader} -> {follower}; this does not imply dominance.")
    labels = ep.get("labels") or []
    if labels:
        st.markdown(" ".join(
            f"<span class='status-chip'>{html.escape(str(label))}</span>" for label in labels
        ), unsafe_allow_html=True)
    if ep.get("state_model_id") == "wiser_lagged_path_reuse_v1":
        st.caption(
            "Existing Phase B2 lagged path-reuse cut - candidate strict trailing - "
            "video validation pending."
        )
    else:
        st.caption("WISER route-bout cut - native inches - unverified offset origin")
    if ep.get("notes"):
        st.caption(str(ep["notes"]))
    st.markdown("<div class='rail-rule'></div>", unsafe_allow_html=True)
    st.markdown("**Evidence availability**")
    for source, status, reason in evidence_statuses(ctx):
        css = "warn-chip" if status in {"missing", "unmapped", "unverified"} else ""
        st.markdown(
            f"<span class='status-chip {css}'>{html.escape(source)}: {html.escape(status)}</span> "
            f"<span style='font-size:11px;color:#657383'>{html.escape(reason)}</span>",
            unsafe_allow_html=True,
        )
    st.markdown("<div class='rail-rule'></div>", unsafe_allow_html=True)
    st.markdown("**Lens signals**")
    scores = ep.get("lens_scores") if isinstance(ep.get("lens_scores"), dict) else {}
    if not scores:
        st.caption("not scored - absence is not zero")
    else:
        for name, value in scores.items():
            st.markdown(f"<span class='status-chip'>{html.escape(name)} {value:.2f}</span>",
                        unsafe_allow_html=True)
    st.markdown("<div class='rail-rule'></div>", unsafe_allow_html=True)
    history = annotations.read_episode_history(ctx.episode_id)
    st.markdown(f"**Annotation history** ({len(history)})")
    for record in history[-3:]:
        st.caption(f"{record.get('verdict')} - {record.get('annotator_id')} - {record.get('ts')}")
    annotator = st.session_state.get("annotator_id", "").strip()
    verdict = st.radio(
        "Judgment",
        ["interesting", "unclear", "artifact", "follow_up"],
        horizontal=True,
        key=f"verdict_{ctx.episode_id}",
    )
    labels = st.text_input("Add post-hoc labels", key=f"labels_{ctx.episode_id}",
                           placeholder="comma-separated")
    note = st.text_area("Note", key=f"note_{ctx.episode_id}", height=80)
    if st.button("Save judgment", key=f"save_{ctx.episode_id}", use_container_width=True):
        if not annotator:
            st.warning("Set an annotator ID before saving.")
        else:
            path = annotations.write_annotation(
                ctx.episode_id,
                annotator,
                verdict,
                [value.strip() for value in labels.split(",") if value.strip()],
                note,
                session=st.session_state.session_tag,
            )
            st.toast(f"Appended to {path.name}; no existing record was overwritten.")
            st.rerun()
    st.caption("Judgments are append-only. The episode store is never modified.")


def render_blind() -> None:
    st.markdown("### Blind evaluation")
    st.caption("Scores remain hidden until the expert verdict is recorded.")
    lens_keys = options["lens_keys"]
    if not lens_keys:
        st.info("No lens scores exist in this real integration slice. Use demo mode to exercise blind ranking.")
        return
    lens = st.selectbox("Ranking lens", lens_keys)
    top_k = st.number_input("Top k", 1, 50, min(10, len(session_index)))
    ranked = query.rank_by_lens(session_index, lens, drop_absent=True).head(int(top_k))
    if ranked.empty:
        st.info("No episodes carry this lens score.")
        return
    st.session_state.setdefault("blind_index", 0)
    index = min(int(st.session_state.blind_index), len(ranked) - 1)
    row = ranked.iloc[index]
    episode = repository.get_episode(str(row["episode_id"]))
    st.progress((index + 1) / len(ranked), text=f"episode {index + 1} of {len(ranked)}")
    st.write(f"**{episode['episode_id']}** - {subject_text(episode.get('subject_ids'), names)}")
    st.write({"state_vector": episode.get("state_vector"), "labels": episode.get("labels"),
              "qc_flags": episode.get("qc_flags")})
    st.info("Lens scores hidden. Record the verdict before reveal.")
    verdict = st.radio("Blind verdict", ["interesting", "unclear", "artifact", "follow_up"],
                       horizontal=True, key=f"blind_verdict_{episode['episode_id']}")
    left, right = st.columns(2)
    if left.button("Reveal and log verdict"):
        annotator = st.session_state.get("annotator_id", "").strip()
        if not annotator:
            st.warning("Set an annotator ID before logging.")
        else:
            annotations.log_blind_eval(
                episode["episode_id"], annotator, lens, verdict,
                episode.get("lens_scores") or {}, session=st.session_state.session_tag,
            )
            st.session_state[f"blind_revealed_{episode['episode_id']}"] = True
    if st.session_state.get(f"blind_revealed_{episode['episode_id']}"):
        st.success(f"Recorded. Scores: {episode.get('lens_scores')}")
    if right.button("Next episode"):
        st.session_state.blind_index = min(index + 1, len(ranked) - 1)
        st.rerun()


if st.session_state.nav == "Review":
    selected_header(context)
    if context is not None:
        summary = coverage.compute_separate_coverage(session_index, fixes, span)
        selected_subject = context.subject_ids[0] if context.subject_ids else "unknown"
        st.markdown("#### Session coverage")
        coverage_chart(summary, selected_subject)
        evidence_column, rail_column = st.columns([2.25, 1], gap="large")
        with evidence_column:
            st.markdown("#### Synchronized evidence")
            render_timeline(context)
            evidence_view = st.segmented_control(
                "Evidence view", ["WISER", "Weather", "Video"], default="WISER",
                label_visibility="collapsed",
            )
            if evidence_view == "Weather":
                render_weather(context)
            elif evidence_view == "Video":
                render_video(context, frame_count=4, width=320, key_prefix="review")
            else:
                render_wiser(context)
        with rail_column:
            render_judgment_rail(context)

elif st.session_state.nav == "Video":
    selected_header(context)
    if context is None:
        st.info("Select an episode in Review first.")
    else:
        video_column, rail_column = st.columns([2.25, 1], gap="large")
        with video_column:
            st.markdown("### Video evidence")
            render_video(context, frame_count=6, width=480, key_prefix="full")
        with rail_column:
            render_judgment_rail(context)

else:
    render_blind()
