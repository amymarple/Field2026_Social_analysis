r"""
weather_context.py — dynamic environmental context + weather-dependent measurement audit.

Weather plays THREE distinct roles here (never a coarse wet/dry label, never causal):
  1. **Dynamic context** — a PRESPECIFIED, low-dimensional per-decision weather vector
     (temperature, temp-dewpoint gap = humidity, rain, solar radiation = daylight). The same
     vector adjusts the shared, personalized, and social models identically.
  2. **Measurement-quality determinant** — :func:`measurement_process_audit` quantifies whether
     the OBSERVATION process (WISER validity/dropout and stationary jitter) varies with
     weather x ROI x animal x night, BEFORE any policy modeling. A gap stays 'unknown',
     never a departure.
  3. **Transfer axis** — individual/social gains are unfolded by weather regime downstream.

Because ~8 nights are available and weather is confounded with night, habituation, fireworks,
and burrow formation, this module deliberately exposes only a LOW-dimensional prespecified
vector and makes NO causal weather claims and fits NO high-dimensional weather response.

Shelter/microclimate temperature is NOT available in-window (ambient AWN only; the interior
CH07/CH08 cams begin 2026-07-07, after the WISER window) — a documented hook, not a variable.

numpy + pandas (+ reuses wiser_analysis_utils.load_weather*). Imports in the ``cv`` env.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from . import wiser_analysis_utils as w
except ImportError:                                  # src on sys.path
    import wiser_analysis_utils as w                 # type: ignore


# The prespecified low-dimensional weather vector (kept small on purpose).
PRESPEC_FEATURES = ["w_temp_c", "w_tempdew_gap_c", "w_rain_log1p", "w_solar_wm2"]


def load_weather_features(paths) -> pd.DataFrame:
    """Load AWN weather (via ``wiser_analysis_utils``) and add the prespecified w_* columns.

    - ``w_temp_c``        : outdoor temperature (deg C).
    - ``w_tempdew_gap_c`` : temperature minus dew point (deg C); larger = drier air.
    - ``w_rain_log1p``    : log(1 + rain rate mm/hr); 0 = dry.
    - ``w_solar_wm2``     : solar radiation (W/m^2) = daylight/photoperiod signal.
    Returns rows sorted by ``datetime_utc`` (naive UTC)."""
    if isinstance(paths, (list, tuple)):
        wx = w.load_weather_multi(list(paths))
    else:
        wx = w.load_weather_multi([paths]) if hasattr(w, "load_weather_multi") else w.load_weather(paths)
    wx = wx.copy()
    wx["w_temp_c"] = wx["temp_c"].astype(float)
    wx["w_tempdew_gap_c"] = (wx["temp_c"] - wx["dewpoint_c"]).astype(float)
    wx["w_rain_log1p"] = np.log1p(wx["rain_rate_mmhr"].clip(lower=0).astype(float))
    wx["w_solar_wm2"] = wx["solar_wm2"].astype(float)
    wx["datetime_utc"] = pd.to_datetime(wx["datetime_utc"]).astype("datetime64[ns]")
    return wx.sort_values("datetime_utc").reset_index(drop=True)


def attach_weather(df: pd.DataFrame, wx: pd.DataFrame, *, time_col: str = "datetime",
                   tol_minutes: float = 15.0, features=None) -> pd.DataFrame:
    """As-of merge the prespecified weather vector onto ``df`` by nearest UTC time within a
    tolerance (AWN cadence is ~5 min). ``df[time_col]`` must be naive UTC. Rows with no
    weather within tolerance get NaN weather (carried, never imputed to a value)."""
    features = list(features or PRESPEC_FEATURES)
    left = df.copy()
    left[time_col] = pd.to_datetime(left[time_col]).astype("datetime64[ns]")
    order = left[time_col].argsort(kind="mergesort")
    left_sorted = left.iloc[order.to_numpy()].reset_index(drop=True) if hasattr(order, "to_numpy") \
        else left.iloc[np.asarray(order)].reset_index(drop=True)
    right = wx[["datetime_utc"] + features].dropna(subset=["datetime_utc"]).sort_values("datetime_utc")
    merged = pd.merge_asof(left_sorted, right, left_on=time_col, right_on="datetime_utc",
                           direction="nearest", tolerance=pd.Timedelta(minutes=tol_minutes))
    merged = merged.drop(columns=["datetime_utc"])
    return merged


def night_weather_summary(wx: pd.DataFrame, *, night_start: int = 21, night_end: int = 5,
                          tz_offset_hours: int = -4, features=None) -> pd.DataFrame:
    """Per-night mean of the prespecified weather vector over the night window (for the
    weather-regime transfer unfolding). Night N = local date N 21:00 -> N+1 05:00."""
    features = list(features or PRESPEC_FEATURES)
    x = wx.copy()
    local = x["datetime_utc"] + pd.to_timedelta(tz_offset_hours, unit="h")
    hour = local.dt.hour
    in_night = (hour >= night_start) | (hour < night_end)
    x = x[in_night].copy()
    # attribute pre-dawn hours (<night_end) to the previous local date
    ldate = local.dt.normalize()
    pre_dawn = local.dt.hour < night_end
    night = ldate.where(~pre_dawn, ldate - pd.Timedelta(days=1))
    x["night"] = night[in_night].dt.date.astype(str).values
    return (x.groupby("night")[features].mean().reset_index()
            .rename(columns={f: f + "_nightmean" for f in features}))


# ---------------------------------------------------------------------------
# weather-dependent measurement-process audit
# ---------------------------------------------------------------------------

def _stationary_jitter_proxy(raw_speed: pd.Series, smooth_speed: pd.Series | None = None, *,
                             low_quantile: float = 0.25) -> float:
    """Stationary-jitter proxy (in/s): among the epochs the animal is (near) STILL, the residual
    apparent frame-to-frame speed is localization noise. Stillness is selected on the ROBUST
    locomotion channel ``speed_inps_smooth`` (which separates motion from jitter), and the residual
    is measured on ``speed_inps_raw`` (jitter + motion) — selecting and measuring on the SAME raw
    speed would confound activity with noise and could invert the rain-vs-dry ordering. If the
    smooth channel is unavailable, falls back to the raw channel (documented, weaker). NaN if too
    few epochs."""
    r = pd.to_numeric(raw_speed, errors="coerce")
    s = pd.to_numeric(smooth_speed, errors="coerce") if smooth_speed is not None else r
    dd = pd.DataFrame({"r": r, "s": s}).dropna()
    if len(dd) < 8:
        return float("nan")
    still = dd[dd["s"] <= dd["s"].quantile(low_quantile)]      # stillness by robust speed
    return float(still["r"].median()) if len(still) else float("nan")   # residual on raw speed


def measurement_process_audit(fixes: pd.DataFrame, *, group_cols=("night", "shortid", "roi"),
                              weather_col: str | None = None, weather_bins: int = 3,
                              speed_col: str = "speed_inps_raw",
                              smooth_speed_col: str = "speed_inps_smooth",
                              valid_col: str = "valid", gap_col: str = "gap_flag",
                              min_n: int = 30) -> pd.DataFrame:
    """Quantify whether the OBSERVATION process varies with weather x ROI x animal x night.

    For each stratum (``group_cols`` [+ a weather bin]) report:
      - ``n``                    : fixes in the stratum;
      - ``valid_frac``           : observation probability = mean(``valid``);
      - ``gap_frac``             : dropout indicator = mean(``gap_flag``);
      - ``jitter_proxy_inps``    : stationary-jitter proxy (see ``_stationary_jitter_proxy``).

    This is a measurement diagnostic, NOT behavior. A high gap_frac stratum means the decision
    tables there are unreliable — gaps must remain 'unknown', never coded as staying/leaving.
    Pass ``weather_col`` (e.g. 'w_rain_log1p') to also stratify by a weather tercile.
    """
    df = fixes.copy()
    gcols = list(group_cols)
    if weather_col and weather_col in df.columns:
        wq = pd.to_numeric(df[weather_col], errors="coerce")
        try:
            df["weather_bin"] = pd.qcut(wq, q=weather_bins, labels=False, duplicates="drop")
        except ValueError:
            df["weather_bin"] = 0
        gcols = gcols + ["weather_bin"]

    rows = []
    for key, g in df.groupby(gcols, dropna=False):
        if len(g) < min_n:
            continue
        rec = dict(zip(gcols, key if isinstance(key, tuple) else (key,)))
        rec["n"] = int(len(g))
        rec["valid_frac"] = float(pd.to_numeric(g.get(valid_col, np.nan), errors="coerce").mean())
        rec["gap_frac"] = float(pd.to_numeric(g.get(gap_col, np.nan), errors="coerce").mean())
        rec["jitter_proxy_inps"] = _stationary_jitter_proxy(
            g.get(speed_col, pd.Series(dtype=float)),
            g.get(smooth_speed_col) if smooth_speed_col in g.columns else None)
        rows.append(rec)
    return pd.DataFrame(rows)
