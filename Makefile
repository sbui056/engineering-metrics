PYTHON ?= python
REPO_PATH ?= target-repo/FastVideo
DATA := data

.PHONY: setup commits reviews coupling ownership score narrate validate all clean

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

all: narrate validate

clean:
	rm -f $(DATA)/*.parquet
