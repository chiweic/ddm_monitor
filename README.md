# data_ingest

data_ingest is a small FastAPI service that does the followings:
1. Posts: periodically scrapes news articles (Q&A) from the Dharma Drum Mountain (DDM) website. 
2. Books: ingest books contents from designated folders (moved)
3. Audios: so-called postable audio recordings publicly available also via DDM website (moved)
4. Videos: youtube videos that containing Master Sheng Yan and his interview with anchor speakers (moved)
5. Videos: other youtube videos that comes from official channels from DDM (moved)

# data storage

1. The scraped posts are stored as JSON files under the `data/posts` directory
2. Simiarly for books, audios and videos under data/books, data/audios and data/videos

# data transform

What additional features or work performed on these data are:

1. Chunking: producing meaningful size or semanticlly related that are suitable for further processing. 
2. On each chunk, we also try to produce "Topic", "Summary", "Name Entity" and "Key Phrases" extraction
3. For the Audios/Videos, we do perform speech-to-text, and then following chunking etc.,


# Exposed API endpoints

1. Initial ingest of data are already part when the system start. (so warmup take times)
2. Additional online ingest are exposed via `/posts`
3. Read-only access on chunks (associated with the original doc) are exposed via `/chunks`

**noted. the Retrieval and Chat endpoint from other runtime will consume chunks via this interface**

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

