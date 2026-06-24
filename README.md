# Dash

A local dashboard that pulls your activity data from Garmin Connect and displays running, strength, and cycling trends in your browser. Also integrates with Power of 10 for race results and athlete comparisons.

## Requirements

- Python 3.12+
- A Garmin Connect account
- Homebrew (to install Python 3.12 if needed)

## Setup

### 1. Install Python 3.12

If you don't have it:

```bash
brew install python@3.12
```

### 2. Create the virtual environment

```bash
cd /path/to/Garmin
python3.12 -m venv .venv
```

### 3. Install dependencies

```bash
.venv/bin/pip install git+https://github.com/cyberjunky/python-garminconnect.git python-dotenv
```

### 4. Add your Garmin credentials

```bash
cp .env.example .env
```

Edit `.env` with your details:

```
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=yourpassword
```

The `.env` file is gitignored and never committed.

## Usage

### Start the dashboard

```bash
.venv/bin/python serve.py
```

Then open **http://localhost:8080** in your browser.

The first load reads the existing `activities.json` if present. Click **Sync Garmin** in the top-right to fetch the latest 500 activities from Garmin Connect.

### Fetch activities manually

```bash
.venv/bin/python fetch_activities.py        # last 20 (default)
.venv/bin/python fetch_activities.py 500    # last 500
```

This saves `activities.json` in the project folder. Run this before starting the server if you want data ready on first load.

### Authentication

On first run you'll be prompted to log in. A token is saved to `.garmin_tokens/` so subsequent runs don't require your password. If your session expires, delete `.garmin_tokens/` and run again.

## Dashboard tabs

| Tab | What's shown |
|---|---|
| **Overview** | Weekly volume by type, activity breakdown donut, monthly running distance |
| **Running** | Pace, HR, weekly distance, power, cadence — all outdoor + treadmill runs |
| **Strength** | Sessions per week, duration trend, calories per session |
| **Cycling** | Distance and HR per ride — outdoor, indoor, MTB |

## Exporting data for Claude

Each tab (Running, Strength, Cycling) has **⬇ CSV** and **⬇ JSON** export buttons in the top-right corner of the activity table. Click either to download the filtered dataset for that activity type.

To analyse in Claude:
1. Export the JSON file from the relevant tab
2. Open a new Claude conversation
3. Attach or paste the JSON and ask your question — e.g. *"What trends do you see in my running pace over the last 3 months?"*

## File overview

```
Garmin/
├── .env                  # Your credentials (gitignored)
├── .env.example          # Credentials template
├── .gitignore
├── activities.json       # Cached activity data (gitignored)
├── dashboard.html        # The dashboard UI
├── fetch_activities.py   # Pulls data from Garmin Connect
├── serve.py              # Local web server
└── .venv/                # Python virtual environment (gitignored)
```

## Troubleshooting

**429 rate limit warnings on login** — normal, the library tries multiple login methods and falls back automatically. If it keeps failing, wait a few minutes and try again.

**`activities.json` not found on first load** — run `fetch_activities.py` once before starting the server, or click Sync Garmin in the browser.

**Token expired / auth error** — delete the `.garmin_tokens/` folder and re-run the fetch script to log in fresh.
