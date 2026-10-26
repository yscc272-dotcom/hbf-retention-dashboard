# HBF Policy Cancellation Early-Warning Dashboard

Public demo of the hackathon retention dashboard. Bundled data is **20,000 mock scored policies**, not live member records.

Code and data: https://github.com/yscc272-dotcom/hbf-retention-dashboard

## Deploy the live site (Streamlit Community Cloud)

1. Open https://share.streamlit.io/ and sign in with GitHub (`yscc272-dotcom`).
2. Create app → Yup, I have an app → Paste GitHub URL:
   `https://github.com/yscc272-dotcom/hbf-retention-dashboard/blob/main/09_dashboard_presentation.py`
3. Optional custom subdomain: `hbf-retention`
4. Deploy. The public URL will look like `https://hbf-retention.streamlit.app`

## Run locally

```bash
python3 -m venv .venv_dashboard
source .venv_dashboard/bin/activate
pip install -r requirements.txt
streamlit run 09_dashboard_presentation.py
```

Required CSV columns: `POLICY_HASH`, `MONTHLY_PREMIUM`, `p_Switcher`, `p_System Lapsed`, `p_Leave PHI`, `p_Non-Recoverable`.
