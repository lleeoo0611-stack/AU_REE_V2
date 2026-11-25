"""Reproduce a synthetic counterexample to dispersion-based importance weights.

This is a constructed eight-case demonstration, not a general weighting API or
an estimate of predictive performance on real mining Projects. Both utilities
have fixed [0, 1] scales and also span their full sample min/max range.

CRITIC: C_j = std(z_j) * sum_k(1 - corr(z_j, z_k)); w_j = C_j / sum(C).
Diakoulaki, Mavrotas & Papayannakis (1995), Computers & Operations Research:
https://doi.org/10.1016/0305-0548(94)00059-H

Entropy: p_ij = z_ij / sum_i(z_ij); E_j = -sum_i(p_ij*ln(p_ij))/ln(n),
with 0*ln(0)=0; w_j = (1-E_j) / sum_k(1-E_k).
Xu (2004), European Journal of Operational Research, section "The two models":
https://doi.org/10.1016/S0377-2217(03)00146-2

The supervised comparison reuses experiment_models.fit_predict without changing
its fixed utility scales, nonnegative coefficient constraints or lambda=0.01.
"""

import argparse
import json
import math
import statistics
from pathlib import Path

from au_ree_v2.experiment_models import fit_predict


def _correlation(left, right):
    """Pearson correlation for the nonconstant constructed vectors only."""
    mean_left, mean_right = statistics.mean(left), statistics.mean(right)
    numerator = math.fsum((a - mean_left) * (b - mean_right)
                          for a, b in zip(left, right))
    denominator = len(left) * statistics.pstdev(left) * statistics.pstdev(right)
    return numerator / denominator


def _auc(scores, labels):
    """Tie-aware pairwise AUC; these labels are construction checks, not a holdout."""
    positive = [value for value, label in zip(scores, labels) if label == 1]
    negative = [value for value, label in zip(scores, labels) if label == 0]
    return math.fsum(float(a > b) + 0.5 * float(a == b)
                     for a in positive for b in negative) / (len(positive) * len(negative))


def build_counterexample():
    columns = {
        'signal': [i / 7 for i in range(8)],
        'noise': [0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0],
    }
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    names = list(columns)
    count = len(labels)
    correlation = _correlation(columns['signal'], columns['noise'])
    noise_label_correlation = _correlation(columns['noise'], labels)
    auc = {name: _auc(values, labels) for name, values in columns.items()}
    same_noise_distribution = (
        sorted(v for v, y in zip(columns['noise'], labels) if y == 0)
        == sorted(v for v, y in zip(columns['noise'], labels) if y == 1)
    )
    if (not math.isclose(correlation, 0.0, abs_tol=1e-12)
            or not math.isclose(noise_label_correlation, 0.0, abs_tol=1e-12)
            or not same_noise_distribution or auc != {'signal': 1.0, 'noise': 0.5}):
        raise ValueError('Constructed signal/noise relationships have changed')

    standard_deviation = {name: statistics.pstdev(values) for name, values in columns.items()}
    information = {
        name: standard_deviation[name] * math.fsum(
            0.0 if name == other else 1 - _correlation(columns[name], columns[other])
            for other in names)
        for name in names
    }
    critic_weights = {name: value / math.fsum(information.values())
                      for name, value in information.items()}
    entropy = {}
    for name, values in columns.items():
        probabilities = [value / math.fsum(values) for value in values]
        entropy[name] = -math.fsum(p * math.log(p) for p in probabilities if p > 0) / math.log(count)
    diversity = {name: 1 - value for name, value in entropy.items()}
    entropy_weights = {name: value / math.fsum(diversity.values()) for name, value in diversity.items()}
    criteria = {name: {'direction': 'MAX', 'function': 'linear', 'low': 0,
                       'high': 1, 'unit': 'dimensionless'} for name in names}

    def rows(prefix):
        return [{'case_id': f'SYNTHETIC-{prefix}-{i}',
                 'project_id': f'SYNTHETIC-{prefix}-{i}',
                 'features': {name: columns[name][i] for name in names},
                 'label': labels[i]} for i in range(count)]

    # The API separates fit/predict case IDs. These prediction vectors repeat the
    # eight construction vectors exactly; they are NOT an independent test set.
    result = fit_predict(rows('FIT'), rows('RECONSTRUCT'), names,
                         model='outcome_mcda', seed=0, criteria=criteria)
    fitted = result['model']
    return {
        'schema_version': 'weighting-counterexample-v1',
        'synthetic': True,
        'research_status': 'SYNTHETIC_COUNTEREXAMPLE_ONLY_NOT_GENERALIZATION_EVIDENCE',
        'purpose': 'Demonstrate that greater dispersion need not imply outcome-predictive information',
        'case_count': count,
        'cases': rows('CONSTRUCTION'),
        'utility_definitions': criteria,
        'normalization': 'FIXED_0_TO_1_UTILITIES_ALSO_SPAN_SAMPLE_MIN_MAX_0_TO_1',
        'construction_checks': {
            'signal_noise_correlation': correlation,
            'noise_label_correlation': noise_label_correlation,
            'noise_distribution_identical_in_both_label_classes': same_noise_distribution,
            'single_feature_auc': auc,
            'auc_interpretation': 'CONSTRUCTED_VECTOR_CHECK_ONLY_NOT_HELD_OUT_PERFORMANCE',
        },
        'weights': {
            'equal': {name: 1 / len(names) for name in names},
            'critic': critic_weights,
            'entropy': entropy_weights,
            'outcome_mcda': fitted['learned_mcda_weights'],
        },
        'dispersion_diagnostics': {'population_standard_deviation': standard_deviation,
                                   'critic_information': information,
                                   'normalized_entropy': entropy},
        'outcome_mcda': {
            'coefficients': fitted['coefficients'], 'intercept': fitted['intercept'],
            'strength': fitted['strength'], 'weight_status': fitted['weight_status'],
            'regularization': fitted['regularization'], 'optimizer': fitted['optimizer'],
            'seed': fitted['seed'], 'runtime': fitted['runtime'],
            'interpretation': fitted['interpretation'],
        },
        'evaluation': {
            'independent_test_set': False,
            'fit_cases': count,
            'prediction_vectors': 'EXACT_REPETITION_OF_CONSTRUCTION_VECTORS_WITH_DISTINCT_API_IDS',
            'generalization_metrics_reported': False,
        },
        'sources': {
            'critic': 'https://doi.org/10.1016/0305-0548(94)00059-H',
            'entropy': 'https://doi.org/10.1016/S0377-2217(03)00146-2',
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional JSON output; also prints JSON to stdout')
    args = parser.parse_args()
    text = json.dumps(build_counterexample(), ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False) + '\n'
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
