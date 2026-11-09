"""
Dependency-free statistics helpers for A/B tests (Python 3.9+, stdlib only).

Everything here is plain textbook maths, kept small on purpose so each function
can be checked by hand: two-proportion z-test, sample size and power, sample ratio
mismatch (SRM) check, chi-square test of independence, bootstrap confidence
interval for a difference in means, winsorizing, and a peeking simulation.
"""

import math
import random


# ---------------------------------------------------------------- distributions

def normal_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_sf(x):
    """Upper tail P(Z > x)."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def normal_ppf(p):
    """Inverse normal CDF by bisection (slow but exact enough: ~1e-12)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _gamma_series(a, x):
    """Regularised lower incomplete gamma P(a, x), series form (x < a + 1)."""
    term = total = 1.0 / a
    ap = a
    for _ in range(2000):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cfrac(a, x):
    """Regularised upper incomplete gamma Q(a, x), continued fraction (x >= a + 1)."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 2000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x, df):
    """Upper tail of the chi-square distribution: P(X > x)."""
    if x <= 0:
        return 1.0
    a, xx = df / 2.0, x / 2.0
    if xx < a + 1.0:
        return 1.0 - _gamma_series(a, xx)
    return _gamma_cfrac(a, xx)


# ------------------------------------------------------------------- design

def sample_size_per_arm(p1, p2, alpha=0.05, power=0.80):
    """Players needed per arm to detect p1 -> p2 (two-sided, equal arms)."""
    za = normal_ppf(1.0 - alpha / 2.0)
    zb = normal_ppf(power)
    pbar = (p1 + p2) / 2.0
    num = (za * math.sqrt(2.0 * pbar * (1.0 - pbar))
           + zb * math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))) ** 2
    return int(math.ceil(num / (p2 - p1) ** 2))


def power_two_proportions(p1, p2, n_per_arm, alpha=0.05):
    """Probability to detect p1 -> p2 with n_per_arm players per arm."""
    za = normal_ppf(1.0 - alpha / 2.0)
    pbar = (p1 + p2) / 2.0
    se0 = math.sqrt(2.0 * pbar * (1.0 - pbar) / n_per_arm)
    se1 = math.sqrt((p1 * (1.0 - p1) + p2 * (1.0 - p2)) / n_per_arm)
    return normal_cdf((abs(p2 - p1) - za * se0) / se1)


# ------------------------------------------------------------------- tests

def two_proportion_test(x_a, n_a, x_b, n_b, alpha=0.05):
    """A = control, B = treatment. p-value from the pooled z-test; the confidence
    interval of the difference (B - A) is the unpooled Wald interval at 1 - alpha."""
    p_a, p_b = x_a / n_a, x_b / n_b
    diff = p_b - p_a
    pooled = (x_a + x_b) / float(n_a + n_b)
    se_pooled = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b))
    z = diff / se_pooled if se_pooled > 0 else 0.0
    se = math.sqrt(p_a * (1.0 - p_a) / n_a + p_b * (1.0 - p_b) / n_b)
    zc = normal_ppf(1.0 - alpha / 2.0)
    return {
        "p_a": p_a, "p_b": p_b, "diff": diff,
        "rel_lift": diff / p_a if p_a > 0 else None,
        "ci_low": diff - zc * se, "ci_high": diff + zc * se,
        "z": z, "p_value": 2.0 * normal_sf(abs(z)),
    }


def srm_check(counts, expected_shares, threshold=0.001):
    """Sample ratio mismatch: do the observed arm sizes fit the planned split?
    A p-value below `threshold` (0.001 is the usual cut-off) means the assignment
    is broken and the experiment result must not be trusted."""
    total = float(sum(counts))
    expected = [total * s for s in expected_shares]
    chi2 = sum((o - e) ** 2 / e for o, e in zip(counts, expected))
    df = len(counts) - 1
    p = chi2_sf(chi2, df)
    return {"chi2": chi2, "df": df, "p_value": p, "ok": p >= threshold}


def chi_square_independence(table):
    """table = list of rows, each row = counts per arm. Tests whether the category
    mix (channel, country) is the same in every arm (covariate balance)."""
    row_tot = [sum(r) for r in table]
    col_tot = [sum(r[j] for r in table) for j in range(len(table[0]))]
    grand = float(sum(row_tot))
    chi2 = 0.0
    for i, r in enumerate(table):
        for j, o in enumerate(r):
            e = row_tot[i] * col_tot[j] / grand
            chi2 += (o - e) ** 2 / e
    df = (len(table) - 1) * (len(table[0]) - 1)
    return {"chi2": chi2, "df": df, "p_value": chi2_sf(chi2, df)}


# ----------------------------------------------------------- means / outliers

def mean(values):
    return sum(values) / len(values)


def winsorize(values, lower=0.01, upper=0.99):
    """Cap extreme values at the given percentiles (computed on the pooled sample)."""
    s = sorted(values)
    lo = s[int(lower * (len(s) - 1))]
    hi = s[int(upper * (len(s) - 1))]
    return [min(max(v, lo), hi) for v in values], lo, hi


def bootstrap_mean_diff(a, b, n_boot=2000, ci_level=0.95, seed=1):
    """Percentile bootstrap interval for mean(b) - mean(a). Resamples each arm with
    replacement; no normality assumption, which matters for heavy-tailed revenue."""
    rnd = random.Random(seed)
    na, nb = len(a), len(b)
    diffs = []
    for _ in range(n_boot):
        diffs.append(sum(rnd.choices(b, k=nb)) / nb - sum(rnd.choices(a, k=na)) / na)
    diffs.sort()
    lo = diffs[int((1.0 - ci_level) / 2.0 * n_boot)]
    hi = diffs[int((1.0 + ci_level) / 2.0 * n_boot) - 1]
    return {"mean_a": mean(a), "mean_b": mean(b), "diff": mean(b) - mean(a),
            "ci_low": lo, "ci_high": hi, "ci_level": ci_level}


# -------------------------------------------------------------- peeking demo

def peeking_simulation(p=0.10, n_per_arm=4000, n_looks=14, n_sims=1000, alpha=0.05, seed=7):
    """A/A experiments (both arms convert at the same rate p, so any 'win' is a false
    positive). Compare two ways to read the same data: one look at the end versus
    checking every day and stopping at the first p < alpha."""
    rnd = random.Random(seed)
    zc = normal_ppf(1.0 - alpha / 2.0)
    batch = n_per_arm // n_looks
    any_hit = final_hit = 0
    for _ in range(n_sims):
        xa = xb = n = 0
        hit = False
        z = 0.0
        for _look in range(n_looks):
            xa += sum(rnd.random() < p for _ in range(batch))
            xb += sum(rnd.random() < p for _ in range(batch))
            n += batch
            pooled = (xa + xb) / (2.0 * n)
            se = math.sqrt(pooled * (1.0 - pooled) * 2.0 / n)
            z = ((xb - xa) / float(n)) / se if se > 0 else 0.0
            if abs(z) > zc:
                hit = True
        any_hit += hit
        final_hit += abs(z) > zc
    return {"n_sims": n_sims, "n_looks": n_looks, "alpha": alpha,
            "n_per_arm": batch * n_looks,
            "fp_single_look": final_hit / float(n_sims),
            "fp_peeking": any_hit / float(n_sims)}
