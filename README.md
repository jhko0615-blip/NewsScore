# 🎈 Blank app template

A simple Streamlit app template for you to modify!

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. **API key (Anthropic)**  
   Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` to your key.  
   **Never commit `.env`** — it is listed in `.gitignore`.  
   If a key was ever exposed (chat, screenshot, or accidental commit), **revoke it immediately** in the [Anthropic Console](https://console.anthropic.com/) and create a new key.

3. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
