# email_agent

A Python-based automation agent for managing email workflows using Gmail and Google Sheets.

This project implements a modular email agent that authenticates with Google APIs, sends and receives email via Gmail, and persists or retrieves metadata from Google Sheets. It is designed as a lightweight engine that can be extended into production automation, analytics, or workflow pipelines.

## Features

Core capabilities included in this repository:

- **Google OAuth2 Authentication**  
  Handles OAuth2 flow for Gmail and Google Sheets API access through secure token storage.  

- **Gmail Integration**  
  Send, receive, and process emails programmatically via the Gmail API.

- **Google Sheets Integration**  
  Store, update, and retrieve structured metadata or logs from Google Sheets.

- **Worker Orchestration**  
  A worker module orchestrates asynchronous or scheduled tasks, such as polling for new messages or processing workflows.

- **Modular Structure**  
  Logical separation between authentication (`google_auth.py`), mail operations (`gmailer.py`), data persistence (`sheets_store.py`), and application logic (`worker.py`, `app.py`).

## Architecture

The repository is structured as follows:

```email_agent/
├── app.py # Application entrypoint
├── gmailer.py # Gmail API interface
├── google_auth.py # OAuth2 authentication with Google
├── sheets_store.py # Google Sheets persistence logic
├── worker.py # Task orchestration and workflow logic
├── credentials.json # OAuth client secrets (excluded from source control)
├── token.json # Persisted OAuth tokens generated at runtime
├── requirements.txt # Python dependencies
└── LICENSE # MIT License```



## Requirements

- Python 3.9+
- Installed dependencies from `requirements.txt`
- Google Cloud Project with:
  - Gmail API enabled
  - Google Sheets API enabled
  - OAuth2 credentials (`credentials.json`)

## Setup


```bash
   git clone https://github.com/arbstatistix/email_agent.git
   cd email_agent
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
```

