# HBF Policy Cancellation Early-Warning Dashboard

Public demo of the hackathon retention dashboard. Bundled data is **20,000 mock scored policies**, not live member records.

Open the app: after Streamlit Community Cloud is connected, the URL is on the app page.

## Run locally

```bash
python3 -m venv .venv_dashboard
source .venv_dashboard/bin/activate
pip install -r requirements.txt
streamlit run 09_dashboard_presentation.py
```

Required CSV columns: `POLICY_HASH`, `MONTHLY_PREMIUM`, `p_Switcher`, `p_System Lapsed`, `p_Leave PHI`, `p_Non-Recoverable`.
