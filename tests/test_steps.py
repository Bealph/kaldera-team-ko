"""Résolution des étapes depuis les libellés de scénario."""

from kaldera.steps import Step, step_from_name


def test_review_label_resolves_to_review_step():
    assert step_from_name("REVIEW") == Step.REVIEW


def test_all_business_labels_resolve():
    for label in ("RESEARCH", "DRAFT", "REVIEW", "FINALIZE"):
        assert step_from_name(label).value == label
