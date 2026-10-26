"""
09_dashboard_presentation.py
------------------------------
Presentation-ready version of the scores-only dashboard (08): full English UI, KPI
tiles, a value breakdown table, a cancellation-type x action cross-tab, a color-coded
risk list, and a plain-language walkthrough of the math, for use in a pitch.

Decision logic builds on 08_dashboard_from_scores.py's input contract, with two
enhancements: (1) policy value scales with each policy's own premium over an
adjustable "value horizon" instead of a flat book-wide average, and (2) the
incentive/discount can be attached to either contact channel — a phone call or a
low-cost SMS/email — not just phone.

============================================================
REQUIRED CSV COLUMNS:
  POLICY_HASH        unique policy identifier
  p_Switcher         probability of "Switcher" cancellation (0-1)
  p_System Lapsed    probability of "System Lapsed" cancellation (0-1)
  p_Leave PHI        probability of "Leave PHI" cancellation (0-1)
  p_Non-Recoverable  probability of "Non-Recoverable" cancellation (0-1)
  MONTHLY_PREMIUM    monthly premium (used to size the discount cost)

OPTIONAL CSV COLUMNS (nice to have, not required):
  STATE_CODE, TENURE_BAND, ARREARS_FLAG
============================================================

Run:
  pip install streamlit pandas numpy --break-system-packages
  streamlit run 09_dashboard_presentation.py

The one thing you'll want to change: DEFAULT_CSV_PATH below, or just type the
right file name into the "Scored CSV path" box in the sidebar once the app is open.
"""

import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="HBF Policy Cancellation Early-Warning Dashboard", layout="wide")

# ============================================================
# Change this to the file your teammate gives you, or type the path
# straight into the sidebar once the app is running.
# ============================================================
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV_PATH = os.path.join(HERE, "mock_scored_policies_20000.csv")

# ============ Business constants (from the official HBF challenge pack) ============
CANCEL_TYPES = ["Switcher", "System Lapsed", "Leave PHI", "Non-Recoverable"]
ACTIONS = ["digital", "digital_discount", "phone", "phone_discount"]
ACTION_LABEL = {
    "digital": "Digital (SMS/email)",
    "digital_discount": "Digital + incentive",
    "phone": "Phone only",
    "phone_discount": "Phone + incentive",
}
NO_ACTION_LABEL = "No action"
PHONE_COST = 20
DIGITAL_COST = 0.10
MAX_DISCOUNT_PCT = 0.12
ACTION_COST = {
    "digital": DIGITAL_COST,
    "digital_discount": DIGITAL_COST,
    "phone": PHONE_COST,
    "phone_discount": PHONE_COST,
}

REQUIRED_COLS = ["POLICY_HASH", "MONTHLY_PREMIUM"] + [f"p_{t}" for t in CANCEL_TYPES]
OPTIONAL_DISPLAY_COLS = ["STATE_CODE", "TENURE_BAND", "ARREARS_FLAG"]

# digital_discount defaults sit between plain digital and phone_discount: the incentive
# itself lifts success meaningfully, but a text/email still can't persuade like a live
# call can, so it's set below phone_discount's rate for the same cancellation type.
DEFAULT_UPLIFT = {
    "Switcher":        {"digital": 0.03, "digital_discount": 0.60, "phone": 0.12, "phone_discount": 0.80},
    "System Lapsed":   {"digital": 0.05, "digital_discount": 0.15, "phone": 0.25, "phone_discount": 0.32},
    "Leave PHI":       {"digital": 0.04, "digital_discount": 0.09, "phone": 0.10, "phone_discount": 0.20},
    "Non-Recoverable": {"digital": 0.00, "digital_discount": 0.00, "phone": 0.00, "phone_discount": 0.00},
}

# ============ Chart colors (validated categorical palette, fixed assignment) ============
ACTION_COLORS = {
    NO_ACTION_LABEL: "#898781",                       # muted gray — "nothing happens" is not a category to compete for hue
    ACTION_LABEL["digital"]: "#2a78d6",                # slot 1 blue
    ACTION_LABEL["phone"]: "#eb6834",                  # slot 2 orange
    ACTION_LABEL["phone_discount"]: "#1baf7a",         # slot 3 aqua
    ACTION_LABEL["digital_discount"]: "#eda100",       # slot 4 yellow
}
TYPE_COLORS = {
    "Switcher": "#2a78d6",          # slot 1 blue
    "System Lapsed": "#eb6834",     # slot 2 orange
    "Leave PHI": "#1baf7a",         # slot 3 aqua
    "Non-Recoverable": "#eda100",   # slot 4 yellow
}
# Light background tints for row-highlighting the risk list — same hue family as
# ACTION_COLORS, stepped light enough that primary-ink text stays easily readable
# on top. "No action" deliberately gets no tint (nothing to flag for that row).
ACTION_ROW_TINT = {
    ACTION_LABEL["digital"]: "#dbeafc",             # light blue
    ACTION_LABEL["phone"]: "#fbe3d5",               # light orange
    ACTION_LABEL["phone_discount"]: "#d7f3e9",      # light aqua
    ACTION_LABEL["digital_discount"]: "#fbead0",    # light yellow
}
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"


@st.cache_data(show_spinner="Loading scored policies...")
def load_scores(csv_source):
    """csv_source can be a local file path (str) or an uploaded file object
    (what st.file_uploader returns) — pandas reads either the same way."""
    df = pd.read_csv(csv_source)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required column(s): {missing}")
    return df


def decide_action(probs_row, monthly_premium, uplift, min_ev, value_horizon_months):
    """Same expected-net-value formula as the other dashboard scripts, with two changes:
       1) the "value" of saving a policy is THIS policy's own premium over some number of
          future months (monthly_premium x value_horizon_months), not a flat book-wide
          average — a $50/month policy and a $500/month policy are not worth the same to
          retain. value_horizon_months is adjustable in the sidebar (nobody here knows the
          real average tenure of a saved policy, so it's a testable assumption, not a fact).
       2) the discount/incentive can be attached to EITHER contact method — a phone call
          ("Phone + incentive") or a low-cost SMS/email ("Digital + incentive") — each
          reduces the value being saved by the same 12%-of-annual-premium amount, but only
          costs $0.10 to send digitally instead of $20 for a call.
       The discount cap itself stays tied to ANNUAL premium — that part IS specified by
       the official brief ("up to 12% of annual premium") and doesn't move with the slider.
       EV(action) = (Σ_type P(type) x uplift[type][action]) x value_for(action) - cost(action)

       One `min_ev` bar applies to all 4 actions equally: a channel is only recommended
       once its own expected net value clears that same bar, whether it's a $0.10 text or
       a $20 call. (Digital used to get a separate, lower bar while phone only needed
       EV > 0 — inconsistent, and it meant raising the digital bar alone could never bring
       down how many policies get a phone call.)
    """
    annual_premium = monthly_premium * 12
    horizon_value = monthly_premium * value_horizon_months
    incentive_cost = annual_premium * MAX_DISCOUNT_PCT
    discounted_value = max(horizon_value - incentive_cost, 0)
    value_for = {
        "digital": horizon_value,
        "phone": horizon_value,
        "digital_discount": discounted_value,
        "phone_discount": discounted_value,
    }

    ev = {}
    for a in ACTIONS:
        gain = sum(probs_row[t] * uplift[t][a] for t in CANCEL_TYPES)
        ev[a] = gain * value_for[a] - ACTION_COST[a]

    candidates = {NO_ACTION_LABEL: 0.0}
    for a in ACTIONS:
        if ev[a] >= min_ev:
            candidates[ACTION_LABEL[a]] = ev[a]

    best_label = max(candidates, key=candidates.get)
    best_ev = candidates[best_label]
    return best_label, best_ev


def decide_actions(probs, monthly_premium, uplift, min_ev, value_horizon_months):
    """Vectorized version of decide_action for the full book (needed on a 20k-row public demo)."""
    premium = monthly_premium.to_numpy(dtype=float)
    horizon_value = premium * value_horizon_months
    discounted_value = np.maximum(horizon_value - premium * 12 * MAX_DISCOUNT_PCT, 0.0)

    columns = [NO_ACTION_LABEL]
    data = [np.zeros(len(probs))]
    for a in ACTIONS:
        gain = np.zeros(len(probs))
        for t in CANCEL_TYPES:
            gain = gain + probs[t].to_numpy(dtype=float) * uplift[t][a]
        value = discounted_value if a in ("digital_discount", "phone_discount") else horizon_value
        ev = gain * value - ACTION_COST[a]
        ev = np.where(ev >= min_ev, ev, -np.inf)
        columns.append(ACTION_LABEL[a])
        data.append(ev)

    ev_df = pd.DataFrame(dict(zip(columns, data)), index=probs.index)
    return ev_df.idxmax(axis=1), ev_df.max(axis=1)


# ============================================================
# Page
# ============================================================
st.title("HBF Policy Cancellation Early-Warning Dashboard")
st.caption(
    "Reads a teammate's already-scored policies (4 cancellation-type probabilities per "
    "policy) and turns them into a recommended action and its expected net value."
)

st.sidebar.header("Data source")
uploaded_file = st.sidebar.file_uploader(
    "Upload your scored CSV",
    type=["csv"],
    help=(
        "Must contain: POLICY_HASH, MONTHLY_PREMIUM, p_Switcher, p_System Lapsed, "
        "p_Leave PHI, p_Non-Recoverable. Nothing you upload here is saved anywhere "
        "beyond this browser session."
    ),
)
st.sidebar.divider()

st.sidebar.header("Success-rate assumptions")
st.sidebar.caption(
    "Adjust the assumed success rate per cancellation type x contact method below; "
    "defaults are a reasonable starting point."
)

uplift = {}
for t in CANCEL_TYPES:
    if t == "Non-Recoverable":
        uplift[t] = {"digital": 0.0, "digital_discount": 0.0, "phone": 0.0, "phone_discount": 0.0}
        st.sidebar.caption(f"\"{t}\" is defined as unrecoverable — all 4 success rates are fixed at 0.")
        continue
    with st.sidebar.expander(f"\"{t}\" success rates", expanded=False):
        uplift[t] = {
            a: st.slider(
                f"{ACTION_LABEL[a]}", 0.0, 1.0, DEFAULT_UPLIFT[t][a], 0.01,
                key=f"uplift_{t}_{a}",
            )
            for a in ACTIONS
        }

st.sidebar.divider()
value_horizon_months = st.sidebar.slider(
    "Value horizon: how many months of premium is a saved policy worth?",
    1, 24, 6, 1,
    help=(
        "Nobody here knows the real average tenure of a policy that's successfully "
        "retained — 12 months is just a starting assumption, not a known fact. If your "
        "data suggests people who get saved typically stick around ~3 more months (or "
        "24), move this slider and every dollar figure below recalculates."
    ),
)
st.sidebar.divider()
min_ev = st.sidebar.slider(
    "Minimum expected net value to recommend any contact ($)",
    0.0, 20.0, 10.0, 0.5,
    help=(
        "One bar for all 4 actions — digital, digital + incentive, phone, phone + incentive. "
        "A channel is only recommended once its own expected net value clears this bar. "
        "Raw cost alone (as low as $0.10 for digital) would otherwise recommend messaging "
        "almost everyone; raising this keeps every channel selective instead of spammy, and "
        "since it applies to phone too, it's the one control that actually caps 'total "
        "policies to contact', not just the digital ones."
    ),
)
st.sidebar.caption(
    f"Cost assumptions: policy value = this policy's own premium over the next "
    f"{value_horizon_months} month{'s' if value_horizon_months != 1 else ''} (adjustable above) | "
    "phone cost \\$20 (official) | digital cost \\$0.10 (official) | discount capped at 12% of "
    "annual premium (official, doesn't move with the slider above)"
)

st.sidebar.divider()
min_primary_risk_sidebar = st.sidebar.slider(
    "Minimum primary risk probability to consider for contact",
    0.0, 1.0, 0.50, 0.01,
    help=(
        "Policies below this probability are dropped from the whole dashboard before "
        "anything else is calculated — not just from the risk list below, but from every "
        "KPI, table and chart. Use this to test 'what if we only bothered with policies "
        "the model is at least X% confident are at risk?' Leave at 0 to consider everyone; "
        "the cost/value formula already down-weights low-probability policies on its own, "
        "so this is an extra, optional sanity filter on top of that, not a replacement for it."
    ),
)

csv_source = uploaded_file if uploaded_file is not None else DEFAULT_CSV_PATH

if uploaded_file is None and not os.path.isfile(DEFAULT_CSV_PATH):
    st.info("Upload a scored CSV using the sidebar to get started.")
    st.stop()

try:
    latest = load_scores(csv_source)
except ValueError as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"Couldn't read that CSV: {e}")
    st.stop()

# ============ Core calculation: probabilities -> recommended action -> expected value ============
probs = latest[[f"p_{t}" for t in CANCEL_TYPES]].copy()
probs.columns = CANCEL_TYPES

latest["recommended_action"], latest["expected_net_value"] = decide_actions(
    probs, latest["MONTHLY_PREMIUM"], uplift, min_ev, value_horizon_months
)
latest["primary_type"] = probs.idxmax(axis=1).values
latest["primary_risk"] = probs.max(axis=1).values

# Sidebar-level "who's even eligible for contact" filter. This does NOT shrink the book
# itself — "Active policies" always reflects every policy in the CSV. It only limits which
# policies are considered when counting/valuing ACTIONS: everything below the threshold is
# treated the same as a policy the formula itself decided not to act on.
n_total = len(latest)
eligible = latest[latest["primary_risk"] >= min_primary_risk_sidebar]
n_dropped_by_risk_filter = n_total - len(eligible)

# ============ KPI row ============
acted = eligible[eligible["recommended_action"] != NO_ACTION_LABEL]
total_env = acted["expected_net_value"].sum()
n_phone_discount = (eligible["recommended_action"] == ACTION_LABEL["phone_discount"]).sum()
n_phone_plain = (eligible["recommended_action"] == ACTION_LABEL["phone"]).sum()
n_phone = n_phone_discount + n_phone_plain
n_digital_discount = (eligible["recommended_action"] == ACTION_LABEL["digital_discount"]).sum()
n_digital_plain = (eligible["recommended_action"] == ACTION_LABEL["digital"]).sum()
n_digital = n_digital_discount + n_digital_plain

st.markdown(
    f"""
<div style="margin: 4px 0 18px 0;">
  <div style="font-size:2.1rem; font-weight:800; color:{INK_PRIMARY}; line-height:1.2;">
    Potential cancellations over the next 3 months
  </div>
  <div style="display:inline-block; margin-top:10px; padding:5px 16px; border:1.5px solid #4a3aa7;
              border-radius:6px; font-size:0.95rem; color:{INK_SECONDARY};">
    Demo dataset: 20,000 mock scored policies (not live HBF members)
  </div>
</div>
""",
    unsafe_allow_html=True,
)
if min_primary_risk_sidebar > 0:
    st.caption(
        f"Sidebar filter active: policies below {min_primary_risk_sidebar:.0%} primary risk "
        f"probability ({n_dropped_by_risk_filter:,} of {n_total:,}) are excluded from contact "
        "consideration below — \"Active policies\" still counts the whole book."
    )
k1, k2, k3 = st.columns(3)
k1.metric("Active policies", f"{n_total:,}")
k2.metric("Policies to contact", f"{len(acted):,}",
          f"{len(acted)/n_total:.1%} of active policies" if n_total else None)
k3.metric("Total expected net value / month", f"${total_env:,.0f}")

k5, k6 = st.columns(2)
k5.metric("Contacted by phone", f"{n_phone:,}",
          f"incl. {n_phone_discount} with a discount" if n_phone else None)
k6.metric("Contacted digitally", f"{n_digital:,}",
          f"incl. {n_digital_discount} with a discount" if n_digital else None)
st.caption(
    "Adjust the success-rate assumptions or minimum expected net value in the sidebar and "
    "these numbers recalculate live."
)

st.divider()

# ============ Table: what makes up the $ total ============
st.subheader("Where the total expected net value comes from")
st.caption(
    "Breaks the headline 'Total expected net value / month' figure down by "
    "recommended action, so it's clear which action is driving the number."
)

breakdown_rows = []
for label in [ACTION_LABEL["digital"], ACTION_LABEL["digital_discount"], ACTION_LABEL["phone"], ACTION_LABEL["phone_discount"]]:
    subset = eligible[eligible["recommended_action"] == label]
    n = len(subset)
    total = subset["expected_net_value"].sum()
    avg = subset["expected_net_value"].mean() if n else 0.0
    breakdown_rows.append({
        "Recommended action": label,
        "Policies": n,
        "Total expected net value": total,
        "Avg. expected net value / policy": avg,
    })
breakdown_rows.append({
    "Recommended action": "Total (contacted)",
    "Policies": len(acted),
    "Total expected net value": total_env,
    "Avg. expected net value / policy": (total_env / len(acted)) if len(acted) else 0.0,
})
breakdown_df = pd.DataFrame(breakdown_rows)

st.dataframe(
    breakdown_df.style.format({
        "Policies": "{:,}",
        "Total expected net value": "${:,.2f}",
        "Avg. expected net value / policy": "${:,.2f}",
    }),
    width="stretch",
    hide_index=True,
)

st.divider()

# ============ Table: cancellation type x recommended action ============
st.subheader("Which cancellation types benefit from an incentive?")
st.caption(
    "Rows are the model's primary cancellation type, columns are the recommended action."
)

action_col_order = [
    ACTION_LABEL["digital"], ACTION_LABEL["digital_discount"],
    ACTION_LABEL["phone"], ACTION_LABEL["phone_discount"],
]
crosstab = pd.crosstab(eligible["primary_type"], eligible["recommended_action"])
crosstab = crosstab.reindex(index=CANCEL_TYPES, columns=action_col_order, fill_value=0)
crosstab["Total contacted"] = crosstab.sum(axis=1)
crosstab.index.name = "Primary cancellation type"

st.dataframe(
    crosstab.style.format("{:,}"),
    width="stretch",
)
_incentive_cols = [ACTION_LABEL["digital_discount"], ACTION_LABEL["phone_discount"]]
crosstab["Any incentive"] = crosstab[_incentive_cols].sum(axis=1)
_best_incentive_type = crosstab["Any incentive"].idxmax() if crosstab["Any incentive"].sum() > 0 else None
if _best_incentive_type:
    st.caption(
        f"Under the current sidebar assumptions, **{_best_incentive_type}** has the most policies "
        f"recommended for an incentive, digital or phone "
        f"({crosstab.loc[_best_incentive_type, 'Any incentive']:,} of them) — "
        "that's the cancellation type where an incentive is doing the most work."
    )
crosstab = crosstab.drop(columns=["Any incentive"])

st.divider()

# ============ Filters + risk list ============
st.subheader("Risk list")

col_a, col_b = st.columns(2)
type_filter = col_a.multiselect(
    "Primary risk type",
    options=CANCEL_TYPES,
    default=CANCEL_TYPES,
)
_action_options = sorted(eligible["recommended_action"].unique())
action_filter = col_b.multiselect(
    "Recommended action",
    options=_action_options,
    default=[a for a in _action_options if a != NO_ACTION_LABEL],
)
st.caption(
    "This list (and the two tables above) already reflect the sidebar's \"Minimum primary "
    "risk probability to consider for contact\" filter — \"Active policies\" above is the "
    "only number that always counts the whole book."
)

filtered = eligible[
    eligible["primary_type"].isin(type_filter)
    & eligible["recommended_action"].isin(action_filter)
].sort_values("expected_net_value", ascending=False)

display_cols = (
    ["POLICY_HASH", "primary_type", "primary_risk", "recommended_action", "expected_net_value"]
    + [f"p_{t}" for t in CANCEL_TYPES]
    + ["MONTHLY_PREMIUM"]
    + [c for c in OPTIONAL_DISPLAY_COLS if c in filtered.columns]
)
display_cols = [c for c in display_cols if c in filtered.columns]

missing_optional = [c for c in OPTIONAL_DISPLAY_COLS if c not in latest.columns]
if missing_optional:
    st.caption(
        f"Note: the CSV doesn't include optional column(s) {missing_optional} — the list is "
        "missing those filter/display fields, but the recommendation and dollar figures are unaffected."
    )

fmt = {"primary_risk": "{:.1%}", "MONTHLY_PREMIUM": "${:.0f}", "expected_net_value": "${:.2f}"}
fmt.update({f"p_{t}": "{:.1%}" for t in CANCEL_TYPES})


def highlight_by_action(row):
    """Row background = the recommended action's color, tinted light so text stays
    readable. 'No action' rows get no color — nothing to flag there."""
    color = ACTION_ROW_TINT.get(row["recommended_action"])
    style = f"background-color: {color}" if color else ""
    return [style] * len(row)


# Pandas caps how many cells its Styler will color at once (default 262,144) as a safety
# limit, not a hard technical ceiling — real teammate exports can be much bigger than the
# small test file, so raise the cap to fit whatever's actually being displayed.
_n_style_cells = filtered[display_cols].shape[0] * max(filtered[display_cols].shape[1], 1)
if _n_style_cells > pd.get_option("styler.render.max_elements"):
    pd.set_option("styler.render.max_elements", _n_style_cells + 1000)

st.dataframe(
    filtered[display_cols].style.format(fmt).apply(highlight_by_action, axis=1),
    width="stretch",
    height=420,
)
st.caption(
    f"Showing {len(filtered):,} / {len(eligible):,} eligible policies "
    f"({n_total:,} in the whole book), sorted by expected net value. "
    f"Row color = recommended action ({', '.join(ACTION_ROW_TINT.keys())}); "
    f"\"{NO_ACTION_LABEL}\" rows are left uncolored."
)

csv_out = filtered[display_cols].to_csv(index=False).encode("utf-8")
st.download_button("Download current list (CSV)", csv_out, "risk_list.csv", "text/csv")

st.divider()

# ============================================================
# Explainer: how a recommendation is calculated (for non-technical readers)
# ============================================================
st.subheader("How we decide what to do")

STEP_HTML = """
<div style="display:flex; flex-wrap:wrap; gap:0; align-items:stretch; margin:8px 0 20px 0;">
{steps}
</div>
"""
STEP_BOX = """
<div style="flex:1; min-width:150px; background:{surface}; border:1px solid {gridline};
            border-radius:10px; padding:14px 16px; position:relative;">
  <div style="font-size:12px; color:{muted}; font-weight:600; letter-spacing:0.02em;">STEP {n}</div>
  <div style="font-size:15px; color:{ink}; font-weight:600; margin-top:4px;">{title}</div>
  <div style="font-size:13px; color:{secondary}; margin-top:6px; line-height:1.4;">{body}</div>
</div>
"""
ARROW = """
<div style="display:flex; align-items:center; justify-content:center; min-width:28px;
            color:{muted}; font-size:20px;">&#8594;</div>
"""

steps_data = [
    ("4 risk probabilities", "The model's own output for this policy: "
     "P(Switcher), P(System&nbsp;Lapsed), P(Leave&nbsp;PHI), P(Non-Recoverable)."),
    ("&times; success-rate assumption", "Each type &times; how likely a given contact "
     "method is to actually save it (the sidebar sliders — a team assumption, not a "
     "known fact)."),
    ("= expected chance saved", "Adding that up across all 4 types gives one action's "
     "expected chance of preventing cancellation."),
    ("&times; value, &minus; cost", f"&times; this policy's own premium over the next "
     f"{value_horizon_months} months (the sidebar's \"value horizon\" slider, less any "
     "discount given) &minus; the cost of that contact method (&#36;20 phone, &#36;0.10 digital)."),
    ("= expected net value", "The dollar result for that one action. Repeat for all 4 "
     "actions (digital, digital+incentive, phone, phone+incentive), keep the highest "
     "positive one (or \"No action\" if none clear the bar)."),
]

steps_html = ""
for i, (title, body) in enumerate(steps_data, start=1):
    steps_html += STEP_BOX.format(
        n=i, title=title, body=body,
        surface=SURFACE, gridline=GRIDLINE, muted=INK_MUTED,
        ink=INK_PRIMARY, secondary=INK_SECONDARY,
    )
    if i < len(steps_data):
        steps_html += ARROW.format(muted=INK_MUTED)

st.markdown(STEP_HTML.format(steps=steps_html), unsafe_allow_html=True)

# Worked example recomputed live from the actual sidebar values, so it always matches
# whatever "value horizon" / success-rate assumptions are currently set. Walks through
# all 4 real actions so it's clear how "Digital + incentive" stacks up against the other 3.
_ex_monthly = 200.0
_ex_prob = 0.30
_ex_type = "System Lapsed"
_ex_horizon_value = _ex_monthly * value_horizon_months
_ex_annual = _ex_monthly * 12
_ex_discount_cost = _ex_annual * MAX_DISCOUNT_PCT
_ex_disc_value = max(_ex_horizon_value - _ex_discount_cost, 0)

_ex_ev = {}
for _a in ACTIONS:
    _rate = uplift[_ex_type][_a]
    _value = _ex_disc_value if _a in ("digital_discount", "phone_discount") else _ex_horizon_value
    _ex_ev[_a] = _ex_prob * _rate * _value - ACTION_COST[_a]
_ex_winner_key = max(_ex_ev, key=_ex_ev.get)
_ex_winner = ACTION_LABEL[_ex_winner_key]

st.markdown(
    f"""
<div style="background:{SURFACE}; border:1px solid {GRIDLINE}; border-radius:10px;
            padding:14px 18px; font-size:13px; color:{INK_SECONDARY}; line-height:1.6;">
<b style="color:{INK_PRIMARY};">Worked example</b> (recalculated live from your current
sidebar settings) — a policy with a {_ex_prob:.0%} chance of being "{_ex_type}" and a
&#36;{_ex_monthly:,.0f} monthly premium, valued over the {value_horizon_months}-month horizon
(&#36;{_ex_horizon_value:,.0f}; discounted value if an incentive is used: &#36;{_ex_disc_value:,.0f},
after the 12% &times; &#36;{_ex_annual:,.0f} annual-premium discount of &#36;{_ex_discount_cost:,.0f}):<br>
&bull; <b>Digital only</b>: {_ex_prob:.0%} &times; {uplift[_ex_type]['digital']:.0%} success &times;
&#36;{_ex_horizon_value:,.0f} &minus; &#36;0.10 contact cost = <b>&#36;{_ex_ev['digital']:,.2f}</b><br>
&bull; <b>Digital + incentive</b>: {_ex_prob:.0%} &times; {uplift[_ex_type]['digital_discount']:.0%} success &times;
&#36;{_ex_disc_value:,.0f} &minus; &#36;0.10 = <b>&#36;{_ex_ev['digital_discount']:,.2f}</b><br>
&bull; <b>Phone only</b>: {_ex_prob:.0%} &times; {uplift[_ex_type]['phone']:.0%} success &times;
&#36;{_ex_horizon_value:,.0f} &minus; &#36;20 contact cost = <b>&#36;{_ex_ev['phone']:,.2f}</b><br>
&bull; <b>Phone + incentive</b>: {_ex_prob:.0%} &times; {uplift[_ex_type]['phone_discount']:.0%} success &times;
&#36;{_ex_disc_value:,.0f} &minus; &#36;20 = <b>&#36;{_ex_ev['phone_discount']:,.2f}</b><br>
&bull; <b>{_ex_winner}</b> wins here. Because the incentive discount is a fixed dollar cost
regardless of channel, attaching it to the cheap digital channel instead of a phone call
can win when the discount's boost to success rate is large enough relative to the
$19.90 contact-cost gap between the two channels — move the sidebar sliders and this can flip.
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div style="margin-top:14px; font-size:13px; color:{INK_SECONDARY};">
<b style="color:{INK_PRIMARY};">Row colors in the list above:</b>
<span style="background:{ACTION_ROW_TINT[ACTION_LABEL['digital']]}; padding:2px 8px;
             border-radius:4px; margin:0 4px;">{ACTION_LABEL['digital']}</span>
<span style="background:{ACTION_ROW_TINT[ACTION_LABEL['digital_discount']]}; padding:2px 8px;
             border-radius:4px; margin:0 4px;">{ACTION_LABEL['digital_discount']}</span>
<span style="background:{ACTION_ROW_TINT[ACTION_LABEL['phone']]}; padding:2px 8px;
             border-radius:4px; margin:0 4px;">{ACTION_LABEL['phone']}</span>
<span style="background:{ACTION_ROW_TINT[ACTION_LABEL['phone_discount']]}; padding:2px 8px;
             border-radius:4px; margin:0 4px;">{ACTION_LABEL['phone_discount']}</span>
<span style="padding:2px 8px; margin:0 4px; border:1px dashed {GRIDLINE}; border-radius:4px;">
{NO_ACTION_LABEL} (uncolored)</span>
</div>
""",
    unsafe_allow_html=True,
)
