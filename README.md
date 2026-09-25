# NetWatch NMS (Network Monitoring System)

An automated network monitoring dashboard and alert system built with FastAPI, SQLite, and Telegram notifications.

---

## Problem Statement


---

## Screenshot


---

## Architecture Diagram


---

## Tech Stack & Why
- **Backend:** FastAPI (Python)
- **Database:** SQLite & SQLAlchemy
- **Templating:** Jinja2
- **Scheduler:** APScheduler (for periodic ICMP/ping checks)
- **Alerting:** `python-telegram-bot`
- **Containerization:** Docker & Docker Compose

---

## Setup & Running

### Local Environment
```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create environment file
cp .env.example .env

# 4. Run application
uvicorn app.main:app --reload
