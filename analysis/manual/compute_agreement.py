#!/usr/bin/env python3
"""Two-rater binary multi-label inter-rater agreement, standard library only.

Usage: python3 compute_agreement.py --input-dir . --output-dir agreement_results
Reads RU.csv and UR.csv by default. This script never edits the annotations.

Design
------
Two fixed raters assign, per case, a set of binary labels (each category is an
independent 0/1 decision). Agreement is computed per category and then
aggregated.

Metrics (per category, over cases where BOTH raters gave a 0/1 value):
  * raw_agreement  -- observed agreement  po = (n00 + n11) / n
  * cohen_kappa    -- chance-corrected, per-rater marginals (classic 2-rater coef)
  * gwet_ac1       -- chance-corrected, robust to the prevalence/skew paradox

Why two coefficients. The label distribution here is highly skewed (one class
dominates most categories). Under skew, Cohen's kappa (and Krippendorff's alpha,
Scott's pi) are driven toward 0 or become undefined even when raw agreement is
high -- the well-documented "kappa paradox" (Feinstein & Cicchetti 1990;
Gwet 2008). Gwet's AC1 uses a chance term that does not inflate under skew and
stays defined; it is the recommended coefficient in exactly this regime. We
report raw agreement, kappa (expected by most readers), and AC1 (the reliable
chance-corrected number) side by side.

  Cohen kappa:  pe = p1a*p1b + (1-p1a)*(1-p1b);  kappa = (po-pe)/(1-pe)
  Gwet  AC1:    pi1 = (p1a+p1b)/2; pe = 2*pi1*(1-pi1);  ac1 = (po-pe)/(1-pe)
  where p1a, p1b are each rater's proportion of positive ratings.

AC1 is always defined for n>0 (1-pe >= 0.5). Kappa is undefined only in the
degenerate case where both raters give the same constant label to every case
(pe = 1); AC1 correctly returns 1 there. Missing labels never become negatives:
only cases both raters scored contribute to a category.

Multi-label (subject-level) agreement treats each case's positive labels as a
set: mean Jaccard overlap and exact-set-match rate across cases.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

MISSING = {'', '?', 'na', 'n/a', 'nan', 'none', 'null', '.'}
CATEGORIES = {
    'RU': ['bad_guidance', 'nondeterminism', 'brittle_vanilla', 'incomplete_compliance', 'secondary_distraction'],
    'UR': ['drift_correction', 'refocusing', 'task_specific_guidance', 'progressive_correction'],
}


def parse_label(value):
    s = str(value).strip().lower() if value is not None else ''
    if s in MISSING:
        return None
    if s in {'0', '0.0'}:
        return 0
    if s in {'1', '1.0'}:
        return 1
    raise ValueError(f'Invalid binary annotation {value!r}; expected 0/1 or missing')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        raw_fields = reader.fieldnames
        fields = [name if name else f'__unnamed_column_{i+1}' for i, name in enumerate(raw_fields or [])]
        reader.fieldnames = fields
        if not fields or len(set(fields)) != len(fields):
            raise ValueError(f'{path}: missing or duplicate header names')
        rows = list(reader)
    for i, row in enumerate(rows, 1):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'{path}: ragged data row {i}')
    return fields, rows


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['' if k.startswith('__unnamed_column_') else k for k in fields])
        for row in rows:
            w.writerow([row.get(k) for k in fields])


def category_stats(units):
    """units: iterable of (rater1, rater2), each 0/1/None. Returns per-category metrics."""
    pairs = [(a, b) for a, b in units if a is not None and b is not None]
    n = len(pairs)
    n11 = sum(a == 1 and b == 1 for a, b in pairs)
    n00 = sum(a == 0 and b == 0 for a, b in pairs)
    n01 = sum(a == 0 and b == 1 for a, b in pairs)
    n10 = sum(a == 1 and b == 0 for a, b in pairs)
    if n == 0:
        return dict(paired=0, n00=0, n01=0, n10=0, n11=0, positives_rater1=0, positives_rater2=0,
                    raw_agreement=None, cohen_kappa=None, gwet_ac1=None,
                    cohen_kappa_status='no_paired_units', gwet_ac1_status='no_paired_units')
    po = (n00 + n11) / n
    p1a = (n10 + n11) / n   # rater 1 positive proportion
    p1b = (n01 + n11) / n   # rater 2 positive proportion
    # Cohen's kappa (per-rater marginals)
    pe_k = p1a * p1b + (1 - p1a) * (1 - p1b)
    kappa = (po - pe_k) / (1 - pe_k) if pe_k != 1 else None
    # Gwet's AC1 (prevalence-robust)
    pi1 = (p1a + p1b) / 2
    pe_g = 2 * pi1 * (1 - pi1)
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g != 1 else None
    return dict(paired=n, n00=n00, n01=n01, n10=n10, n11=n11,
                positives_rater1=n10 + n11, positives_rater2=n01 + n11,
                raw_agreement=po, cohen_kappa=kappa, gwet_ac1=ac1,
                cohen_kappa_status='ok' if kappa is not None else 'undefined_constant_labels',
                gwet_ac1_status='ok')


def subject_level(matrix):
    """matrix: list of cases; each case a list of (r1,r2) across categories.
    Set agreement over each case's positive-label set, cases fully scored by both."""
    full = [row for row in matrix if all(a is not None and b is not None for a, b in row)]
    jaccards, exact = [], 0
    for row in full:
        a = {j for j, (x, _) in enumerate(row) if x == 1}
        b = {j for j, (_, y) in enumerate(row) if y == 1}
        union = a | b
        jaccards.append(1.0 if not union else len(a & b) / len(union))
        exact += (a == b)
    return dict(cases=len(matrix), fully_scored_cases=len(full),
                exact_set_matches=exact, exact_set_match_rate=exact / len(full) if full else None,
                mean_jaccard=statistics.mean(jaccards) if jaccards else None)


def macro(per_cat, metric):
    vals = [c[metric] for c in per_cat if c[metric] is not None]
    return statistics.mean(vals) if vals else None


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def bootstrap(matrix, keys, reps, seed):
    """Cluster bootstrap by instance; CIs for raw agreement, kappa, AC1 per category + macro."""
    groups = collections.defaultdict(list)
    for key, row in zip(keys, matrix):
        groups[key].append(row)
    groups = list(groups.values())
    ncat = len(matrix[0])
    metrics = ['raw_agreement', 'cohen_kappa', 'gwet_ac1']
    draws = {(j, m): [] for j in range(ncat) for m in metrics}
    draws.update({('macro', m): [] for m in metrics})
    if not groups:
        return draws
    rng = random.Random(seed)
    for _ in range(reps):
        sample = [row for _ in groups for row in groups[rng.randrange(len(groups))]]
        per_cat = [category_stats(col) for col in zip(*sample)]
        for j, c in enumerate(per_cat):
            for m in metrics:
                if c[m] is not None:
                    draws[(j, m)].append(c[m])
        for m in metrics:
            mv = macro(per_cat, m)
            if mv is not None:
                draws[('macro', m)].append(mv)
    return draws


def ci(values, reps):
    return dict(ci_low=percentile(values, .025), ci_high=percentile(values, .975),
                bootstrap_defined=len(values), bootstrap_reps=reps)


def self_test():
    # Cohen's kappa worked example: po=.7, pe=.5 -> kappa=.4
    units = [(1, 1)] * 20 + [(0, 0)] * 15 + [(0, 1)] * 5 + [(1, 0)] * 10
    s = category_stats(units)
    assert abs(s['raw_agreement'] - 0.7) < 1e-12
    assert abs(s['cohen_kappa'] - 0.4) < 1e-12
    # Gwet AC1 cross-check against the definition
    pi1 = ((s['n10'] + s['n11']) / s['paired'] + (s['n01'] + s['n11']) / s['paired']) / 2
    pe_g = 2 * pi1 * (1 - pi1)
    assert abs(s['gwet_ac1'] - (0.7 - pe_g) / (1 - pe_g)) < 1e-12
    # Perfect agreement: both coefficients = 1
    assert category_stats([(0, 0), (1, 1)])['cohen_kappa'] == 1
    assert category_stats([(0, 0), (1, 1)])['gwet_ac1'] == 1
    # Prevalence paradox: high raw agreement, kappa undefined (constant), AC1 = 1
    allzero = category_stats([(0, 0)] * 20)
    assert allzero['raw_agreement'] == 1
    assert allzero['cohen_kappa'] is None and allzero['gwet_ac1'] == 1
    # Skew: 18 agree-positive, 1 each off -> high raw agreement, AC1 >> kappa
    skew = category_stats([(1, 1)] * 18 + [(0, 1), (1, 0)])
    assert skew['gwet_ac1'] > skew['cohen_kappa']
    # Symmetry under swapping raters
    rng = random.Random(13)
    for _ in range(100):
        u = [(rng.choice([0, 1, None]), rng.choice([0, 1, None])) for _ in range(30)]
        for m in ['raw_agreement', 'cohen_kappa', 'gwet_ac1']:
            x = category_stats(u)[m]
            y = category_stats([(b, a) for a, b in u])[m]
            assert (x is None and y is None) or abs(x - y) < 1e-12
    # Missing labels excluded, not treated as 0
    assert category_stats([(0, 0), (1, 1), (1, None)])['paired'] == 2
    # Perfect multi-label set agreement
    sl = subject_level([[(1, 1), (0, 0)], [(0, 0), (1, 1)]])
    assert sl['exact_set_match_rate'] == 1 and sl['mean_jaccard'] == 1
    for s in MISSING:
        assert parse_label(s) is None
    try:
        parse_label('2')
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid value accepted')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--input-dir', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--ru', type=Path, default=Path('RU.csv'), help='RU labels, relative to input-dir or absolute')
    ap.add_argument('--ur', type=Path, default=Path('UR.csv'), help='UR labels, relative to input-dir or absolute')
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--bootstrap', type=int, default=2000)
    ap.add_argument('--seed', type=int, default=20261106)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    self_test()
    if args.self_test:
        print('Self-tests passed')
        return
    if args.bootstrap < 0:
        ap.error('--bootstrap must be >= 0')
    paths = {name: (args.input_dir / path).resolve() for name, path in [('RU', args.ru), ('UR', args.ur)]}
    out = (args.output_dir or args.input_dir / 'agreement_results').resolve()
    generated = ['summary.csv', 'subject_level.csv', 'disagreements.csv', 'manifest.json', 'results.json', 'README.md']
    if any(out / name in paths.values() for name in generated):
        raise ValueError('An output file would overwrite an input')

    data, hashes = {}, {}
    for name, path in paths.items():
        fields, rows = read_csv(path)
        required = ['dataset', 'model', 'instance_id'] + [f'{r}_cause_{c}' for r in [1, 2] for c in CATEGORIES[name]]
        if set(required) - set(fields):
            raise ValueError(f'{path}: missing columns {sorted(set(required)-set(fields))}')
        if not rows:
            raise ValueError(f'{path}: no cases')
        ids = set()
        for i, row in enumerate(rows, 1):
            key = tuple(row[k] for k in ['dataset', 'model', 'instance_id'])
            if not all(key) or key in ids:
                raise ValueError(f'{path}: empty or duplicate case ID at data row {i}')
            ids.add(key)
            for c in CATEGORIES[name]:
                for r in [1, 2]:
                    try:
                        parse_label(row[f'{r}_cause_{c}'])
                    except ValueError as e:
                        raise ValueError(f'{name} row {i}, rater {r}, category {c}: {e}') from e
        data[name] = rows
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    summary, subjects, disagreements = [], [], []
    for name, rows in data.items():
        cats = CATEGORIES[name]
        matrix = [[(parse_label(r[f'1_cause_{c}']), parse_label(r[f'2_cause_{c}'])) for c in cats] for r in rows]
        per_cat = [category_stats(col) for col in zip(*matrix)]
        draws = bootstrap(matrix, [(r['dataset'], r['instance_id']) for r in rows], args.bootstrap, args.seed)
        for j, c in enumerate(cats):
            s = dict(dataset=name, category=c, **per_cat[j])
            for m in ['raw_agreement', 'cohen_kappa', 'gwet_ac1']:
                for k, v in ci(draws[(j, m)], args.bootstrap).items():
                    s[f'{m}_{k}'] = v
            summary.append(s)
        # macro means (mean of per-category coefficients; not itself a coefficient)
        m_row = dict(dataset=name, category='MACRO_MEAN',
                     raw_agreement=macro(per_cat, 'raw_agreement'),
                     cohen_kappa=macro(per_cat, 'cohen_kappa'),
                     gwet_ac1=macro(per_cat, 'gwet_ac1'))
        for m in ['raw_agreement', 'cohen_kappa', 'gwet_ac1']:
            for k, v in ci(draws[('macro', m)], args.bootstrap).items():
                m_row[f'{m}_{k}'] = v
        summary.append(m_row)
        # pooled raw agreement across all (case, category) binary decisions
        pooled = category_stats(pair for row in matrix for pair in row)
        summary.append(dict(dataset=name, category='POOLED_BINARY_DECISIONS', **pooled))
        subjects.append(dict(dataset=name, **subject_level(matrix)))
        for i, (r, row) in enumerate(zip(rows, matrix), 1):
            for c, (a, b) in zip(cats, row):
                if a is not None and b is not None and a == b:
                    continue
                disagreements.append(dict(dataset=name, data_row=i, instance_id=r['instance_id'], model=r['model'],
                                          category=c, rater1=a, rater2=b,
                                          status='missing' if a is None or b is None else 'disagree'))

    for row in summary:
        if row.get('raw_agreement') is not None:
            row['raw_agreement_percent'] = 100 * row['raw_agreement']

    manifest = dict(python=sys.version, input_files={n: str(p) for n, p in paths.items()}, source_sha256=hashes,
                    source_rows={n: len(r) for n, r in data.items()}, bootstrap_seed=args.seed, bootstrap_reps=args.bootstrap,
                    bootstrap_unit='dataset + instance_id (cluster), model rows and categories kept together',
                    metrics=dict(
                        raw_agreement='po = (n00+n11)/n',
                        cohen_kappa='(po-pe)/(1-pe), pe = p1a*p1b + p0a*p0b (per-rater marginals)',
                        gwet_ac1='(po-pe)/(1-pe), pe = 2*pi1*(1-pi1), pi1 = mean positive proportion; robust to prevalence'),
                    note='Chance-corrected kappa is unreliable under class skew (prevalence paradox); '
                         'Gwet AC1 is the recommended coefficient here. Missing labels are never treated as 0.',
                    missing_tokens=sorted(MISSING), annotations_modified=False)

    out.mkdir(parents=True, exist_ok=True)
    for filename, items in [('summary.csv', summary), ('subject_level.csv', subjects),
                            ('disagreements.csv', disagreements)]:
        fields = list(dict.fromkeys(k for row in items for k in row)) or ['status']
        write_csv(out / filename, items, fields)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (out / 'results.json').write_text(
        json.dumps(dict(manifest=manifest, summary=summary, subject_level=subjects), indent=2, allow_nan=False) + '\n',
        encoding='utf-8')
    (out / 'README.md').write_text('''# Inter-rater agreement results

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
''', encoding='utf-8')

    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise RuntimeError(f'Input changed during calculation: {path}')

    print(f'Results: {out}')
    hdr = f'{"Dataset":<6} {"Category":<26} {"Paired":>6} {"Raw%":>7} {"Kappa":>8} {"AC1":>8}'
    print(hdr)
    print('-' * len(hdr))
    for row in summary:
        raw = f"{row['raw_agreement_percent']:.2f}" if row.get('raw_agreement_percent') is not None else '—'
        kap = f"{row['cohen_kappa']:.3f}" if row.get('cohen_kappa') is not None else 'undef'
        ac1 = f"{row['gwet_ac1']:.3f}" if row.get('gwet_ac1') is not None else '—'
        print(f"{row['dataset']:<6} {row['category']:<26} {str(row.get('paired','—')):>6} {raw:>7} {kap:>8} {ac1:>8}")


if __name__ == '__main__':
    main()
