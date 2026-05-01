# ══════════════════════════════════════════════════════════════
#  KEYWORD MAPS — English
# ══════════════════════════════════════════════════════════════

SENTIMENT_MAP_EN = {
    "very_negative": [
        "hopeless", "worthless", "can't go on", "want to die", "end it",
        "kill myself", "suicidal", "no point", "give up", "hate myself",
        "unbearable", "i'm done", "want to disappear", "end my life",
        "hurt myself", "self harm", "do not want to live", "nothing matters",
        "life is over", "cannot survive this", "do not feel safe with myself"
        , "i do not want to be here", "i want to vanish", "i might hurt myself",
        "i feel unsafe", "no reason to keep going"
    ],
    "negative": [
        "sad", "depressed", "anxious", "stressed", "tired", "exhausted",
        "overwhelmed", "scared", "worried", "pain", "hurt", "cry",
        "awful", "terrible", "miserable", "bad", "struggling", "numb",
        "empty", "lost", "alone", "lonely", "dread", "panic", "fever",
        "cold", "cough", "chills", "nausea", "dizzy", "weak", "drained",
        "burned out", "sick", "shaky", "restless", "sore throat"
        , "distressed", "upset", "frightened", "afraid", "tense",
        "uneasy", "overloaded", "helpless", "heavy", "not okay",
        "unwell", "ill", "body ache", "throat pain", "runny nose",
        "blocked nose", "stomach pain", "loose motion", "migraine"
    ],
    "positive": [
        "happy", "good", "great", "better", "calm", "hopeful", "relieved",
        "grateful", "fine", "okay", "thankful", "improving", "wonderful",
        "recovering", "stable", "rested", "supported", "lighter", "healing"
        , "safe", "settled", "peaceful", "encouraged", "doing okay"
    ]
}

INTENT_MAP_EN = {
    "emergency": [
        "want to die", "kill myself", "end my life", "suicidal",
        "can't go on", "no reason to live", "hurt myself", "self harm",
        "want to disappear", "i'm done with life"
        , "i do not want to live", "i don't want to live", "i might hurt myself",
        "i feel unsafe with myself", "i want everything to end"
    ],
    "solution_request": [
        "help me", "what can i do", "how to", "how do i", "tips",
        "advice", "suggest", "what should i", "ways to", "fix",
        "solution", "cope", "deal with", "manage", "treat", "reduce"
        , "recover from", "calm down", "sleep better", "feel better",
        "handle this", "relieve", "soothe", "at home", "should i worry"
        , "what now", "what should i do now", "can you guide me",
        "tell me what to do", "how can i feel better", "how can i stop this",
        "home remedy", "next step", "what is the next step"
    ],
    "symptom_report": [
        "i have", "experiencing", "my chest", "my head",
        "headache", "nausea", "dizzy", "palpitations", "can't breathe",
        "shaking", "sweating", "stomach", "pain", "ache", "symptoms",
        "fever", "cold", "cough", "chills", "sore throat", "runny nose",
        "blocked nose", "sneezing", "vomiting", "diarrhea", "body ache",
        "weakness", "fatigue", "shortness of breath", "cramps"
        , "throat hurts", "my throat hurts", "my stomach hurts",
        "my body hurts", "body pain", "loose motion", "migraine",
        "malaria", "jaundice", "dengue", "typhoid", "influenza",
        "high temperature", "nose is blocked", "nose blocked",
        "feeling feverish", "cannot sleep", "can't sleep"
    ],
    "emotional_support": [
        "i'm sad", "i feel sad", "feeling down", "no one understands",
        "alone", "lonely", "i'm scared", "anxious", "worried",
        "stressed", "overwhelmed", "i can't handle", "i'm lost",
        "need someone", "please help", "i'm not okay", "i feel broken",
        "i feel helpless", "i am not doing well", "i need support",
        "i feel empty", "i feel low", "i feel unstable"
        , "can we talk", "i need to talk", "i feel alone", "i feel overwhelmed",
        "i am scared", "i am worried", "i am stressed", "i feel anxious",
        "i need someone to listen", "i am struggling", "sad", "unhappy",
        "low", "down", "depressed", "hopeless", "empty", "numb",
        "anxiety", "panic", "overthinking", "stress", "loneliness",
        "isolated", "nobody", "feel lonely", "feel alone", "emotionally tired"
    ],
    "greeting": [
        "hi", "hello", "hey", "heyy", "good morning", "good evening",
        "good afternoon", "hiya", "hey there", "hello there"
    ],
    "gratitude": [
        "thanks", "thank you", "thanks a lot", "thank you so much",
        "appreciate it", "much appreciated", "thankyou"
    ],
    "goodbye": [
        "bye", "goodbye", "good night", "goodnight", "see you",
        "see you later", "bye bye", "take care"
    ],
    "casual_checkin": [
        "how are you", "how are you doing", "how's it going", "hows it going",
        "what's up", "whats up", "how have you been", "how is it going",
        "sup", "yo"
    ]
}

INTENT_PATTERNS_EN = [
    {"intent": "emergency", "priority": 100, "keywords": INTENT_MAP_EN["emergency"]},
    {"intent": "solution_request", "priority": 80, "keywords": INTENT_MAP_EN["solution_request"]},
    {"intent": "symptom_report", "priority": 70, "keywords": INTENT_MAP_EN["symptom_report"]},
    {"intent": "emotional_support", "priority": 60, "keywords": INTENT_MAP_EN["emotional_support"]},
    {"intent": "casual_checkin", "priority": 35, "keywords": INTENT_MAP_EN["casual_checkin"]},
    {"intent": "gratitude", "priority": 34, "keywords": INTENT_MAP_EN["gratitude"]},
    {"intent": "goodbye", "priority": 33, "keywords": INTENT_MAP_EN["goodbye"]},
    {"intent": "greeting", "priority": 32, "keywords": INTENT_MAP_EN["greeting"]},
]

TOPIC_MAP_EN = {
    "anxiety": [
        "anxious", "anxiety", "panic", "panic attack", "heart racing",
        "restless", "can't calm", "overthinking", "nervous", "fear",
        "dread", "worried", "worry", "palpitations", "shaking",
        "racing thoughts", "mind won't stop", "tight chest", "feeling unsafe"
        , "spiraling", "can't stop thinking", "cannot stop thinking",
        "breathing fast", "panic feeling", "uneasy", "on edge",
        "stressed", "stress", "anxious", "panic", "overthinking"
    ],
    "fatigue": [
        "tired", "exhausted", "fatigue", "no energy", "sleep", "can't sleep",
        "insomnia", "sleepy", "worn out", "drained", "sluggish",
        "always tired", "wake up tired", "burned out", "burnt out",
        "no motivation", "weakness", "low energy"
        , "cannot sleep", "can't sleep", "poor sleep", "sleep trouble",
        "body feels heavy", "mentally tired", "physically tired"
    ],
    "stress": [
        "stress", "stressed", "pressure", "workload", "deadline", "overwhelmed",
        "too much", "burden", "responsibilities", "burnout", "overworked",
        "tension", "can't relax", "mentally drained", "emotionally drained",
        "family pressure", "exam pressure"
        , "school pressure", "college pressure", "financial pressure",
        "too many things", "too much pressure", "mental pressure"
    ],
    "physical_discomfort": [
        "nausea", "vomit", "chest pain", "chest tight", "headache",
        "stomach", "dizzy", "dizziness", "shortness of breath",
        "can't breathe", "heart", "sweat", "fever", "body pain",
        "body ache", "cold", "cough", "flu", "chills", "sore throat",
        "runny nose", "blocked nose", "sneezing", "cramps", "diarrhea",
        "loose motion", "vomiting", "back pain", "joint pain", "weakness"
        , "throat hurts", "throat pain", "high temperature", "feeling feverish",
        "nose blocked", "stuffy nose", "breathing problem", "body hurts",
        "malaria", "jaundice", "dengue", "typhoid", "migraine", "influenza",
        "yellow eyes", "yellow skin"
    ]
}
