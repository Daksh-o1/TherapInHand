import json
import re

import pandas as pd
import requests

from keywords import (
    INTENT_MAP_EN,
    INTENT_MAP_HI,
    SENTIMENT_MAP_EN,
    SENTIMENT_MAP_HI,
    TOPIC_MAP_EN,
    TOPIC_MAP_HI,
)


SOURCE_URLS = [
    "https://raw.githubusercontent.com/niyarrbarman/Symptom2Disease/main/Symptom2Disease.csv",
    "https://raw.githubusercontent.com/mahsa-sanaei/disease-treatment-dataset/main/dataset.csv",
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "having", "he", "her",
    "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "just", "like", "may", "me", "might", "more", "most", "my", "of", "on", "or", "our",
    "please", "should", "since", "so", "some", "than", "that", "the", "their", "them",
    "there", "these", "they", "this", "those", "to", "too", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "who", "why", "will", "with", "would",
    "you", "your", "yours", "patient", "patients", "disease", "disorder", "condition",
    "syndrome", "medical", "medicine", "medicines", "drug", "drugs", "tablet", "tablets",
    "capsule", "capsules", "treatment", "treatments", "therapy", "care", "common",
    "include", "includes", "including", "possible", "often", "usually", "typical",
    "symptom", "symptoms", "sign", "signs",
}

NOISE_WORDS = {
    "unknown", "none", "nan", "n/a", "na", "etc", "misc", "other",
}

GENERAL_TREATMENT_WORDS = {
    "rest", "hydration", "fluids", "water", "monitoring", "observation",
    "follow up", "follow-up", "lifestyle changes", "exercise", "diet",
    "medication", "medications", "therapy", "supportive care", "consultation",
}

COLUMN_ALIASES = {
    "disease": ["label", "disease", "name", "disease_name"],
    "symptoms": ["text", "symptoms", "symptom", "description"],
    "treatments": ["treatments", "treatment", "medication", "medications", "medicine", "medicines"],
    "contagious": ["contagious"],
    "chronic": ["chronic"],
}


def _normalize_space(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _slugify(text):
    text = _normalize_space(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    return text


def _title_case(text):
    words = [word for word in _normalize_space(text).split(" ") if word]
    return " ".join(word.capitalize() for word in words)


def _normalize_header(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def _dedupe_keep_quality(values, limit):
    seen = set()
    scored = []
    for value in values:
        clean = _normalize_space(value)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        score = (
            clean.count(" "),
            len(clean),
            clean,
        )
        scored.append((score, clean))
    scored.sort(key=lambda item: item[0])
    return [item[1] for item in scored[:limit]]


def _split_items(text):
    text = _normalize_space(text).lower()
    if not text:
        return []
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[/|;]+", ",", text)
    text = re.sub(r"\band\/or\b", " and ", text)
    text = re.sub(r"[^a-z0-9,\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if "," in text:
        parts = re.split(r"\s*,\s*", text)
    else:
        parts = re.split(r"\b(?:and|with|plus)\b", text)
    return [_normalize_space(part) for part in parts if _normalize_space(part)]


def _is_truthy(value):
    return _normalize_space(value).lower() in {"true", "1", "yes", "y"}


def _flatten_keyword_maps():
    merged = set()
    keyword_maps = (
        SENTIMENT_MAP_EN,
        INTENT_MAP_EN,
        TOPIC_MAP_EN,
        SENTIMENT_MAP_HI,
        INTENT_MAP_HI,
        TOPIC_MAP_HI,
    )
    for mapping in keyword_maps:
        for values in mapping.values():
            for item in values:
                merged.add(_normalize_space(item))
    return merged


def _keyword_overlap(base_keywords, reference_keywords, limit=10):
    reference_set = {item.lower() for item in reference_keywords if item}
    matched = []
    for item in base_keywords:
        lowered = item.lower()
        if lowered in reference_set:
            matched.append(item)
            continue
        parts = set(lowered.split())
        if parts and any(part in reference_set for part in parts):
            matched.append(item)
    return _dedupe_keep_quality(matched, limit)


def fetch_data(url, chunksize=250):
    header_response = requests.get(url, stream=True, timeout=60)
    header_response.raise_for_status()
    header_line = ""
    for line in header_response.iter_lines(decode_unicode=True):
        if line:
            header_line = line
            break
    header_response.close()
    if not header_line:
        raise ValueError("Missing CSV header for: " + url)

    raw_headers = [part.strip().strip('"') for part in header_line.split(",")]
    normalized_map = {_normalize_header(name): name for name in raw_headers}

    selected_columns = []
    for target in ("disease", "symptoms", "treatments"):
        for alias in COLUMN_ALIASES[target]:
            actual = normalized_map.get(_normalize_header(alias))
            if actual and actual not in selected_columns:
                selected_columns.append(actual)
                break

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    response.raw.decode_content = True
    return pd.read_csv(
        response.raw,
        chunksize=chunksize,
        usecols=selected_columns,
        dtype=str,
        keep_default_na=False,
        low_memory=True,
    )


def clean_keywords(text):
    phrases = set()
    for part in _split_items(text):
        tokens = []
        for token in part.split():
            token = re.sub(r"[^a-z0-9-]", "", token).strip("-")
            if not token or token in STOPWORDS or token in NOISE_WORDS or token.isdigit():
                continue
            tokens.append(token)
        if not tokens:
            continue
        compact = " ".join(tokens[:3])
        if 1 <= len(compact.split()) <= 3:
            phrases.add(compact)
        size = len(tokens)
        for n in (1, 2, 3):
            if size < n:
                continue
            for i in range(size - n + 1):
                phrase = " ".join(tokens[i:i + n])
                if phrase in NOISE_WORDS:
                    continue
                if 1 <= len(phrase.split()) <= 3:
                    phrases.add(phrase)
    return phrases


def enhance_patterns(intent_name, keywords, symptom_examples, base_keywords=None):
    disease_name = _normalize_space(intent_name).lower()
    patterns = set()
    base_keywords = base_keywords or []

    if disease_name:
        patterns.update({
            disease_name,
            "symptoms of " + disease_name,
            "signs of " + disease_name,
            "treatment for " + disease_name,
            "what is " + disease_name,
            "do i have " + disease_name,
            disease_name + " treatment",
            disease_name + " medicine",
            disease_name + " causes",
        })

    for phrase in list(sorted(keywords))[:10]:
        if not phrase or len(phrase) < 2:
            continue
        patterns.update({
            phrase,
            "i have " + phrase,
            "having " + phrase,
            "my symptoms are " + phrase,
            phrase + " symptoms",
            "symptoms of " + phrase,
            "treatment for " + phrase,
            "medicine for " + phrase,
            "is " + phrase + " serious",
        })

    for phrase in list(base_keywords)[:8]:
        patterns.update({
            phrase,
            "i have " + phrase,
            "help with " + phrase,
            "treatment for " + phrase,
        })

    for example in list(symptom_examples)[:6]:
        clean = _normalize_space(example).lower()
        clean = re.sub(r"[^a-z0-9\s,/-]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip(" ,")
        if not clean:
            continue
        if len(clean.split()) <= 12:
            patterns.add(clean)

    high_quality = []
    for item in patterns:
        item = _normalize_space(item)
        if not item:
            continue
        if item.count(" ") > 11:
            continue
        if len(item) < 3:
            continue
        if item.lower() in {"treatment", "symptoms", "medicine"}:
            continue
        high_quality.append(item)
    return _dedupe_keep_quality(high_quality, 25)


def generate_responses(intent_name, keywords, treatments, base_keywords=None, contagious=None, chronic=None):
    disease_name = _title_case(intent_name)
    base_keywords = base_keywords or []
    symptom_list = _dedupe_keep_quality(list(keywords), 5)
    treatment_list = [
        item for item in _dedupe_keep_quality(list(treatments), 5)
        if item.lower() not in GENERAL_TREATMENT_WORDS
    ]
    overlap_keywords = _dedupe_keep_quality(list(base_keywords), 4)

    symptom_text = ", ".join(symptom_list[:4]) if symptom_list else "related symptoms"
    overlap_text = ", ".join(overlap_keywords[:3]) if overlap_keywords else symptom_text
    response_pool = [
        "This may indicate " + disease_name + ".",
        disease_name + " can involve " + symptom_text + ".",
        "Common symptoms include " + symptom_text + ".",
        disease_name + " may also be discussed alongside " + overlap_text + ".",
        "Rest, fluids, and symptom monitoring may help while you recover.",
        "You can ask about symptoms, treatment, warning signs, or recovery for " + disease_name + ".",
        "Consider medical advice if symptoms persist or worsen.",
        "Consult a doctor if symptoms are severe, new, or not improving.",
        "A clinician can confirm whether this matches " + disease_name + ".",
        "Track your symptoms and seek professional guidance if they continue.",
    ]

    if contagious is True:
        response_pool.append(disease_name + " may spread between people, so hygiene and limiting close contact can help.")
    elif contagious is False:
        response_pool.append(disease_name + " is not usually considered contagious, but symptoms should still be monitored.")

    if chronic is True:
        response_pool.append(disease_name + " can be long-term, so follow-up care may matter.")
    elif chronic is False:
        response_pool.append(disease_name + " is often managed as a short-term condition, depending on severity.")

    for item in treatment_list[:4]:
        response_pool.append("Doctors may consider " + item + " depending on your case.")
        response_pool.append(item.capitalize() + " may be used in some cases, but a clinician should decide what fits your symptoms.")

    if not treatment_list:
        response_pool.append("Treatment depends on the cause and severity, so a clinician can guide the safest next step.")

    safe_responses = []
    for response in response_pool:
        response = _normalize_space(response)
        if disease_name.lower() not in response.lower() and "symptom" not in response.lower() and "doctor" not in response.lower():
            continue
        safe_responses.append(response)
    return _dedupe_keep_quality(safe_responses, 12)


def merge_intents(existing_data, generated_intents):
    if not isinstance(existing_data, dict):
        existing_data = {"intents": []}
    existing_list = existing_data.get("intents", [])
    if not isinstance(existing_list, list):
        existing_list = []

    existing_map = {}
    passthrough = []
    for intent in existing_list:
        if not isinstance(intent, dict):
            continue
        tag = intent.get("tag", "")
        key = _slugify(tag)
        if not key:
            passthrough.append(intent)
            continue
        existing_map[key] = {
            "tag": tag,
            "patterns": list(intent.get("patterns", [])),
            "responses": list(intent.get("responses", [])),
        }

    for key, payload in generated_intents.items():
        if key in existing_map:
            merged_patterns = _dedupe_keep_quality(
                existing_map[key]["patterns"] + payload["patterns"],
                25,
            )
            merged_responses = _dedupe_keep_quality(
                payload["responses"] + existing_map[key]["responses"],
                12,
            )
            existing_map[key]["patterns"] = merged_patterns
            existing_map[key]["responses"] = merged_responses
            existing_map[key]["tag"] = payload["tag"]
        else:
            existing_map[key] = {
                "tag": payload["tag"],
                "patterns": payload["patterns"],
                "responses": payload["responses"],
            }

    final_intents = passthrough + list(existing_map.values())
    final_intents.sort(key=lambda item: item.get("tag", "").lower())
    return {"intents": final_intents}


def _pick_column(columns, target_name):
    normalized_columns = {_normalize_header(col): col for col in columns}
    for alias in COLUMN_ALIASES[target_name]:
        found = normalized_columns.get(_normalize_header(alias))
        if found:
            return found
    return ""


def _load_existing_intents():
    for path in ("intents.json", "data/intents.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            continue
    return {"intents": []}


def _aggregate_sources():
    aggregated = {}
    original_keyword_bank = _flatten_keyword_maps()

    for url in SOURCE_URLS:
        reader = fetch_data(url)
        for chunk in reader:
            disease_col = _pick_column(chunk.columns, "disease")
            symptoms_col = _pick_column(chunk.columns, "symptoms")
            treatments_col = _pick_column(chunk.columns, "treatments")
            contagious_col = _pick_column(chunk.columns, "contagious")
            chronic_col = _pick_column(chunk.columns, "chronic")
            if not disease_col:
                continue

            for row in chunk.to_dict("records"):
                disease_raw = _normalize_space(row.get(disease_col, ""))
                if not disease_raw:
                    continue
                tag = _slugify(disease_raw)
                if not tag:
                    continue

                bucket = aggregated.setdefault(
                    tag,
                    {
                        "tag": tag,
                        "display_name": _title_case(disease_raw),
                        "keywords": set(),
                        "symptom_examples": set(),
                        "treatments": set(),
                        "contagious": None,
                        "chronic": None,
                    },
                )

                bucket["keywords"].update(clean_keywords(disease_raw))

                symptom_text = row.get(symptoms_col, "") if symptoms_col else ""
                if symptom_text:
                    bucket["keywords"].update(clean_keywords(symptom_text))
                    if len(bucket["symptom_examples"]) < 8:
                        bucket["symptom_examples"].add(_normalize_space(symptom_text))

                treatment_text = row.get(treatments_col, "") if treatments_col else ""
                if treatment_text:
                    bucket["treatments"].update(clean_keywords(treatment_text))

                if contagious_col:
                    contagious_value = row.get(contagious_col, "")
                    if contagious_value != "":
                        bucket["contagious"] = _is_truthy(contagious_value)

                if chronic_col:
                    chronic_value = row.get(chronic_col, "")
                    if chronic_value != "":
                        bucket["chronic"] = _is_truthy(chronic_value)

    generated = {}
    for tag, bucket in aggregated.items():
        base_keywords = _keyword_overlap(bucket["keywords"], original_keyword_bank, limit=10)
        patterns = enhance_patterns(
            bucket["display_name"],
            bucket["keywords"],
            bucket["symptom_examples"],
            base_keywords=base_keywords,
        )
        responses = generate_responses(
            bucket["display_name"],
            bucket["keywords"],
            bucket["treatments"],
            base_keywords=base_keywords,
            contagious=bucket["contagious"],
            chronic=bucket["chronic"],
        )
        if patterns and responses:
            generated[tag] = {
                "tag": bucket["tag"],
                "patterns": patterns,
                "responses": responses,
            }
    return generated


def main():
    existing_data = _load_existing_intents()
    generated_intents = _aggregate_sources()
    merged = merge_intents(existing_data, generated_intents)
    with open("updated_intents.json", "w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
