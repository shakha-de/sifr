# sifr

Sifr is a Streamlit-based grading assistant for exploring student submissions, attaching feedback, and exporting annotated results. It scans uploaded archives, indexes exercises, and keeps track of points and reusable error codes so reviewers can focus on the actual review instead of file wrangling.

## Prerequisites
- Python 3.13 or newer when running locally
- `tar`, `gzip`, and other standard Unix tools for handling uploaded archives
- Access to the submission archives you want to review

## Getting Started
We strongly recommend isolating the environment with either [`uv`](https://github.com/astral-sh/uv) or Docker. Both capture dependencies precisely and avoid accidental differences across machines. Direct `pip` usage is available but should be treated as a fallback.

### Option 1: `uv` (recommended if you already have LaTeX distribution on your system)
1. Install `uv` if needed: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Sync dependencies into an isolated environment:
	```bash
	uv sync
	```
3. Launch the Streamlit app:
	```bash
	uv run streamlit run app/🖎_Korrektur.py
	```

`uv` reads `pyproject.toml`, keeps lock files up-to-date, and lets you run `uv run pytest` for the test suite.

### Option 2: Docker (recommended for reproducibility)
1. Build the image:
	```bash
	docker build -t sifr .
	```
2. Run the container, forwarding the Streamlit port and mounting a data directory for uploaded archives:
	```bash
	docker run --rm -p 8501:8501 -v "$PWD/data:/app/data" -e SIFR_DATA_DIR=/app/data sifr
	```

This keeps host dependencies clean and makes it easy to ship a ready-to-run image.

### Option 3: Classic `pip` (fallback)
1. Create and activate a virtual environment (example shown for `venv`):
	```bash
	python -m venv .venv
	source .venv/bin/activate
	```
2. Install dependencies:
	```bash
	pip install -r requirements.txt
	```
3. Serve the app with Streamlit:
	```bash
	streamlit run app/🖎_Korrektur.py
	```

## Configuration
- `SIFR_DATA_DIR` (optional): set to override where extracted archives, feedback, and generated assets are stored. Defaults to `./data/` inside the project.
- Place `.tar.gz` archives of submissions into the configured data directory or upload them through the UI.

## Running the App
- Once started, open `http://localhost:8501` in your browser.
- Use the sidebar to upload an archive, select exercises, and record feedback.

## Testing
- Run the test suite with your preferred workflow (`uv run pytest`, `docker run ... pytest`, or `pytest` inside an activated virtual environment).

## Project Layout
- `app/` — Streamlit app, database helpers, utility functions, configuration
- `test/` — Pytest-based regression tests for critical paths
- `Dockerfile` — Container definition for reproducible deployments
- `pyproject.toml` / `requirements.txt` — Python dependency manifests suited for `uv` and `pip`


