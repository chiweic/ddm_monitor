# DDM Monitor

DDM Monitor is a small FastAPI service that periodically scrapes news articles from the Dharma Drum Mountain (DDM) website. The scraped posts are stored as JSON files under the `data` directory and exposed through a `/posts` API endpoint.

## Installation

1. Ensure Python 3.8+ is installed.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

The project only lists `playwright` explicitly but requires packages like `fastapi`, `httpx`, `selectolax` and `uvicorn`. Install them if not already available.

## Usage

Start the API server with Uvicorn:

```bash
uvicorn main:app --reload
```

The server will begin scraping news when it starts. You can then access the posts at `http://localhost:8000/posts`.

Alternatively, you may run the module directly with Python:

```bash
python -m uvicorn main:app --reload
```

## Configuration

Configuration is done through constants in `main.py`:

- `ENTRY_URL` – starting URL for scraping DDM news.
- `SCRAPE_INTERVAL` – time between scrapes in seconds (default `86400`, once a day).
- `DATA_DIR` – base directory for storing scraped data (`data/`).
- `CURRENT_DIR` – directory that holds the latest `posts.json`.
- `ARCHIVE_DIR` – directory where older posts are archived.
- `POSTS_FILE` – current posts file path.
- `POSTS_NEW_FILE` – temporary file used during updates.

Modify these values in `main.py` if you need to change scraping behaviour or storage locations.

## Directory Structure

```
.
├── app/
│   └── scraper.py
├── data/
│   ├── archive/
│   └── current/
├── main.py
└── requirements.txt
```

The `data/current` folder holds the latest scraped posts, while `data/archive` keeps timestamped backups.

