# N1 — query language, script and LLM commercial recommendations (code)

Code of study N1, reported in *Query language, script and commercial recommendations from large language models: A
pre-registered three-arm audit (English, Bangla, Banglish) in the Bangladeshi market* by Md Tahidul Islam and
Maksuda Akter (Department of Computer Science and Engineering, CCN University of Science & Technology, Comilla,
Bangladesh). Registration: osf.io/n72qs. Data: https://doi.org/10.5281/zenodo.23076544 (the Zenodo record is published when the article is accepted). Article: [reference added at publication].

## Contents

- **Root folder** — the study's own scripts, in the layout they ran in:
  - `n1_pipeline.py`, the collection runner: call planner, cache-first caller, deterministic outcome coder,
    extractor driver, cost ledger, run-window log and the `release` command that produced the released records. It
    makes no network call unless `--go` is passed and its preflight passes, and it reads the API key only from the
    `GATEWAY_KEY` environment variable;
  - `make_translit.py`, the mechanical transliteration arm (`bl_translit`);
  - the tools that built and checked the query files, the raters' Banglish renderings, the labelling and
    adjudication pages, and the alias and classification tables;
  - the extraction, agreement and validation scripts (for example `check_extraction.py`, `contest_score.py`,
    `e2_agreement.py`, `round2_agreement.py`, `d4_cut_validation.py`, `alt_test.py` with `test_alt_test.py`);
  - the registered analyses (`n1_analysis.py`, which calls `n1_glmm.R`; `n1_robustness.py`, `n1_supplement.py`,
    `n1_report.py`, `n1_c1_sensitivity.py`, `registered_descriptives.py`), their validation on synthetic data
    (`n1_synth.py`, `n1_calibrate.py`) and the registration-versus-execution audit (`n1_plan_audit.py`).
- **`posthoc/`** — the post-hoc tests and null calibration declared in record 53 and reported in record 54
  (`n1_posthoc.py`), its validation harness (`n1_posthoc_tests.py`, `validation/run_validation.sh`) and the
  calibration runner (`run_cal.sh`).
- **`posthoc2/`** — items C, D and E declared in record 56 and reported in records 57 and 58 (`n1_posthoc2.py`):
  the second calibration of record 53's interpretation rule, each rater against the consensus of the other two, and
  the detection limits of the refusal and transliterated-arm contrasts; its validation harness
  (`n1_posthoc2_tests.py`); the stage runner (`run_posthoc2.sh`) and the script that resumed its last two stages
  after a worker restart (`resume_E.sh`); and `checkpoint.sh` (release copy; see the data's README), which committed the partial outputs to a branch
  during the long runs. The driver imports `posthoc/n1_posthoc.py` read-only, so the two folders sit side by side,
  and it refuses real data unless `--registration` names a registration that holds its declaration record. The
  released copy (`PREREGISTRATION-RELEASE.md`, in the data) holds it; the runner scripts name the study's working
  copy (`../registration/prereg.md`).
- **`exploratory/`** — the descriptive analyses declared in the records of 28 September 2026.
- **`paper/`** — the scripts that build the article's tables and figures from the analysis outputs (`build_tables.py`,
  `build_table7.py`, `make_figures.py`; each takes the results folder and an output folder as its two arguments).
  `build_table7.py` keeps its working name: the table of sensitivity analyses it builds is Table A in S3 File.
- **`config/models.public.json`** — the released model configuration (the gateway address is redacted).

Every script states its purpose, inputs and usage in its header, with the registration section or dated record it
implements.

## Requirements

Python 3.11 (the study ran 3.11.15) with numpy 2.4.4, pandas 3.0.2, scipy 1.17.1 and statsmodels 0.15.0; R 4.3.3
with lme4 1.1.35.1 and jsonlite for the mixed models. The spreadsheet tools also need openpyxl, `make_translit.py`
needs aksharamukha 2.3, and the figure script needs matplotlib and Pillow.

## Reproducing the analyses

1. Download the data from Zenodo (https://doi.org/10.5281/zenodo.23076544). Unzip the four `runs` archives into a folder named `runs/` here and
   move the files of `runs-top-level/` into it; put the contents of the frozen-inputs, queries-and-tables,
   labelling and results archives into this root folder, which is the flat layout the scripts expect; copy
   `config/models.public.json` to `models.json`.
2. `python3 n1_pipeline.py selftest` runs the offline end-to-end test on synthetic responses.
3. `python3 n1_analysis.py --root .` recomputes the registered analyses (see its header for the options). It first
   checks the SHA-256 of its 15 inputs (the query set, the final coded table, the primary extraction and the persona
   and usage files); the released copies match all 15.

Re-running the data collection is not needed for any result: every request body, parameter and response is in the
data, and every model is publicly reachable.

## Not included

`gateway_check.py` (a connection test for the private routing gateway), `release_registration.py` (it builds the
released registration copy, the article's S1 File, from the authors' working registration file, which is not
public; the released copy is in the data), and the gateway configuration files `models.json` and
`models.e6-fallback.json` (`config/models.public.json` is the released configuration).

## Licence

MIT (see `LICENSE`). The data are released under CC BY 4.0 at Zenodo.
