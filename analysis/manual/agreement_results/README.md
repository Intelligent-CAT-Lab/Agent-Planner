# Inter-rater agreement results

Two fixed raters, binary multi-label coding. The script computes statistics from
the supplied annotations without changing any label. Run
`python3 compute_agreement.py --self-test` to check the math, then
`python3 compute_agreement.py --input-dir . --output-dir agreement_results`.

`summary.csv` reports, per category (and macro mean over categories):
- `raw_agreement` / `raw_agreement_percent` -- observed agreement po = (n00+n11)/n
- `cohen_kappa` -- classic chance-corrected coefficient for two raters
- `gwet_ac1` -- chance-corrected, robust to class skew
- 2x2 counts, paired positives, and 95% cluster-bootstrap intervals for each metric
- `POOLED_BINARY_DECISIONS`: raw agreement over all (case, category) decisions

`subject_level.csv` reports multi-label set agreement across cases:
exact-set-match rate and mean Jaccard overlap of the two raters' positive-label sets.

`disagreements.csv` lists every disagreeing or missing decision.
`manifest.json` records input paths, sha256 hashes, parameters, and formulas.

## Choosing a number to report

Report **raw agreement** (descriptive) alongside a **chance-corrected**
coefficient. Here the labels are highly skewed (one class dominates most
categories), which drives Cohen's kappa (and Krippendorff's alpha / Scott's pi)
toward 0 or leaves it undefined even when raw agreement is high -- the documented
"kappa paradox" (Feinstein & Cicchetti 1990; Gwet 2008). **Gwet's AC1** does not
inflate its chance term under skew and stays defined; it is the recommended
chance-corrected coefficient in this regime. Per-category values are primary;
the macro mean is an average of coefficients, not itself a coefficient.

Missing labels are never treated as negatives: only decisions both raters scored
contribute to a category. Agreement measures reproducibility of these
annotations, not their correctness or validity.
