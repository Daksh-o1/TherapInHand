"""
ml/intent_model.py
──────────────────
Intent Classifier for TherapInHand
Algorithm : TF-IDF  +  Logistic Regression
Labels    : emergency | solution_request | symptom_report |
            emotional_support | general_query

How it works
────────────
1. On first run  → reads data/intent_dataset.csv, trains, saves to models/.
2. On later runs → loads the saved model from models/ (instant startup).
3. predict_intent(text) → returns a label string.
"""

import os
import csv
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# ── Paths ──────────────────────────────────────────────────────
_BASE    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA    = os.path.join(_BASE, "data",   "intent_dataset.csv")
_MODEL   = os.path.join(_BASE, "models", "intent_model.pkl")


# ── Training ────────────────────────────────────────────────────

def _load_dataset(path: str):
    """Read CSV with columns [text, intent] → (texts, labels)."""
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["text"].strip()
            label = row["intent"].strip()
            if t and label:
                texts.append(t)
                labels.append(label)
    return texts, labels


def _train_and_save():
    """Train Logistic Regression on TF-IDF features, persist to disk."""
    print("[IntentModel] Training intent classifier …")
    texts, labels = _load_dataset(_DATA)

    # Pipeline: TF-IDF vectorizer → Logistic Regression
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),   # unigrams + bigrams for better coverage
            sublinear_tf=True,    # apply log(1 + tf) scaling
            min_df=1,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver="lbfgs",
        )),
    ])

    pipeline.fit(texts, labels)
    os.makedirs(os.path.dirname(_MODEL), exist_ok=True)
    joblib.dump(pipeline, _MODEL)
    print(f"[IntentModel] Model saved → {_MODEL}")
    return pipeline


def _load_model():
    """Load trained model from disk, train first if missing."""
    if os.path.exists(_MODEL):
        try:
            return joblib.load(_MODEL)
        except Exception as e:
            print(f"[IntentModel] Corrupt model file, retraining: {e}")
            return _train_and_save()
    return _train_and_save()


# ── Public API ──────────────────────────────────────────────────

_pipeline = None   # lazy-load on first call


def predict_intent(text: str) -> str:
    """
    Predict intent label for an English text.

    Returns one of:
        emergency | solution_request | symptom_report |
        emotional_support | general_query
    """
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_model()

    label = _pipeline.predict([text])[0]
    return str(label)


def predict_intent_with_confidence(text: str):
    """Return (label, confidence) for a text input."""
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_model()

    probabilities = _pipeline.predict_proba([text])[0]
    best_index = probabilities.argmax()
    label = str(_pipeline.classes_[best_index])
    confidence = float(probabilities[best_index])
    return label, confidence


def retrain():
    """Force re-training even if a saved model already exists (utility)."""
    global _pipeline
    _pipeline = _train_and_save()


# ── Standalone test ─────────────────────────────────────────────
if __name__ == "__main__":
    test_sentences = [
        "I want to kill myself",
        "I feel so sad and alone",
        "My head hurts and I feel dizzy",
        "How can I manage my anxiety",
        "What is mental health",
    ]
    for s in test_sentences:
        print(f"  {s!r:50s} → {predict_intent(s)}")
