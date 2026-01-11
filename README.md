# jnuaigent-beta

## Admin Streamlit UI

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r admin/requirements.txt
```

### Run
```bash
export BACKEND_URL=http://localhost:8000
# Optional: export ADMIN_PASSWORD=your-password
streamlit run admin/admin_app.py
```

If `ADMIN_PASSWORD` is not set, the admin UI runs in open mode and shows a warning banner.
