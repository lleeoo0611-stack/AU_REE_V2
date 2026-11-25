"""Small experiment baselines; learning dependencies are imported only on demand.

Rows represent cases, which may be repeated snapshots of one Project. The
experiment splitter owns the group/time contract. This module never imputes a
label, changes evidence, or interprets a decision utility as an event probability.
"""

import math
import platform
import statistics
import warnings
from collections.abc import Mapping
from importlib.metadata import version

from .mcda import interval_mcda, score


def _number(value, description):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{description} must be a finite number')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f'{description} must be a finite number')
    return value


def _feature_order(features, allow_empty=False):
    if isinstance(features, (str, bytes)):
        raise ValueError('features must be a sequence of unique feature names')
    try:
        names = list(features)
    except TypeError as exc:
        raise ValueError('features must be a sequence of unique feature names') from exc
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError('Feature names must be nonempty strings')
    if len(set(names)) != len(names) or (not names and not allow_empty):
        raise ValueError('Require unique, nonempty selected features')
    return sorted(names)


def _rows(rows, features, partition, require_labels):
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f'{partition} rows must be mappings')
        identifiers = {key: row.get(key) for key in ('case_id', 'project_id')}
        if any(not isinstance(value, str) or not value.strip()
               for value in identifiers.values()):
            raise ValueError(f'{partition} requires nonempty case_id and project_id')
        case_id = identifiers['case_id']
        if case_id in seen:
            raise ValueError(f'Duplicate {partition} case_id: {case_id}')
        seen.add(case_id)
        raw_features = row.get('features')
        if not isinstance(raw_features, Mapping):
            raise ValueError(f'{partition} case {case_id} requires a features mapping')
        values = {}
        for name in features:
            value = raw_features.get(name)
            values[name] = None if value is None else _number(
                value, f'{partition} case {case_id} feature {name}')
        label = row.get('label')
        if label is None:
            if require_labels:
                raise ValueError(f'{partition} case {case_id} requires an observed binary label')
        else:
            label = _number(label, f'{partition} case {case_id} label')
            if label not in (0, 1):
                raise ValueError(f'{partition} case {case_id} label must be 0 or 1')
            label = int(label)
        result.append({**identifiers, 'features': values, 'label': label})
    return sorted(result, key=lambda row: (row['case_id'], row['project_id']))


def _counts(rows):
    return {
        'rows': len(rows),
        'projects': len({row['project_id'] for row in rows}),
        'class_counts': {str(label): sum(row['label'] == label for row in rows)
                         for label in (0, 1)},
        'unlabeled_rows': sum(row['label'] is None for row in rows),
    }


def _probability_metrics(test, probabilities):
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError('Model returned an invalid probability')
    labels = [row['label'] for row in test]
    clipping = 1e-15
    clipped = [min(1 - clipping, max(clipping, p)) for p in probabilities]
    positive = sum(labels)
    negative = len(labels) - positive
    auc = None
    if positive and negative:
        ordered = sorted(zip(probabilities, labels))
        rank_sum = 0.0
        start = 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and ordered[end][0] == ordered[start][0]:
                end += 1
            mean_rank = (start + 1 + end) / 2
            rank_sum += mean_rank * sum(label for _, label in ordered[start:end])
            start = end
        auc = (rank_sum - positive * (positive + 1) / 2) / (positive * negative)
    return {
        'task': 'binary_event_probability',
        'evaluation_unit': 'case',
        'brier_score': math.fsum((p - y) ** 2 for p, y in zip(probabilities, labels)) / len(test),
        'log_loss': -math.fsum(y * math.log(p) + (1 - y) * math.log1p(-p)
                               for p, y in zip(clipped, labels)) / len(test),
        'log_loss_clipping': clipping,
        'roc_auc': auc,
        'roc_auc_status': 'DEFINED' if auc is not None else 'UNDEFINED_SINGLE_TEST_CLASS',
    }


def _validated_anchors(features, criteria):
    if not isinstance(criteria, Mapping) or set(criteria) != set(features):
        raise ValueError('Scoring criteria must name every selected feature exactly once')
    anchors = {}
    for name in features:
        raw = criteria[name]
        if not isinstance(raw, Mapping):
            raise ValueError(f'Criterion {name} must be a mapping')
        low = _number(raw.get('low'), f'Lower anchor for {name}')
        high = _number(raw.get('high'), f'Upper anchor for {name}')
        function, direction = raw.get('function'), raw.get('direction')
        if (high <= low or not math.isfinite(high - low)
                or function not in ('linear', 'log1p') or direction not in ('MIN', 'MAX')):
            raise ValueError(f'Invalid fixed scoring scale, function or direction for {name}')
        if function == 'log1p' and low <= -1:
            raise ValueError(f'log1p lower anchor for {name} must exceed -1')
        if function == 'log1p' and math.log1p(high) <= math.log1p(low):
            raise ValueError(f'log1p scoring anchors for {name} collapse at floating-point precision')
        anchors[name] = {**raw, 'low': low, 'high': high}
    return anchors


def _fixed_mcda(test, features, criteria, weights):
    anchors = _validated_anchors(features, criteria)
    if not isinstance(weights, Mapping) or set(weights) != set(features):
        raise ValueError('fixed_mcda weights must name every selected feature exactly once')
    ordered_weights = [_number(weights[name], f'Weight for {name}') for name in features]
    total = sum(ordered_weights)
    if any(weight < 0 for weight in ordered_weights) or not math.isfinite(total) or total <= 0:
        raise ValueError('fixed_mcda requires nonnegative weights with a finite positive sum')
    matrix = []
    for row in test:
        bounds = []
        for name in features:
            value = row['features'][name]
            if value is None:
                bounds.append((0.0, 1.0))
            else:
                utility = score(value, anchors[name])
                bounds.append((utility, utility))
        matrix.append(bounds)
    method_bounds = interval_mcda(matrix, ordered_weights, threshold=0.2)
    predictions = [{
        'case_id': row['case_id'], 'project_id': row['project_id'],
        'kind': 'mcda_intervals',
        'prediction': {method: results[index] for method, results in method_bounds.items()},
        'unknown_features': [name for name in features if row['features'][name] is None],
    } for index, row in enumerate(test)]
    details = {
        'trained': False,
        'criteria': anchors,
        'input_weights': dict(zip(features, ordered_weights)),
        'normalized_weights': {name: weight / total for name, weight in zip(features, ordered_weights)},
        'promethee_threshold': 0.2,
        'ranking_population': [row['case_id'] for row in test],
        'ranking_unit': 'case',
        'interpretation': 'UTILITY_AND_PANEL_RANK_BOUNDS_NOT_EVENT_PROBABILITIES',
        'unknown_values': 'UTILITY_SET_0_TO_1_NOT_ZERO_FILL_OR_RANDOM_DRAWS',
    }
    return predictions, details


def _logistic(train, test, features, seed):
    empty = [name for name in features if all(row['features'][name] is None for row in train)]
    if empty:
        raise ValueError('ALL_MISSING_TRAIN_FEATURES: ' + ', '.join(empty))
    if len({row['label'] for row in train}) != 2:
        raise ValueError('Logistic training requires both observed label classes')
    try:
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise ValueError('logistic requires the optional experiment dependencies (scikit-learn)') from exc

    def matrix(rows):
        return [[math.nan if row['features'][name] is None else row['features'][name]
                 for name in features] for row in rows]

    parameters = {'C': 1.0, 'solver': 'lbfgs', 'max_iter': 1000,
                  'tol': 1e-8, 'random_state': seed, 'fit_intercept': True,
                  'class_weight': None}
    pipeline = Pipeline([
        ('imputer', SimpleImputer(strategy='median', add_indicator=True)),
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(**parameters)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        try:
            pipeline.fit(matrix(train), [row['label'] for row in train])
        except ConvergenceWarning as exc:
            raise ValueError('Logistic training did not converge with the fixed iteration budget') from exc
    probabilities = [float(value) for value in pipeline.predict_proba(matrix(test))[:, 1]]
    imputer, scaler, classifier = (pipeline.named_steps[name]
                                   for name in ('imputer', 'scaler', 'classifier'))
    transformed_names = [str(name) for name in imputer.get_feature_names_out(features)]
    if len(set(transformed_names)) != len(transformed_names):
        raise ValueError('Transformed feature names collide with missing-indicator names')
    details = {
        'trained': True,
        'parameters': parameters,
        'classes': [int(value) for value in classifier.classes_],
        'transformed_feature_order': transformed_names,
        'imputer': {
            'strategy': 'median', 'add_indicator': True,
            'statistics': {name: float(value) for name, value in zip(features, imputer.statistics_)},
            'indicator_features': [features[int(index)] for index in imputer.indicator_.features_],
        },
        'scaler': {
            'mean': {name: float(value) for name, value in zip(transformed_names, scaler.mean_)},
            'scale': {name: float(value) for name, value in zip(transformed_names, scaler.scale_)},
        },
        'coefficients': {name: float(value) for name, value in zip(transformed_names, classifier.coef_[0])},
        'intercept': float(classifier.intercept_[0]),
        'n_iter': [int(value) for value in classifier.n_iter_],
        'preprocessing_fit_scope': 'TRAIN_CASES_ONLY',
        'hyperparameter_selection': 'FIXED_NO_TEST_TUNING',
        'interpretation': 'BINARY_EVENT_PROBABILITY_NOT_MCDA_PREFERENCE_WEIGHT',
        'runtime': {package: version(package) for package in ('numpy', 'scipy', 'scikit-learn')},
    }
    return probabilities, details


def _outcome_mcda(train, test, features, criteria):
    """Fit event labels with nonnegative coefficients on fixed benefit utilities.

    Missing raw features use training-only medians *before* utility scoring.
    There are no learned anchors, scaler or missing-indicator coefficients.
    The coefficients express empirical outcome associations under these
    constraints; they are not elicited decision-maker preferences.
    """
    anchors = _validated_anchors(features, criteria)
    observed = {name: [row['features'][name] for row in train
                       if row['features'][name] is not None] for name in features}
    empty = [name for name in features if not observed[name]]
    if empty:
        raise ValueError('ALL_MISSING_TRAIN_FEATURES: ' + ', '.join(empty))
    if len({row['label'] for row in train}) != 2:
        raise ValueError('outcome_mcda training requires both observed label classes')
    medians = {name: float(statistics.median(observed[name])) for name in features}
    if not all(math.isfinite(value) for value in medians.values()):
        raise ValueError('Nonfinite training feature median')
    try:
        import numpy as np
        from scipy.optimize import minimize
        from scipy.special import expit
    except ImportError as exc:
        raise ValueError('outcome_mcda requires optional experiment dependencies (numpy and scipy)') from exc

    def utility_matrix(rows):
        return np.asarray([[score(medians[name] if row['features'][name] is None
                                  else row['features'][name], anchors[name])
                            for name in features] for row in rows], dtype=float)

    train_utility, test_utility = utility_matrix(train), utility_matrix(test)
    labels = np.asarray([row['label'] for row in train], dtype=float)
    regularization = 0.01
    tolerance = 1e-8

    def objective(parameters):
        intercept, coefficients = parameters[0], parameters[1:]
        logits = intercept + train_utility @ coefficients
        residuals = expit(logits) - labels
        loss = np.mean(np.logaddexp(0.0, logits) - labels * logits)
        loss += 0.5 * regularization * np.dot(coefficients, coefficients)
        gradient = np.concatenate((np.asarray([np.mean(residuals)]),
                                   train_utility.T @ residuals / len(train)
                                   + regularization * coefficients))
        return float(loss), gradient

    prevalence = float(np.mean(labels))
    initial = np.zeros(len(features) + 1, dtype=float)
    initial[0] = math.log(prevalence) - math.log1p(-prevalence)
    options = {'maxiter': 2000, 'maxls': 50, 'ftol': 1e-12, 'gtol': 1e-9}
    fitted = minimize(objective, initial, jac=True, method='L-BFGS-B',
                      bounds=[(None, None)] + [(0.0, None)] * len(features), options=options)
    if not fitted.success or not np.all(np.isfinite(fitted.x)) or not math.isfinite(float(fitted.fun)):
        raise ValueError('outcome_mcda training did not converge: ' + str(fitted.message))
    intercept = float(fitted.x[0])
    coefficients = [max(0.0, float(value)) for value in fitted.x[1:]]
    strength = math.fsum(coefficients)
    learned_weights = ({name: coefficient / strength for name, coefficient in zip(features, coefficients)}
                       if strength > tolerance else None)
    probabilities = [float(value) for value in expit(intercept + test_utility @ coefficients)]
    explanations = []
    for row, utilities in zip(test, test_utility):
        contributions = ({name: learned_weights[name] * float(utility)
                          for name, utility in zip(features, utilities)}
                         if learned_weights is not None else None)
        explanations.append({
            'utility_score': math.fsum(contributions.values()) if contributions is not None else None,
            'contributions': contributions,
            'logit_contributions': {name: coefficient * float(utility)
                                    for name, coefficient, utility in zip(features, coefficients, utilities)},
            'imputed_features': [name for name in features if row['features'][name] is None],
        })
    details = {
        'trained': True,
        'criteria': anchors,
        'imputer': {'strategy': 'median', 'statistics': medians, 'add_indicator': False,
                    'space': 'RAW_FEATURE_VALUES_BEFORE_FIXED_UTILITY_SCORING'},
        'scaler': None,
        'coefficients': dict(zip(features, coefficients)),
        'intercept': intercept,
        'learned_mcda_weights': learned_weights,
        'strength': strength,
        'weight_status': 'OUTCOME_FITTED_NONNEGATIVE_WEIGHTS' if learned_weights is not None else 'NO_DIRECTIONAL_SIGNAL',
        'weight_normalization_tolerance': tolerance,
        'regularization': {'lambda': regularization, 'penalize_intercept': False,
                           'objective': 'MEAN_LOG_LOSS_PLUS_0.5_LAMBDA_SUM_BETA_SQUARED'},
        'optimizer': {'method': 'L-BFGS-B', 'options': options, 'success': bool(fitted.success),
                      'iterations': int(fitted.nit), 'objective': float(fitted.fun),
                      'initialization': 'TRAIN_PREVALENCE_INTERCEPT_AND_ZERO_COEFFICIENTS'},
        'coefficient_constraints': 'BETA_NONNEGATIVE_ON_FIXED_BENEFIT_UTILITIES',
        'probability_link': 'sigmoid(intercept + sum(beta_j * utility_j))',
        'preprocessing_fit_scope': 'TRAIN_CASES_ONLY',
        'hyperparameter_selection': 'FIXED_NO_TEST_TUNING',
        'input_weights_used': False,
        'interpretation': 'OUTCOME_FITTED_MONOTONE_UTILITY_NOT_EXPERT_PREFERENCE',
        'missing_values': 'TRAIN_MEDIAN_IMPUTATION_FOR_EXPERIMENT_ONLY',
        'runtime': {package: version(package) for package in ('numpy', 'scipy')},
    }
    return probabilities, details, explanations


def fit_predict(train_rows, test_rows, features, model, seed, criteria=None, weights=None):
    """Fit an experimental baseline and evaluate observed test labels.

    ``prior``, ``logistic`` and ``outcome_mcda`` return event probabilities and
    binary metrics. ``outcome_mcda`` learns nonnegative coefficients on fixed
    criterion utilities; its weights argument is unused and no formal weight is
    changed. Its normalized weights are absent when there is no directional signal.
    ``fixed_mcda`` needs exact feature-to-criterion and feature-to-weight maps;
    it ranks the supplied test *cases*, requires no training labels, and reports
    unknown utilities as intervals. Its scores never enter probability metrics.
    Inputs are copied and stably ordered, and source evidence is never modified.
    """
    if model not in ('prior', 'logistic', 'fixed_mcda', 'outcome_mcda'):
        raise ValueError(f'Unsupported experiment model: {model}')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** 32:
        raise ValueError('seed must be an integer in [0, 2**32)')
    names = _feature_order(features, allow_empty=model == 'prior')
    probability_model = model != 'fixed_mcda'
    train = _rows(train_rows, names, 'train', probability_model)
    test = _rows(test_rows, names, 'test', probability_model)
    if not test or (probability_model and not train):
        raise ValueError('Require nonempty test cases and, for learning models, training cases')
    overlap = {row['case_id'] for row in train} & {row['case_id'] for row in test}
    if overlap:
        raise ValueError('Train/test case_id overlap: ' + ', '.join(sorted(overlap)))
    metadata = {
        'name': model, 'feature_order': names, 'seed': seed,
        'train_case_ids': [row['case_id'] for row in train],
        'runtime': {'python': platform.python_version()},
        'sample_weighting': 'EQUAL_CASE_WEIGHT_NOT_INDEPENDENT_PROJECT_COUNT',
    }
    metrics = {'train': _counts(train), 'test': _counts(test)}
    if model == 'fixed_mcda':
        predictions, details = _fixed_mcda(test, names, criteria, weights)
        metadata.update(details)
        metrics.update(task='fixed_mcda', evaluation_unit='case',
                       probability_metrics='NOT_APPLICABLE_UTILITY_BOUNDS')
    else:
        explanations = [{} for _ in test]
        if model == 'prior':
            prior = sum(row['label'] for row in train) / len(train)
            probabilities = [prior] * len(test)
            metadata.update(trained=True, positive_fraction=prior,
                            interpretation='TRAIN_LABEL_PREVALENCE_BASELINE')
        else:
            if model == 'outcome_mcda':
                probabilities, details, explanations = _outcome_mcda(train, test, names, criteria)
            else:
                probabilities, details = _logistic(train, test, names, seed)
            runtime = {**metadata['runtime'], **details.pop('runtime')}
            metadata.update(details, runtime=runtime)
        predictions = [{'case_id': row['case_id'], 'project_id': row['project_id'],
                        'prediction': probability, 'kind': 'probability', **explanation}
                       for row, probability, explanation in zip(test, probabilities, explanations)]
        metrics.update(_probability_metrics(test, probabilities))
    return {'predictions': predictions, 'model': metadata, 'metrics': metrics}
