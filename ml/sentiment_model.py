"""
ml/sentiment_model.py
─────────────────────
Sentiment Classifier for TherapInHand
Algorithm : TF-IDF  +  Multinomial Naive Bayes
Labels    : very_negative | negative | neutral | positive

How it works
────────────
1. On first run  → reads data/sentiment_dataset.csv, trains, saves to models/.
2. On later runs → loads the saved model from models/ (instant startup).
3. predict_sentiment(text) → returns a label string.

Why Naive Bayes for sentiment?
──────────────────────────────
Naive Bayes is a probabilistic classifier that works extremely well on
text data because it treats each word as an independent feature.
It is fast, interpretable, and performs especially well on small datasets
— which makes it ideal for a college-level NLP project.
"""

import os
import csv
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

# ── Paths ──────────────────────────────────────────────────────
_BASE  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA  = os.path.join(_BASE, "data",   "sentiment_dataset.csv")
_MODEL = os.path.join(_BASE, "models", "sentiment_model.pkl")


# ── Training ────────────────────────────────────────────────────

def _load_dataset(path: str):
    """Read CSV with columns [text, sentiment] → (texts, labels)."""
    texts, labels = [], []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["text"].strip()
            label = row["sentiment"].strip()
            if t and label:
                texts.append(t)
                labels.append(label)
    return texts, labels


def _train_and_save():
    """Train Naive Bayes on TF-IDF features, persist to disk."""
    print("[SentimentModel] Training sentiment classifier …")
    texts, labels = _load_dataset(_DATA)

    # Pipeline: TF-IDF vectorizer → Multinomial Naive Bayes
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),   # unigrams + bigrams
            sublinear_tf=True,    # log-scaled TF
            min_df=1,
        )),
        ("clf", MultinomialNB(alpha=0.5)),  # alpha = Laplace smoothing
    ])

    pipeline.fit(texts, labels)
    os.makedirs(os.path.dirname(_MODEL), exist_ok=True)
    joblib.dump(pipeline, _MODEL)
    print(f"[SentimentModel] Model saved → {_MODEL}")
    return pipeline


def _load_model():
    """Load trained model from disk, train first if missing."""
    if os.path.exists(_MODEL):
        try:
            return joblib.load(_MODEL)
        except Exception as e:
            print(f"[SentimentModel] Corrupt model file, retraining: {e}")
            return _train_and_save()
    return _train_and_save()


# ── Public API ──────────────────────────────────────────────────

_pipeline = None   # lazy-load on first call


def predict_sentiment(text: str) -> str:
    """
    Predict sentiment label for an English text.

    Returns one of:
        very_negative | negative | neutral | positive
    """
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_model()

    label = _pipeline.predict([text])[0]
    return str(label)


def predict_sentiment_with_confidence(text: str):
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
        "I want to kill myself everything is hopeless",
        "I feel so sad and depressed",
        "Just checking in nothing special",
        "I feel great and hopeful today",
        "I'm calm and grateful for everything",
    ]
    for s in test_sentences:
        print(f"  {s!r:55s} → {predict_sentiment(s)}")
