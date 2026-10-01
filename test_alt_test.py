#!/usr/bin/env python3
"""test_alt_test.py — validation of alt_test.py's alt-test against the authors' reference implementation
(github.com/nitaytech/AltTest, alt_test_example.ipynb; the functions below marked REFERENCE are copied from it
verbatim, only the scoring function is passed in as a callable, as that code allows). Synthetic data only:
brand sets drawn around a latent truth, several extractor qualities, missing extractor annotations, ties.
Asserts identical per-rater p-values, winning rate and advantage probability, plus two sanity cases
(an extractor equal to the latent truth must pass; a random extractor must fail).
Usage: python test_alt_test.py [path/to/alt_test.py]"""
import random, sys, re
from typing import Any, Callable, Dict, List, Union
import numpy as np
from scipy.stats import ttest_1samp

with open(sys.argv[1] if len(sys.argv) > 1 else "alt_test.py", encoding="utf-8") as fh:
    src = fh.read()
ns = {"np": np, "ttest_1samp": ttest_1samp}
exec(re.search(r"^def f1\(x, y\):.*?(?=^def rl)", src, re.S | re.M).group(0), ns)
exec(re.search(r"^def sim_score.*?(?=^res = alt_test)", src, re.S | re.M).group(0), ns)
f1, mine = ns["f1"], ns["alt_test"]

# ----------------------------- REFERENCE (verbatim) -----------------------------
def ttest(indicators, epsilon: float) -> float:
    return ttest_1samp(indicators, epsilon, alternative='less').pvalue

def by_procedure(p_values: List[float], q: float) -> List[int]:
    p_values = np.array(p_values, dtype=float)
    m = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_pvals = p_values[sorted_indices]
    # Compute the harmonic sum H_m = 1 + 1/2 + ... + 1/m
    H_m = np.sum(1.0 / np.arange(1, m + 1))
    # Compute the BY thresholds for each rank i
    by_thresholds = (np.arange(1, m + 1) / m) * (q / H_m)
    max_i = -1
    for i in range(m):
        if sorted_pvals[i] <= by_thresholds[i]:
            max_i = i
    if max_i == -1:
        return []
    rejected_sorted_indices = sorted_indices[:max_i + 1]
    return list(rejected_sorted_indices)

def alt_test(llm_annotations: Dict[Union[int, str], Any],
             humans_annotations: Dict[Union[int, str], Dict[Union[int, str], Any]],
             scoring_function: Union[str, Callable] = 'accuracy',
             epsilon: float = 0.2,
             q_fdr: float = 0.05,
             min_humans_per_instance: int = 2,
             min_instances_per_human: int = 30):
    i_set, h_set = {}, {}
    for h, anns in humans_annotations.items():
        i_set[h] = list(anns.keys())
        for i, ann in anns.items():
            if i not in h_set:
                h_set[i] = []
            h_set[i].append(h)
    instances_to_keep = {i for i in h_set if len(h_set[i]) >= min_humans_per_instance and i in llm_annotations}
    i_set = {h: [i for i in i_set[h] if i in instances_to_keep] for h in i_set}
    h_set = {i: h_set[i] for i in h_set if i in instances_to_keep}
    p_values, advantage_probs, humans = [], [], []
    for excluded_h in humans_annotations:
        llm_indicators = []
        excluded_indicators = []
        instances = [i for i in i_set[excluded_h] if i in llm_annotations]
        if len(instances) < min_instances_per_human:
            continue
        for i in instances:
            human_ann = humans_annotations[excluded_h][i]
            llm_ann = llm_annotations[i]
            remaining_anns = [humans_annotations[h][i] for h in h_set[i] if h != excluded_h]
            human_score = scoring_function(human_ann, remaining_anns)
            llm_score = scoring_function(llm_ann, remaining_anns)
            llm_indicators.append(1 if llm_score >= human_score else 0)
            excluded_indicators.append(1 if human_score >= llm_score else 0)
        diff_indicators = [exc_ind - llm_ind for exc_ind, llm_ind in zip(excluded_indicators, llm_indicators)]
        p_values.append(ttest(diff_indicators, epsilon))
        advantage_probs.append(float(np.mean(llm_indicators)))
        humans.append(excluded_h)
    rejected_indices = by_procedure(p_values, q_fdr)
    advantage_prob = float(np.mean(advantage_probs))
    winning_rate = len(rejected_indices) / len(humans)
    return winning_rate, advantage_prob, p_values
# --------------------------------------------------------------------------------

def sim(pred, anns):
    return float(np.mean([f1(pred, a) for a in anns]))

VOCAB = [f"b{i}" for i in range(60)]
def noisy(truth, p_drop, p_add, rng):
    s = {x for x in truth if rng.random() > p_drop}
    s |= {x for x in VOCAB if rng.random() < p_add / len(VOCAB) * 3}
    return frozenset(s)

def scenario(seed, llm_drop, llm_add, miss=0.0, n=300):
    rng = random.Random(seed)
    truth = {i: frozenset(rng.sample(VOCAB, rng.randint(0, 7))) for i in range(n)}
    humans = {h: {i: noisy(truth[i], 0.12, 0.3, rng) for i in range(n)} for h in ("R1", "R2", "R3")}
    llm = {i: noisy(truth[i], llm_drop, llm_add, rng) for i in range(n) if rng.random() >= miss}
    return llm, humans, truth

checks = 0
for seed in range(40):
    for llm_drop, llm_add, miss in ((0.05, 0.1, 0.0), (0.12, 0.3, 0.02), (0.3, 0.8, 0.0), (0.6, 2.0, 0.05)):
        llm, humans, _ = scenario(seed, llm_drop, llm_add, miss)
        w_ref, adv_ref, p_ref = alt_test(llm, humans, sim, epsilon=0.15, q_fdr=0.05)
        r = mine(llm, humans, 0.15, 0.05)
        p_mine = [x["p"] for x in r["per_rater"]]
        assert np.allclose(p_ref, p_mine, rtol=0, atol=0, equal_nan=True), (seed, p_ref, p_mine)
        assert w_ref == r["winning_rate"] and adv_ref == r["advantage_probability"], (seed, w_ref, r)
        checks += 1
# sanity: the latent truth as the "extractor" passes; a random extractor fails
llm, humans, truth = scenario(7, 0.0, 0.0)
assert mine(dict(truth), humans, 0.15, 0.05)["passes"]
rng = random.Random(9)
rand = {i: frozenset(rng.sample(VOCAB, rng.randint(0, 7))) for i in range(300)}
assert not mine(rand, humans, 0.15, 0.05)["passes"]
print(f"alt-test implementation identical to the reference implementation on {checks} synthetic studies; sanity cases pass")
