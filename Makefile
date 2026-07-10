PYTHON ?= python
REPO_PATH ?= target-repo/FastVideo
DATA := data

.PHONY: setup commits reviews coupling ownership score narrate validate site all clean

setup:
	$(PYTHON) -m pip install -r requirements.txt

# --- Extract (Track A) -------------------------------------------------------
commits: $(DATA)/commits_clean.parquet
$(DATA)/commits_clean.parquet:
	$(PYTHON) scripts/extract_commits.py --repo $(REPO_PATH)

# --- Reviews (Track B) -------------------------------------------------------
reviews: $(DATA)/reviews.parquet
$(DATA)/reviews.parquet:
	$(PYTHON) scripts/fetch_reviews.py

# --- Coupling (Track C) ------------------------------------------------------
coupling: $(DATA)/coupling.parquet
$(DATA)/coupling.parquet: $(DATA)/commits_clean.parquet
	$(PYTHON) scripts/compute_coupling.py

# --- Ownership + survival (Track E) ------------------------------------------
ownership: $(DATA)/ownership_author.parquet
$(DATA)/ownership_author.parquet: $(DATA)/commits_clean.parquet
	$(PYTHON) scripts/compute_ownership.py --repo $(REPO_PATH)

# --- Merge + score -----------------------------------------------------------
score: $(DATA)/scored.parquet
$(DATA)/scored.parquet: $(DATA)/commits_clean.parquet $(DATA)/reviews.parquet $(DATA)/coupling.parquet $(DATA)/ownership_author.parquet
	$(PYTHON) scripts/merge_and_score.py

# --- Narrative (fills one_line_rationale in scored.parquet) -------------------
narrate: score
	$(PYTHON) scripts/narrate.py

# --- Validation harness ------------------------------------------------------
validate:
	$(PYTHON) scripts/validate.py

# --- Static site (after narrate: it fills one_line_rationale in place) --------
# Deploy build: SITE_URL=https://your-host/path make site  (absolute og:image for
# link unfurls). With no SITE_URL, og:image falls back to a relative og.png.
site: narrate
	$(PYTHON) scripts/build_site.py

# --- Publish to GitHub Pages (serves main -> /docs) ---------------------------
# Builds with the public URL baked into og:image, renders the OG card, and
# stages the single-file site into docs/. Then: git add docs && commit && push.
PAGES_URL ?= https://sbui056.github.io/engineering-metrics
deploy: narrate
	SITE_URL=$(PAGES_URL) $(PYTHON) scripts/build_site.py
	$(PYTHON) scripts/render_og.py
	mkdir -p docs
	cp dist/index.html docs/index.html
	cp dist/og.png docs/og.png
	touch docs/.nojekyll

# The one static OG image (crawler-fetched; not a page resource). Dev-only:
# needs playwright. Set SITE_URL when building the site for absolute og:image.
og:
	$(PYTHON) scripts/render_og.py

all: narrate validate site

clean:
	rm -f $(DATA)/*.parquet dist/index.html
