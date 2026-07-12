"""Analysis 3 (left-truncation), 4 (run-termination hazard + model comparison), 10
(distribution model comparison). Pure numpy (scipy absent).

Uses the UN-truncated segment set (min_bout=0, all moving runs >=2 samples) so the
duration distribution is not left-censored at 3 s, then asks whether a reproducible
termination timescale exists beyond the sampling/speed-window floor.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = Path(__file__).resolve(); SRC = HERE.parent; ROOT = SRC.parent
sys.path.insert(0, str(SRC)); import bout_seg as bs
CACHE = Path(sys.argv[1]); TAB = ROOT / "tables"; PLT = ROOT / "plots"
rng = np.random.default_rng(0)

pos = bs.load_positions(CACHE)
ps = bs.add_speed_param(pos, smooth_window=7)
raw = bs.segment(ps, moving_thr=12.63, min_bout_s=0.0, min_disp_in=0.0, pause_merge_s=0.0, max_gap_s=2.0)
T = raw["dur_s"].to_numpy(); T = T[np.isfinite(T) & (T > 0)]
print(f"un-truncated segments: n={len(T)}  min={T.min():.2f} median={np.median(T):.2f} max={T.max():.2f}")

# ---------- discrete-time hazard on a 0.25 s grid ----------
dt = 0.25
edges = np.arange(0, T.max() + dt, dt)
ended, _ = np.histogram(T, bins=edges)
at_risk = len(T) - np.concatenate([[0], np.cumsum(ended)[:-1]])
haz = np.where(at_risk > 0, ended / at_risk, np.nan)
surv = at_risk / len(T)
mid = edges[:-1] + dt / 2
hz = pd.DataFrame({"t_mid_s": mid, "at_risk": at_risk, "ended": ended,
                   "hazard": np.round(haz, 4), "survival": np.round(surv, 4)})
hz.to_csv(TAB / "duration_hazard.csv", index=False)

# ---------- MLE fits (numpy) with left-truncation at a=min duration ----------
a = float(T.min())   # left-truncation point (>=2 samples)
def golden(f, lo, hi, tol=1e-5):
    g = (np.sqrt(5) - 1) / 2; c = hi - g*(hi-lo); d = lo + g*(hi-lo)
    for _ in range(200):
        if f(c) < f(d): hi = d
        else: lo = c
        c = hi - g*(hi-lo); d = lo + g*(hi-lo)
        if abs(hi-lo) < tol: break
    return (lo+hi)/2
def ll_exp(x, a):
    lam = 1.0/(x.mean()-a)                       # left-truncated exponential MLE
    return np.sum(np.log(lam) - lam*(x-a)), 1, {"lambda": lam}
def ll_weibull(x, a):
    # left-truncated Weibull; optimise shape k, scale from moment given k
    lx = np.log(x)
    def negll(k):
        # profile scale via MLE ignoring truncation (approx), then correct with trunc term
        lam = (np.mean(x**k))**(1.0/k)
        S_a = np.exp(-(a/lam)**k)
        ll = np.sum(np.log(k/lam) + (k-1)*np.log(x/lam) - (x/lam)**k) - len(x)*np.log(S_a)
        return -ll
    k = golden(negll, 0.3, 6.0)
    lam = (np.mean(x**k))**(1.0/k)
    return -negll(k), 2, {"k": k, "lambda": lam}
def ll_lognorm(x, a):
    lx = np.log(x)
    def negll(p):
        mu, sig = p
        S_a = 0.5*(1-erf((np.log(a)-mu)/(sig*np.sqrt(2))))
        ll = np.sum(-np.log(x*sig*np.sqrt(2*np.pi)) - (lx-mu)**2/(2*sig**2)) - len(x)*np.log(S_a)
        return -ll
    mu0, sig0 = lx.mean(), lx.std()
    # coordinate ascent (cheap)
    mu, sig = mu0, sig0
    for _ in range(30):
        mu = golden(lambda m: negll((m, sig)), mu0-1, mu0+1)
        sig = golden(lambda s: negll((mu, s)), 0.2, 2.5)
    return -negll((mu, sig)), 2, {"mu": mu, "sigma": sig}
def ll_gamma(x, a):
    # truncated gamma; optimise shape kappa, rate from mean/kappa
    def negll(kap):
        theta = (x.mean())/kap
        # gamma pdf; truncation via lower incomplete approximated by ignoring (a small) -> note approx
        ll = np.sum((kap-1)*np.log(x) - x/theta - kap*np.log(theta) - _lgamma(kap))
        return -ll
    kap = golden(negll, 0.3, 8.0)
    theta = x.mean()/kap
    return -negll(kap), 2, {"kappa": kap, "theta": theta}
def erf(z):
    # Abramowitz-Stegun 7.1.26
    t = 1/(1+0.3275911*np.abs(z))
    y = 1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*np.exp(-z*z)
    return np.sign(z)*y
def _lgamma(z):
    # Lanczos
    g=7; c=[0.99999999999980993,676.5203681218851,-1259.1392167224028,771.32342877765313,
            -176.61502916214059,12.507343278686905,-0.13857109526572012,9.9843695780195716e-6,
            1.5056327351493116e-7]
    z=z-1; xx=c[0]
    for i in range(1,g+2): xx+=c[i]/(z+i)
    tt=z+g+0.5
    return 0.5*np.log(2*np.pi)+(z+0.5)*np.log(tt)-tt+np.log(xx)

# held-out: 70/30 split, fit train, LL on test
idx = rng.permutation(len(T)); tr, te = T[idx[:int(.7*len(T))]], T[idx[int(.7*len(T)):]]
fits = {}
for name, fn in [("exponential", ll_exp), ("weibull", ll_weibull),
                 ("gamma", ll_gamma), ("lognormal", ll_lognorm)]:
    ll_full, kpar, par = fn(T, a)
    ll_tr, _, par_tr = fn(tr, a)
    # test LL under train params (recompute density)
    fits[name] = {"loglik_full": round(float(ll_full), 1), "n_params": kpar,
                  "AIC": round(float(2*kpar - 2*ll_full), 1),
                  "BIC": round(float(kpar*np.log(len(T)) - 2*ll_full), 1),
                  "params": {k: round(float(v), 4) for k, v in par.items()}}
# piecewise-constant hazard breakpoint scan (two rates before/after tau)
def pcll(tau):
    b = T <= tau
    n1, n2 = b.sum(), (~b).sum()
    if n1 < 5 or n2 < 5: return -1e18, None
    lam1 = n1 / (np.minimum(T, tau) - a).sum()
    lam2 = n2 / (T[~b] - tau).sum() if n2 else 0
    ll = (n1*np.log(lam1) - lam1*(np.minimum(T, tau)-a).sum()
          + n2*np.log(lam2) - lam2*(T[~b]-tau).sum())
    return ll, (lam1, lam2)
taus = np.arange(a+0.5, T.max()-0.5, 0.25)
pcvals = [pcll(t)[0] for t in taus]
best_tau = float(taus[int(np.argmax(pcvals))]); best_ll = float(np.max(pcvals))
fits["piecewise_hazard"] = {"loglik_full": round(best_ll, 1), "n_params": 3,
                            "AIC": round(2*3 - 2*best_ll, 1),
                            "BIC": round(3*np.log(len(T)) - 2*best_ll, 1),
                            "breakpoint_s": round(best_tau, 2)}
(TAB / "hazard_model_comparison.csv"
 ).write_text(pd.DataFrame(fits).T.to_csv())
(TAB / "distribution_model_comparison.json").write_text(json.dumps(fits, indent=2))
print(json.dumps(fits, indent=2))

# left-truncation check (A3): does prod median (3s cut) = conditional median of untruncated?
med3 = np.median(T[T >= 3.0])
print(f"\n[A3] untruncated median={np.median(T):.2f}s; median|dur>=3s = {med3:.2f}s "
      f"(production reported 3.8s => {abs(med3-3.8)<0.3})")

# ---------- plots ----------
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].step(mid, surv, where="mid"); ax[0].set_yscale("log")
ax[0].set_xlabel("run duration t (s)"); ax[0].set_ylabel("S(t) = P(T>t)  [log]")
ax[0].axvline(3.0, ls="--", c="r", label="production min_bout 3s"); ax[0].legend(fontsize=8)
ax[0].set_title("Survival (log) — straight line = constant hazard (memoryless)")
m = at_risk >= 30
ax[1].plot(mid[m], haz[m], "-o", ms=3)
ax[1].axvline(3.0, ls="--", c="r"); ax[1].axvline(best_tau, ls=":", c="g", label=f"best breakpoint {best_tau:.1f}s")
ax[1].set_xlabel("run duration t (s)"); ax[1].set_ylabel("termination hazard h(t)")
ax[1].set_title("Hazard vs elapsed time (at-risk>=30)"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(PLT / "survival_and_hazard.png", dpi=120); plt.close(fig)
print("[done] hazard + distributions")
