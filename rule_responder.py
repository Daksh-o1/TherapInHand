import random
import re
import logging

from rule_response_data import RULE_RESPONSE_DATA, SYMPTOM_RESPONSE_DATA
from support_dataset import THERAPINHAND_SUPPORT_DATASET, THERAPINHAND_SUPPORT_MAPPINGS


RULE_MEMORY_KEY = "rule_response_memory"
RULE_LANGUAGE_KEY = "rule_response_language"
FOLLOW_UP_PROBABILITY = 0.35
CHAT_HISTORY_KEY = "chat_history"
MEMORY_TEXT_LIMIT = 220
LOGGER = logging.getLogger(__name__)
SUPPORT_CATEGORY_BY_CONDITION = {
    condition: category
    for category, conditions in THERAPINHAND_SUPPORT_MAPPINGS.get("categories", {}).items()
    for condition in conditions
}
MILD_MEDICATION_CATEGORIES = {"common_physical", "fitness_supplement"}
MILD_MEDICATION_CONDITIONS = {
    "flu",
    "viral_fever",
    "food_poisoning",
}
EMERGENCY_KEYWORDS = {
    "en": [
        "can't breathe", "cannot breathe", "trouble breathing", "shortness of breath",
        "chest pain", "fainting", "passed out", "confusion", "seizure",
        "suicidal", "kill myself", "self harm", "want to die",
    ],
    "hinglish": [
        "saans nahi aa rahi", "saans phool rahi", "sans nahi aa rahi", "sans phool rahi",
        "chest pain", "seene me dard", "faint", "behosh", "confusion",
        "suicidal", "khud ko nuksan", "marna hai", "jeena nahi",
    ],
}
SUPPORT_TOPIC_HINTS = {
    "anxiety": ["anxiety", "panic", "social_anxiety", "overthinking"],
    "stress": ["stress", "burnout", "emotional_exhaustion"],
    "fatigue": ["fatigue", "burnout", "low_motivation", "low_recovery", "gym_fatigue"],
    "physical_discomfort": [
        "headache", "fever", "cold", "cough", "sore_throat", "nausea", "dizziness",
        "dehydration", "stomach_pain", "body_ache", "fatigue", "migraine",
        "malaria", "dengue", "jaundice", "flu", "typhoid", "food_poisoning",
        "viral_fever", "creatine_dehydration", "muscle_soreness",
        "gym_fatigue", "preworkout_side_effects", "low_recovery",
        "protein_digestion_issues",
    ],
}
MENTAL_HEALTH_KEYWORDS = {
    "en": [
        "depression", "depressed", "lonely", "loneliness", "stress", "stressed",
        "anxiety", "anxious", "emotional exhaustion", "emotionally exhausted",
        "exhausted emotionally", "overthinking", "heartbreak", "hopeless",
        "empty", "numb", "burnout", "burned out",
    ],
    "hinglish": [
        "depression", "depressed", "lonely", "stress", "anxiety", "overthinking",
        "hopeless", "burnout", "emotionally exhausted", "heartbreak",
    ],
}
POSITIVE_EMOTION_KEYWORDS = {
    "en": [
        "happy", "excited", "relieved", "peaceful", "motivated", "hopeful",
        "grateful", "confident", "feeling better", "better now", "proud",
    ],
    "hinglish": [
        "happy", "excited", "relieved", "peaceful", "motivated", "hopeful",
        "grateful", "confident", "feeling better", "proud",
    ],
}
POSITIVE_RESPONSE_DATA = {
    "en": {
        "validation": [
            "That's really good to hear.",
            "I'm glad things are feeling a little lighter.",
            "You should give yourself credit for that progress.",
        ],
        "reinforcement": [
            "Moments like this matter, especially if things have felt heavy lately.",
            "It can help to notice what has been supporting you so you can keep some of that momentum going.",
            "Holding onto the small things that are helping can make this feeling easier to carry forward.",
        ],
        "suggestions": [
            "If you can, try to protect the habits that are helping, like rest, food, movement, sunlight, or staying connected with people who feel grounding.",
            "A simple way to build on it is to keep doing one or two things that helped you get here.",
            "If this shift feels meaningful, it may help to slow down for a second and appreciate it instead of rushing past it.",
        ],
        "follow_ups": [
            "Want to talk about what's been going well?",
            "Do you know what helped you feel this way today?",
            "",
        ],
    },
    "hinglish": {
        "validation": [
            "Ye sunke sach me achha laga.",
            "I'm glad cheezein thodi halki feel ho rahi hain.",
            "Is progress ka credit tumhe dena chahiye.",
        ],
        "reinforcement": [
            "Aise moments important hote hain, especially jab pehle sab heavy lag raha ho.",
            "Jo cheezein help kar rahi hain unhe notice karna useful ho sakta hai, taaki momentum bana rahe.",
            "Jo halka feel ho raha hai usko thoda hold karna bhi important hai.",
        ],
        "suggestions": [
            "Agar ho sake to un habits ko protect karo jo help kar rahi hain, jaise rest, paani, movement, sunlight, ya achhe logon se connected rehna.",
            "Ek simple next step ye ho sakta hai ki jo 1 ya 2 cheezein help kar rahi hain, unhe continue rakho.",
            "Agar ye shift meaningful lag rahi hai, to ek second rukkar isse appreciate karna bhi achha hota hai.",
        ],
        "follow_ups": [
            "Kya lagta hai, aaj kya cheez better gayi?",
            "Want to talk about what's been helping?",
            "",
        ],
    },
}
MENTAL_HEALTH_RESPONSE_DATA = {
    "en": {
        "validation": [
            "I'm really sorry you're dealing with that.",
            "That sounds heavy, and it makes sense that you're feeling worn down.",
            "I can understand why that would feel like a lot to carry.",
        ],
        "effects": {
            "depression": "Depression can make even simple things feel exhausting and heavy, and it can affect energy, sleep, motivation, and concentration.",
            "loneliness": "Loneliness can start to affect mood, confidence, energy, and the way everyday things feel.",
            "stress": "Stress can build up in your body and mind until everything starts feeling tighter, louder, and harder to manage.",
            "anxiety": "Anxiety can make your thoughts race and keep your body stuck in a constant state of tension or alertness.",
            "emotional_exhaustion": "Emotional exhaustion can leave you feeling flat, foggy, irritable, or like you have nothing left to give.",
            "overthinking": "Overthinking can trap you in loops where your mind keeps searching for certainty but only feels more drained.",
            "heartbreak": "Heartbreak can affect sleep, appetite, concentration, and make ordinary moments feel unusually painful.",
            "hopelessness": "Hopelessness can make it hard to imagine relief, even when what you're feeling may still shift with support and time.",
            "general": "When you're carrying emotional pain, it can affect sleep, energy, motivation, concentration, and your ability to do everyday things.",
        },
        "suggestions": [
            "For right now, it may help to keep the next step very small: water, a shower, a short walk, fresh air, or messaging one trusted person.",
            "Sometimes the goal is not to fix everything, just to reduce the intensity a little with food, hydration, rest, sunlight, movement, or connection.",
            "If this has been sticking around, talking to someone you trust or a mental health professional could make this feel less isolating.",
        ],
        "follow_ups": {
            "depression": "Has this been building slowly, or has something specific made it feel worse lately?",
            "loneliness": "Has this been feeling more like disconnection from people, or like you're around others but still feel alone?",
            "stress": "Is there one main thing putting the most pressure on you right now?",
            "anxiety": "Is your anxiety feeling more mental, more physical, or both right now?",
            "emotional_exhaustion": "Have you been feeling emotionally drained for a while, or did it spike recently?",
            "overthinking": "Does your mind keep circling one specific worry, or is it everything at once?",
            "heartbreak": "Did something happen recently, or has this been sitting with you for a while?",
            "hopelessness": "Are you feeling safe right now while you're carrying this?",
            "general": "Has this been building slowly, or did something specific trigger it?",
        },
    },
    "hinglish": {
        "validation": [
            "Mujhe afsos hai ki tum itna heavy feel kar rahe ho.",
            "Ye kaafi tough lag raha hai, aur aisa feel karna samajh aata hai.",
            "Main samajh sakta hoon ki ye kitna draining lag sakta hai.",
        ],
        "effects": {
            "general": "Jab emotional load zyada ho jata hai, to energy, sleep, motivation, focus, sab effect ho sakte hain.",
        },
        "suggestions": [
            "Abhi ke liye next step bahut chhota rakho: paani piyo, thodi fresh air lo, face wash karo, ya kisi trusted insaan ko message karo.",
            "Goal sab kuch solve karna nahi hai, bas intensity ko thoda kam karna hai with rest, hydration, sunlight, movement, ya connection.",
            "Agar ye kaafi time se chal raha hai, kisi trusted person ya mental health professional se baat karna genuinely help kar sakta hai.",
        ],
        "follow_ups": {
            "general": "Ye dheere dheere build hua hai, ya kuch specific hua tha jisne trigger kiya?",
        },
    },
}
MENTAL_SUBTOPIC_MAP = {
    "depression": "depression",
    "depressed": "depression",
    "lonely": "loneliness",
    "loneliness": "loneliness",
    "stress": "stress",
    "stressed": "stress",
    "anxiety": "anxiety",
    "anxious": "anxiety",
    "emotionally exhausted": "emotional_exhaustion",
    "emotional exhaustion": "emotional_exhaustion",
    "overthinking": "overthinking",
    "heartbreak": "heartbreak",
    "hopeless": "hopelessness",
    "hopelessness": "hopelessness",
}
FRIENDLY_FALLBACKS = {
    "en": {
        "default": [
            "I want to help, but I need a little more detail to answer well.",
            "I can keep going with this. Give me one more detail and I will be more specific.",
            "I did not get enough signal from that alone, but we can still sort it out together.",
        ],
        "casual": [
            "We can keep it light. Want a joke, a fun fact, or just normal chat?",
            "Happy to switch gears. We can chat casually if you want.",
            "We can go with something lighter here. Pick a topic and I will roll with it.",
        ],
        "medical": [
            "I can give general self-care guidance if you tell me the main symptom, how long it has been going on, and whether anything else came with it.",
            "If this is physical, tell me the symptom clearly and I can give practical next steps plus warning signs.",
            "I can help with basic symptom guidance. Tell me what hurts or what is bothering you most.",
        ],
        "emotional": [
            "If this is feeling emotional, tell me whether it is more sadness, anxiety, stress, or overwhelm and I will meet you there.",
            "If this is a heavy-feeling kind of message, give me one line on what is hitting hardest right now.",
            "If you want support mode, tell me what feels most intense right now and I will keep it focused.",
        ],
        "greeting": [
            "Hi. What do you want to talk about?",
            "Hey. What can I help with right now?",
            "Hello. Want to talk health, feelings, or something casual?",
        ],
        "humor": [
            "I can do jokes too. Say the word and I will give you a quick one.",
            "Want a light joke or something more absurd?",
            "I can switch into fun mode. Ask for a joke and I am in.",
        ],
    },
    "hinglish": {
        "default": [
            "Main help karna chahta hoon, bas thoda aur clear detail chahiye.",
            "Ek aur detail do, phir main zyada useful answer de paunga.",
            "Is line se poora signal nahi mila, but hum isse sort kar sakte hain.",
        ],
        "casual": [
            "Light rakhna hai to casual chat bhi kar sakte hain.",
            "Topic switch karna hai to bolo, main usi mood me aa jaunga.",
            "Normal chat bhi bilkul theek hai. Bolo kis topic pe jaana hai.",
        ],
        "medical": [
            "Agar ye body symptom hai to exact symptom, duration, aur saath ke signs batao. Main practical guidance dunga.",
            "Physical issue hai to clear batao kya problem ho rahi hai, phir main next steps aur warning signs bataunga.",
            "Basic symptom guidance de sakta hoon. Batao sabse zyada kya bother kar raha hai.",
        ],
        "emotional": [
            "Agar ye emotional side ka hai to bolo sadness, anxiety, stress, ya overwhelm me se kya zyada strong lag raha hai.",
            "Heavy feel ho raha hai to ek line me batao abhi sabse zyada kya hit kar raha hai.",
            "Support mode chahiye to main hoon. Bas thoda clear batao kis cheez ka weight zyada hai.",
        ],
        "greeting": [
            "Hi. Bolo kis baat pe help chahiye?",
            "Hello. Health, emotions, ya casual chat me se kya karna hai?",
            "Hey. Main ready hoon, bolo.",
        ],
        "humor": [
            "Joke mode bhi on kar sakta hoon. Bolo to ek halka sa suna deta hoon.",
            "Fun mode chahiye to bolo, ek quick joke deta hoon.",
            "Humor bhi kar lenge. Bas bolo joke chahiye.",
        ],
    },
}
FOLLOW_UP_QUERY_MARKERS = [
    "can you explain more", "explain more", "elaborate", "why", "how", "what do you mean",
    "tell me more", "how does that happen", "what causes that", "can you elaborate",
    "could you explain", "more about that", "what about", "and what about",
]
MEDICATION_QUERY_MARKERS = [
    "medicine", "medication", "tablet", "pill", "paracetamol", "ibuprofen",
    "what helps", "what can i take", "what should i take", "otc",
]
SPECIAL_FOLLOW_UP_OVERRIDES = {
    "dehydration": {
        "urine": {
            "en": [
                "Usually pale yellow urine suggests you are better hydrated, while darker yellow or amber urine can happen when the body is low on fluids.",
                "It is only a rough clue, though. First-morning urine can look darker, and vitamins can change the color too.",
                "What matters more is the overall pattern with thirst, dry mouth, dizziness, low urine frequency, and whether fluids are helping you feel steadier.",
            ],
            "hinglish": [
                "Usually pale yellow urine better hydration ka rough sign hota hai, jabki dark yellow ya amber color low fluids me dikh sakta hai.",
                "Ye perfect test nahi hota. Subah ka first urine dark ho sakta hai, aur vitamins bhi color change kar sakte hain.",
                "Pattern zyada matter karta hai: pyaas, dry mouth, dizziness, urine kam aana, aur fluids se body steady feel ho rahi hai ya nahi.",
            ],
        },
    },
}
GENERIC_PHYSICAL_RESPONSE_DATA = {
    "en": {
        "validation": "That sounds uncomfortable.",
        "causes": "Physical symptoms like this can come from something mild like irritation, infection, dehydration, poor sleep, or something else that needs a closer look.",
        "care": "For now, rest if you can, keep up fluids, avoid anything that makes it worse, and keep an eye on whether the symptom is easing or getting stronger.",
        "medication": "Only use over-the-counter medicine if it fits the symptom and you can take it safely as directed on the label.",
        "warning": "Please get medical care sooner if it becomes severe, keeps getting worse, or comes with red flags like breathing trouble, chest pain, fainting, confusion, repeated vomiting, or dehydration.",
        "follow_up": "If you want, tell me where it hurts, how long it has been going on, and whether anything else came with it.",
    },
    "hinglish": {
        "validation": "Ye uncomfortable lag raha hai.",
        "causes": "Aise physical symptoms kabhi mild irritation, infection, dehydration, low sleep, ya kisi aur cause se aa sakte hain jise thoda closely dekhna padta hai.",
        "care": "Abhi ke liye rest karo, fluids lo, jo cheez isse worse kar rahi ho usse avoid karo, aur dekho symptom settle ho raha hai ya strong hota ja raha hai.",
        "medication": "Over-the-counter medicine tabhi lo jab symptom ke hisaab se sahi ho aur tum use safely label ke mutabik le sako.",
        "warning": "Agar ye severe ho, worse hota jaye, ya breathing problem, chest pain, fainting, confusion, repeated vomiting, ya dehydration jaisi red flags ho to jaldi medical care lo.",
        "follow_up": "Chaho to batao pain ya symptom kahan hai, kab se hai, aur saath me aur kya feel ho raha hai.",
    },
}
RECENT_STYLE_LIMIT = 5
RECENT_BLUEPRINT_LIMIT = 6
RECENT_PHRASE_LIMIT = 14
RECENT_STRUCTURE_LIMIT = 8
SUPPORT_STYLE_PROFILES = {
    "casual": {"blueprints": ["minimal_support", "question_first", "casual_observation"], "follow_up_bias": 0.55},
    "empathetic": {"blueprints": ["supportive_full", "explain_then_help", "followup_driven"], "follow_up_bias": 0.6},
    "direct": {"blueprints": ["direct_guidance", "solution_first", "practical_direct"], "follow_up_bias": 0.25},
    "short": {"blueprints": ["minimal_support", "direct_guidance", "question_only"], "follow_up_bias": 0.15},
    "analytical": {"blueprints": ["explain_then_help", "supportive_full", "question_first"], "follow_up_bias": 0.35},
    "questioning": {"blueprints": ["question_first", "followup_driven", "question_only"], "follow_up_bias": 0.8},
    "supportive_friend": {"blueprints": ["casual_observation", "supportive_full", "solution_first"], "follow_up_bias": 0.5},
    "calm": {"blueprints": ["minimal_support", "explain_then_help", "supportive_full"], "follow_up_bias": 0.3},
    "motivational": {"blueprints": ["solution_first", "direct_guidance", "minimal_support"], "follow_up_bias": 0.2},
    "reassuring": {"blueprints": ["minimal_support", "supportive_full", "explain_then_help"], "follow_up_bias": 0.35},
}
SUPPORT_BLUEPRINTS = {
    "supportive_full": ["friendly_response", "symptom_explanation", "solutions", "medications", "warnings", "follow_ups"],
    "explain_then_help": ["symptom_explanation", "solutions", "warnings", "follow_ups"],
    "solution_first": ["solutions", "friendly_response", "medications", "warnings", "follow_ups"],
    "question_first": ["follow_ups", "friendly_response", "symptom_explanation", "solutions", "warnings"],
    "casual_observation": ["friendly_response", "symptom_explanation", "follow_ups"],
    "minimal_support": ["friendly_response", "solutions", "warnings"],
    "direct_guidance": ["solutions", "warnings", "follow_ups"],
    "followup_driven": ["friendly_response", "follow_ups", "solutions"],
    "question_only": ["follow_ups", "friendly_response"],
    "practical_direct": ["solutions", "medications", "warnings"],
}
STYLE_TRANSITIONS = {
    "en": {
        "casual": ["Honestly, ", "Yeah, ", "Sometimes, "],
        "empathetic": ["I get why that feels like a lot. ", "That can hit harder than people realize. "],
        "direct": ["First thing, ", "Right now, ", "At this point, "],
        "short": ["Okay, ", "Yeah, ", ""],
        "analytical": ["A simple read on this is: ", "What stands out here is that "],
        "questioning": ["Quick question first: ", "Before anything else, "],
        "supportive_friend": ["That sounds rough honestly. ", "I'm not surprised that feels draining. "],
        "calm": ["Let's keep this steady. ", "One calm step at a time. "],
        "motivational": ["You do not need to force everything at once. ", "Small reset first. "],
        "reassuring": ["This does not automatically mean something serious. ", "It makes sense to slow this down a bit. "],
    },
    "hinglish": {
        "casual": ["Honestly, ", "Haan, ", "Kabhi kabhi, "],
        "empathetic": ["Samajh aa raha hai ye heavy lag sakta hai. ", "Ye log sochte hain usse zyada rough feel ho sakta hai. "],
        "direct": ["Abhi ke liye, ", "Sabse pehle, ", "Filhal, "],
        "short": ["Theek, ", "Haan, ", ""],
        "analytical": ["Simple read ye hai ki ", "Jo sabse zyada stand out karta hai wo ye hai ki "],
        "questioning": ["Ek quick sawal pehle: ", "Aage badhne se pehle, "],
        "supportive_friend": ["Bhai, ye rough lag raha hai. ", "Sach me ye draining ho sakta hai. "],
        "calm": ["Isko calmly lete hain. ", "Ek steady step pe focus karte hain. "],
        "motivational": ["Sab kuch ek saath push karne ki zarurat nahi hai. ", "Chhota reset pehle. "],
        "reassuring": ["Ye automatically worst-case nahi hota. ", "Thoda slow hoke dekhna fair rahega. "],
    },
}
CASUAL_PATTERN_BANK = {
    "joke": {
        "en": [
            "Why did the computer go to therapy? It had too many tabs open.",
            "Tiny joke break: my water bottle and I are in a serious relationship. I keep going back to it.",
            "Okay, one soft joke: I told my stress to take a day off. It said it was already working remotely.",
        ],
        "hinglish": [
            "Chhota sa joke: mera stress bhi full-time job karta hai, bas salary mujhe nahi milti.",
            "Ek halka joke suno: phone bola low battery hai, maine bola same yaar.",
            "Mini joke break: paani ki bottle aur mera rishta serious hai, main uske paas baar baar laut aata hoon.",
        ],
    },
    "how_are_you": {
        "en": [
            "I'm here and ready to help. What is going on on your side?",
            "Doing okay here. What is your day feeling like?",
            "I'm around. What do you want to talk about?",
        ],
        "hinglish": [
            "Main yahin hoon. Tumhare side kya chal raha hai?",
            "Main theek hoon. Batao, tumhara din kaisa ja raha hai?",
            "Main ready hoon. Tum kya scene leke aaye ho aaj?",
        ],
    },
    "identity": {
        "en": [
            "I'm TherapInHand's support chat, so I can do calm check-ins, symptom guidance, and everyday conversation too.",
            "I'm the TherapInHand chat support system. Health help is my main lane, but I can keep things conversational too.",
            "I'm your TherapInHand support chat. I try to keep things practical, safe, and human.",
        ],
        "hinglish": [
            "Main TherapInHand ka support chat hoon. Health guidance ke saath normal conversation bhi handle kar leta hoon.",
            "Main TherapInHand support bot hoon, but try karta hoon ki baat robotic na lage.",
            "Main tumhara TherapInHand chat support hoon. Practical bhi, supportive bhi rehne ki koshish karta hoon.",
        ],
    },
    "general_chat": {
        "en": [
            "Of course. What's up?",
            "I'm listening.",
            "How's your day going?",
            "Tell me what's on your mind.",
            "We can keep this casual if you want.",
        ],
        "hinglish": [
            "Haan, casual bhi baat kar sakte hain.",
            "Main sun raha hoon, bolo.",
            "Tumhare dimaag me kya chal raha hai?",
            "Aaj ka din kaisa ja raha hai?",
            "Bilkul, normal chat bhi theek hai.",
        ],
    },
}


def _normalize_text(text):
    return " ".join((text or "").strip().lower().split())


def _topic_label(lang, topic):
    language_data = RULE_RESPONSE_DATA.get(lang, RULE_RESPONSE_DATA["en"])
    return language_data.get("topic_labels", {}).get(topic, topic or "general")


def _choose(pool, exclude=None):
    options = [item for item in pool if item and item != exclude]
    if not options:
        options = [item for item in pool if item]
    return random.choice(options) if options else ""


def _contains_keyword(text, keyword):
    normalized_text = _normalize_text(text)
    normalized_keyword = _normalize_text(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    if " " in normalized_keyword:
        return normalized_keyword in normalized_text
    return re.search(rf"\b{re.escape(normalized_keyword)}\b", normalized_text) is not None


def _compact_text(text, limit=MEMORY_TEXT_LIMIT):
    return " ".join(str(text or "").split())[:limit].strip()


def _resolve_language(session_store):
    lang = (session_store.get(RULE_LANGUAGE_KEY) or session_store.get("lang") or "en").lower()
    return lang if lang in RULE_RESPONSE_DATA else "en"


def _symptom_language_data(lang):
    return SYMPTOM_RESPONSE_DATA.get(lang) or SYMPTOM_RESPONSE_DATA.get("en") or {}


def _response_memory(session_store=None):
    memory = (session_store or {}).get(RULE_MEMORY_KEY, {}) if session_store else {}
    return memory if isinstance(memory, dict) else {}


def _memory_list(memory, key):
    values = memory.get(key, []) or []
    return values if isinstance(values, list) else []


def _text_fingerprint(text, words=5):
    normalized = re.sub(r"[^a-z0-9\u0900-\u097F\s]", "", _normalize_text(text))
    return " ".join(normalized.split()[:words]).strip()


def _structure_signature(parts):
    return "|".join(parts)


def _style_candidates(intent, sentiment, topic, condition=None, category=None, support_lang="en", user_text=""):
    lowered = _normalize_text(user_text)
    if intent == "emergency":
        return ["direct", "calm", "short"]
    if any(marker in lowered for marker in ["severe", "confusion", "fainting", "passed out", "chest pain", "trouble breathing", "behosh", "saans", "shortness of breath"]):
        return ["direct", "calm"]
    if category == "mental_emotional":
        if sentiment == "very_negative":
            return ["calm", "empathetic", "reassuring", "questioning"]
        if "panic" in lowered or topic == "anxiety":
            return ["calm", "questioning", "reassuring", "direct"]
        return ["empathetic", "supportive_friend", "questioning", "casual"]
    if category == "disease_related":
        return ["direct", "analytical", "reassuring", "calm"]
    if category in {"common_physical", "fitness_supplement"}:
        if condition in {"creatine_dehydration", "preworkout_side_effects", "gym_fatigue", "low_recovery"}:
            return ["casual", "direct", "supportive_friend", "analytical"]
        return ["reassuring", "direct", "casual", "analytical"]
    if intent == "solution_request":
        return ["direct", "motivational", "casual", "analytical"]
    if intent == "general_query":
        return ["casual", "short", "questioning", "supportive_friend"]
    return ["casual", "empathetic", "direct", "reassuring"]


def _select_style(intent, sentiment, topic, condition=None, category=None, support_lang="en", user_text="", session_store=None):
    memory = _response_memory(session_store)
    recent_styles = _memory_list(memory, "recent_styles")[-RECENT_STYLE_LIMIT:]
    candidates = _style_candidates(
        intent=intent,
        sentiment=sentiment,
        topic=topic,
        condition=condition,
        category=category,
        support_lang=support_lang,
        user_text=user_text,
    )
    filtered = [style for style in candidates if style not in recent_styles[-2:]]
    style = random.choice(filtered or candidates or list(SUPPORT_STYLE_PROFILES))
    return style, recent_styles


def _style_transition(style, support_lang, recent_phrases=None):
    recent_phrases = set(recent_phrases or [])
    options = STYLE_TRANSITIONS.get(support_lang, STYLE_TRANSITIONS["en"]).get(style, [""])
    filtered = [item for item in options if _text_fingerprint(item) not in recent_phrases]
    return random.choice(filtered or options or [""])


def _supports_follow_up(style, blueprint, include_warning=False):
    if include_warning and blueprint in {"minimal_support", "direct_guidance", "practical_direct"}:
        return False
    bias = SUPPORT_STYLE_PROFILES.get(style, {}).get("follow_up_bias", FOLLOW_UP_PROBABILITY)
    return random.random() < bias


def _select_blueprint(style, mode, include_medication=False, include_warning=False, include_follow_up=False, session_store=None):
    memory = _response_memory(session_store)
    recent_blueprints = _memory_list(memory, "recent_blueprints")[-RECENT_BLUEPRINT_LIMIT:]
    recent_structures = _memory_list(memory, "recent_structures")[-RECENT_STRUCTURE_LIMIT:]
    candidates = SUPPORT_STYLE_PROFILES.get(style, {}).get("blueprints", ["supportive_full"])
    allowed = []
    for blueprint in candidates:
        sections = SUPPORT_BLUEPRINTS.get(blueprint, [])
        if mode == "short" and len(sections) > 4 and blueprint == "supportive_full":
            continue
        if not include_medication and "medications" in sections and blueprint == "practical_direct":
            continue
        if include_warning and "warnings" not in sections and blueprint in {"minimal_support", "question_only"}:
            continue
        structure = _structure_signature(sections)
        if blueprint not in recent_blueprints[-2:] and structure not in recent_structures[-2:]:
            allowed.append(blueprint)
    blueprint = random.choice(allowed or candidates or ["supportive_full"])
    return blueprint, recent_blueprints, recent_structures


def _filter_sections_for_blueprint(blueprint, include_medication=False, include_warning=False, include_follow_up=False):
    sections = []
    for section in SUPPORT_BLUEPRINTS.get(blueprint, ["friendly_response", "solutions"]):
        if section == "medications" and not include_medication:
            continue
        if section == "warnings" and not include_warning:
            continue
        if section == "follow_ups" and not include_follow_up:
            continue
        sections.append(section)
    return sections


def _casual_query_kind(text):
    lowered = _normalize_text(text)
    if any(marker in lowered for marker in ["tell me a joke", "make me laugh", "say something funny", "tell me something funny", "joke"]):
        return "joke"
    if any(marker in lowered for marker in ["who are you", "what are you", "what can you do", "tell me about yourself"]):
        return "identity"
    if any(marker in lowered for marker in ["how are you", "whats up", "what's up"]):
        return "how_are_you"
    if any(marker in lowered for marker in ["chat with me", "talk to me", "say something fun", "say something interesting"]):
        return "general_chat"
    return ""


def _build_casual_response(intent, topic, lang, sentiment="neutral", session_store=None, user_text=""):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    casual_kind = _casual_query_kind(user_text)
    if intent in {"greeting", "casual_checkin", "gratitude", "goodbye"}:
        casual_kind = casual_kind or "general_chat"
    if not casual_kind and not (intent == "general_query" and topic == "general"):
        return None
    memory = _response_memory(session_store)
    recent_phrases = set(_memory_list(memory, "recent_phrases")[-RECENT_PHRASE_LIMIT:])
    pool = CASUAL_PATTERN_BANK.get(casual_kind or "general_chat", {}).get(support_lang, [])
    filtered = [item for item in pool if _text_fingerprint(item) not in recent_phrases]
    base = random.choice(filtered or pool) if pool else ""
    if not base:
        return None
    follow_up_pool = {
        "en": ["What is on your mind?", "Want to keep it light or talk about something real?", ""],
        "hinglish": ["Kya scene chal raha hai?", "Light rakhna hai ya kuch real baat karni hai?", ""],
    }
    follow_up = random.choice(follow_up_pool.get(support_lang, [""]))
    parts = [base]
    if follow_up and random.random() < 0.45 and casual_kind not in {"joke", "identity"}:
        parts.append(follow_up)
    return {
        "kind": "casual",
        "subtopic": casual_kind or intent,
        "category": "casual",
        "mode": "short",
        "style": "casual",
        "blueprint": "minimal_support",
        "parts": parts,
        "selected_blocks": {"friendly_response": base, "follow_ups": follow_up},
        "skipped_sections": ["symptom_explanation", "solutions", "medications", "warnings"],
    }


def _support_language(lang, user_text=""):
    if lang == "hinglish":
        return "hinglish"
    if lang == "hi" and not re.search(r"[\u0900-\u097F]", user_text or ""):
        return "hinglish"
    if lang == "en":
        return "en"
    return None


def _support_dataset(lang, user_text=""):
    support_lang = _support_language(lang, user_text=user_text)
    if not support_lang:
        return {}
    return THERAPINHAND_SUPPORT_DATASET.get(support_lang, {})


def _recent_bot_responses(session_store=None, limit=4):
    history = session_store.get(CHAT_HISTORY_KEY, []) if session_store else []
    recent = []
    for item in history[-limit:]:
        if isinstance(item, dict) and item.get("bot"):
            recent.append(item.get("bot", ""))
    return recent


def _seen_in_recent(text, session_store=None, previous_response=""):
    if not text:
        return False
    haystacks = [previous_response] + _recent_bot_responses(session_store=session_store)
    return any(text in haystack for haystack in haystacks if haystack)


def _condition_alias_scores(user_text, support_lang):
    alias_map = THERAPINHAND_SUPPORT_MAPPINGS.get("condition_aliases", {}).get(support_lang, {})
    scores = {}
    for condition, aliases in alias_map.items():
        score = sum(1 for alias in aliases if _contains_keyword(user_text, alias))
        if score:
            scores[condition] = score
    return scores


def _map_detected_subtopic_to_condition(detected):
    if not detected:
        return None
    name = detected.get("name")
    if name == "cold_flu":
        return "cold"
    if name in SUPPORT_CATEGORY_BY_CONDITION:
        return name
    return None


def _match_condition_from_topic(user_text, topic, support_lang):
    hints = SUPPORT_TOPIC_HINTS.get(topic, [])
    if not hints:
        return None
    alias_map = THERAPINHAND_SUPPORT_MAPPINGS.get("condition_aliases", {}).get(support_lang, {})
    scores = {}
    for condition in hints:
        aliases = alias_map.get(condition, [])
        score = sum(1 for alias in aliases if _contains_keyword(user_text, alias))
        if score:
            scores[condition] = score
    if scores:
        return max(scores, key=scores.get)
    if topic == "anxiety":
        return "anxiety"
    if topic == "stress":
        return "stress"
    if topic == "fatigue":
        return "fatigue"
    return None


def _detect_support_condition(user_text, lang, topic, detected, entities):
    support_lang = _support_language(lang, user_text=user_text)
    if not support_lang:
        return None, support_lang, {}

    alias_scores = _condition_alias_scores(user_text, support_lang)
    symptoms = entities.get("symptom", [])
    causes = entities.get("cause", [])
    supplements = entities.get("supplement", [])

    if "creatine" in supplements and "dehydration" in causes and set(symptoms) & {"headache", "dizziness", "fatigue"}:
        return "creatine_dehydration", support_lang, alias_scores
    if "preworkout" in supplements and any(
        item in _normalize_text(user_text) for item in ["jitters", "racing", "anxious", "panic", "fast heartbeat"]
    ):
        return "preworkout_side_effects", support_lang, alias_scores
    if "protein_powder" in supplements and any(
        item in _normalize_text(user_text) for item in ["bloating", "gas", "stomach", "nausea", "pet"]
    ):
        return "protein_digestion_issues", support_lang, alias_scores

    mapped = _map_detected_subtopic_to_condition(detected)
    if mapped:
        return mapped, support_lang, alias_scores

    if alias_scores:
        best_condition = max(alias_scores, key=alias_scores.get)
        return best_condition, support_lang, alias_scores

    topic_condition = _match_condition_from_topic(user_text, topic, support_lang)
    return topic_condition, support_lang, alias_scores


def _choose_support_line(pool, session_store=None, previous_response="", exclude_lines=None, blocked_phrases=None):
    exclude_lines = set(exclude_lines or [])
    blocked_phrases = set(blocked_phrases or [])
    filtered = [
        item for item in pool
        if item
        and item not in exclude_lines
        and _text_fingerprint(item) not in blocked_phrases
        and not _seen_in_recent(item, session_store=session_store, previous_response=previous_response)
    ]
    if not filtered:
        filtered = [item for item in pool if item and item not in exclude_lines and _text_fingerprint(item) not in blocked_phrases]
    if not filtered:
        filtered = [item for item in pool if item and item not in exclude_lines]
    return random.choice(filtered) if filtered else ""


def _entity_context_line(entities, lang):
    symptoms = entities.get("symptom", [])
    causes = entities.get("cause", [])
    supplements = entities.get("supplement", [])
    medicines = entities.get("medicine", [])
    duration = entities.get("duration", [])
    severity = entities.get("severity", [])

    symptom_label = symptoms[0].replace("_", " ") if symptoms else "symptoms"
    cause_label = causes[0].replace("_", " ") if causes else ""
    supplement_label = supplements[0].replace("_", " ") if supplements else ""
    medicine_label = medicines[0].replace("_", " ") if medicines else ""
    duration_label = duration[0].replace("_", " ") if duration else ""
    severity_label = severity[0].replace("_", " ") if severity else ""

    if lang == "hinglish":
        if symptom_label == "headache" and cause_label == "dehydration" and supplement_label == "creatine":
            return "Creatine ke saath dehydration ho to headache aur zyada trigger ho sakta hai, especially jab water intake low ho."
        if cause_label and supplement_label:
            return f"{symptom_label} shayad {cause_label} aur {supplement_label} dono se push ho raha ho."
        if cause_label:
            line = f"{symptom_label} kabhi kabhi {cause_label} se aur worse feel ho sakta hai."
            if duration_label:
                line += f" Since ye {duration_label.replace('_', ' ')} se chal raha hai, pattern observe karna useful hoga."
            return line
        if supplement_label:
            return f"Kabhi kabhi {supplement_label} ke around {symptom_label} tab zyada feel hota hai jab sleep, food, ya hydration off ho."
        if medicine_label:
            return f"Ye bhi note karna useful ho sakta hai ki {symptom_label} {medicine_label} se pehle tha ya baad me."
        if severity_label or duration_label:
            details = " aur ".join(item.replace("_", " ") for item in [severity_label, duration_label] if item)
            return f"Jo baat isko {details} bana rahi hai, us wajah se thoda extra caution rakhna sahi rahega."
        return ""

    if symptom_label == "headache" and cause_label == "dehydration" and supplement_label == "creatine":
        return "Headaches can show up when dehydration and creatine overlap, especially if fluid intake has been low."
    if cause_label and supplement_label:
        return f"The {symptom_label} could be getting pushed by both {cause_label} and {supplement_label} together."
    if cause_label:
        line = f"{symptom_label.capitalize()} can sometimes feel worse when {cause_label} is in the mix."
        if duration_label:
            line += f" Since this has been going on {duration_label.replace('_', ' ')}, the pattern is worth watching."
        return line
    if supplement_label:
        return f"Sometimes {symptom_label} shows up around supplements like {supplement_label}, especially when hydration, food, or sleep is off."
    if medicine_label:
        return f"It may help to notice whether the {symptom_label} changed before or after taking {medicine_label}."
    if severity_label or duration_label:
        details = " and ".join(item.replace("_", " ") for item in [severity_label, duration_label] if item)
        return f"The fact that this feels {details} makes it worth taking a little more seriously."
    return ""


def _append_unique(base_text, extra_text):
    if not extra_text:
        return base_text
    if not base_text:
        return extra_text
    if extra_text in base_text:
        return base_text
    return f"{base_text} {extra_text}"


def _contains_any(text, keywords):
    return any(_contains_keyword(text, keyword) for keyword in keywords or [])


def _has_emergency_signal(text, support_lang):
    return _contains_any(text, EMERGENCY_KEYWORDS.get(support_lang, []) + EMERGENCY_KEYWORDS.get("en", []))


def _matched_keywords(text, keywords):
    return [keyword for keyword in keywords if _contains_keyword(text, keyword)]


def _detect_positive_subtopic(text, support_lang):
    matches = _matched_keywords(text, POSITIVE_EMOTION_KEYWORDS.get(support_lang, []) + POSITIVE_EMOTION_KEYWORDS.get("en", []))
    return matches[0] if matches else ""


def _detect_mental_subtopic(text, support_lang):
    matches = _matched_keywords(text, MENTAL_HEALTH_KEYWORDS.get(support_lang, []) + MENTAL_HEALTH_KEYWORDS.get("en", []))
    for match in matches:
        subtopic = MENTAL_SUBTOPIC_MAP.get(match)
        if subtopic:
            return subtopic
    return "general" if matches else ""


def _classify_response_route(intent, topic, lang, user_text=""):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    normalized = _normalize_text(user_text)
    positive_subtopic = _detect_positive_subtopic(normalized, support_lang)
    mental_subtopic = _detect_mental_subtopic(normalized, support_lang)
    casual_kind = _casual_query_kind(user_text)
    physical_signal = topic == "physical_discomfort" or intent in {"symptom_report", "solution_request"}

    if intent == "emergency" or _has_emergency_signal(normalized, support_lang):
        return {"category": "crisis", "subtopic": "crisis", "confidence": 1.0, "dataset_match": "none", "fallback_reason": ""}
    if positive_subtopic:
        return {"category": "positive_emotion", "subtopic": positive_subtopic, "confidence": 0.98, "dataset_match": "positive_emotion_keywords", "fallback_reason": ""}
    if mental_subtopic or intent == "emotional_support" or topic in {"anxiety", "stress", "fatigue"}:
        return {"category": "mental_emotional", "subtopic": mental_subtopic or topic or "general", "confidence": 0.96 if mental_subtopic else 0.82, "dataset_match": "mental_health_keywords" if mental_subtopic else "intent_or_topic", "fallback_reason": ""}
    if physical_signal:
        return {"category": "physical_symptom", "subtopic": topic or "physical_discomfort", "confidence": 0.9, "dataset_match": "physical_signal", "fallback_reason": ""}
    if casual_kind or intent in {"greeting", "casual_checkin", "gratitude", "goodbye"}:
        return {"category": "casual_conversation", "subtopic": casual_kind or intent, "confidence": 0.9, "dataset_match": "casual_pattern", "fallback_reason": ""}
    return {"category": "ai_fallback", "subtopic": "general", "confidence": 0.4, "dataset_match": "none", "fallback_reason": "no_specific_route_match"}


def _build_positive_response(lang, user_text="", session_store=None):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    bank = POSITIVE_RESPONSE_DATA.get(support_lang, POSITIVE_RESPONSE_DATA["en"])
    parts = [
        _choose_support_line(bank.get("validation", []), session_store=session_store),
        _choose_support_line(bank.get("reinforcement", []), session_store=session_store),
        _choose_support_line(bank.get("suggestions", []), session_store=session_store),
    ]
    follow_up = _choose_support_line(bank.get("follow_ups", []), session_store=session_store)
    if follow_up:
        parts.append(follow_up)
    return [part for part in parts if part]


def _build_mental_health_response(lang, subtopic="general", user_text="", session_store=None):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    bank = MENTAL_HEALTH_RESPONSE_DATA.get(support_lang, MENTAL_HEALTH_RESPONSE_DATA["en"])
    effects = bank.get("effects", {})
    follow_ups = bank.get("follow_ups", {})
    parts = [
        _choose_support_line(bank.get("validation", []), session_store=session_store),
        effects.get(subtopic) or effects.get("general", ""),
        _choose_support_line(bank.get("suggestions", []), session_store=session_store),
        follow_ups.get(subtopic) or follow_ups.get("general", ""),
    ]
    return [part for part in parts if part]


def friendly_fallback_message(lang, user_text=""):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    bank = FRIENDLY_FALLBACKS.get(support_lang, FRIENDLY_FALLBACKS["en"])
    lowered = _normalize_text(user_text)
    if any(marker in lowered for marker in ["hi", "hello", "hey", "good morning"]):
        key = "greeting"
    elif any(marker in lowered for marker in ["joke", "funny", "laugh"]):
        key = "humor"
    elif any(marker in lowered for marker in ["sad", "anxious", "anxiety", "lonely", "hopeless", "panic", "overwhelmed"]):
        key = "emotional"
    elif any(marker in lowered for marker in ["fever", "cold", "cough", "headache", "pain", "medicine", "symptom", "dizziness"]):
        key = "medical"
    elif any(marker in lowered for marker in ["chat", "casual", "movie", "music", "sports", "python", "coding"]):
        key = "casual"
    else:
        key = "default"
    return _choose(bank.get(key, []) or bank.get("default", []))


def _build_generic_physical_response(lang, user_text=""):
    support_lang = _support_language(lang, user_text=user_text) or "en"
    bank = GENERIC_PHYSICAL_RESPONSE_DATA.get(support_lang, GENERIC_PHYSICAL_RESPONSE_DATA["en"])
    return [
        bank.get("validation", ""),
        bank.get("causes", ""),
        bank.get("care", ""),
        bank.get("medication", ""),
        bank.get("warning", ""),
        bank.get("follow_up", ""),
    ]


def _is_follow_up_query(text):
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in FOLLOW_UP_QUERY_MARKERS)


def _is_medication_query(text):
    normalized = _normalize_text(text)
    return any(marker in normalized for marker in MEDICATION_QUERY_MARKERS)


def _active_chat_context(session_store=None):
    history = session_store.get(CHAT_HISTORY_KEY, []) if session_store else []
    for item in reversed(history):
        if isinstance(item, dict) and (item.get("category") or item.get("topic")):
            return item
    return {}


def _context_follow_up_override(subtopic, user_text, support_lang):
    overrides = SPECIAL_FOLLOW_UP_OVERRIDES.get(subtopic, {})
    normalized = _normalize_text(user_text)
    for keyword, localized in overrides.items():
        if keyword in normalized:
            return localized.get(support_lang, localized.get("en", []))
    return []


def _context_follow_up_parts(condition_data, follow_up_kind, session_store=None, previous_response="", previous_bot=""):
    if follow_up_kind == "medication":
        primary_keys = ["medications", "solutions", "warnings"]
    else:
        primary_keys = ["symptom_explanation", "solutions", "warnings"]
    parts = []
    used = set()
    for key in primary_keys:
        choice = _choose_support_line(
            condition_data.get(key, []),
            session_store=session_store,
            previous_response=previous_response or previous_bot,
            exclude_lines=used,
        )
        if choice:
            parts.append(choice)
            used.add(choice)
        if len(parts) >= 3:
            break
    return parts


def _build_context_follow_up_response(intent, topic, lang, session_store=None, user_text=""):
    if not _is_follow_up_query(user_text):
        return None
    context = _active_chat_context(session_store)
    if not context:
        return None

    support_lang = _support_language(lang, user_text=user_text) or "en"
    category = context.get("category", "ai_fallback")
    subtopic = context.get("subtopic") or context.get("topic") or "general"
    previous_bot = context.get("bot", "")
    follow_up_kind = "medication" if _is_medication_query(user_text) else "explanation"

    if category == "physical_symptom":
        dataset = _support_dataset(lang, user_text=user_text)
        dataset_category = SUPPORT_CATEGORY_BY_CONDITION.get(subtopic)
        condition_data = dataset.get(dataset_category, {}).get(subtopic, {}) if dataset and dataset_category else {}
        if condition_data:
            override_parts = _context_follow_up_override(subtopic, user_text, support_lang)
            if override_parts:
                parts = override_parts[:3]
            else:
                parts = _context_follow_up_parts(
                    condition_data,
                    follow_up_kind,
                    session_store=session_store,
                    previous_response=previous_bot,
                    previous_bot=previous_bot,
                )
            if parts:
                return {
                    "style": "context_follow_up",
                    "blueprint": "follow_up_continuation",
                    "mode": "medium",
                    "structure": ["follow_up_context"],
                    "kind": "physical_follow_up",
                    "category": category,
                    "subtopic": subtopic,
                    "parts": parts,
                    "response_source": "context_follow_up",
                }

    if category == "mental_emotional":
        parts = _build_mental_health_response(
            lang,
            subtopic=subtopic or "general",
            user_text=user_text,
            session_store=session_store,
        )
        if parts:
            return {
                "style": "context_follow_up",
                "blueprint": "mental_follow_up",
                "mode": "medium",
                "structure": ["follow_up_context"],
                "kind": "mental_follow_up",
                "category": category,
                "subtopic": subtopic,
                "parts": parts[:3],
                "response_source": "context_follow_up",
            }

    return None


def _should_include_medication(condition, category, intent, text, entities, support_lang):
    if category in MILD_MEDICATION_CATEGORIES:
        return True, f"category:{category}"
    if condition in MILD_MEDICATION_CONDITIONS:
        return True, f"condition:{condition}"
    if intent == "solution_request" and entities.get("medicine"):
        return True, "user_mentioned_medicine"
    if support_lang == "hinglish" and _contains_any(text, ["medicine", "medication", "tablet", "dawai", "dawa"]):
        return True, "user_requested_medication"
    if support_lang == "en" and _contains_any(text, ["medicine", "medication", "tablet", "pain relief", "otc"]):
        return True, "user_requested_medication"
    return False, "safety_filtered"


def _should_include_warning(condition, category, severe, emergency, detected):
    if emergency:
        return True, "emergency_signal"
    if severe:
        return True, "severity_signal"
    if detected and detected.get("kind") == "disease":
        return True, "disease_condition"
    if category == "disease_related":
        return True, "disease_category"
    return False, "not_needed"


def _support_length_mode(intent, sentiment, session_store, topic, user_text, severe=False, emergency=False):
    history = session_store.get(CHAT_HISTORY_KEY, []) if hasattr(session_store, "get") else []
    repeated_topic = sum(
        1 for item in history[-6:]
        if topic and isinstance(item, dict) and item.get("topic") == topic
    )
    word_count = len((user_text or "").split())
    if emergency:
        return "short"
    if severe or sentiment == "very_negative":
        return random.choice(["short", "medium"])
    if intent == "solution_request" or word_count >= 14:
        return random.choice(["medium", "long"])
    if repeated_topic < 2 and word_count >= 6:
        return random.choice(["medium", "long"])
    return random.choice(["short", "medium"])


def _assemble_support_parts(mode, blocks, blueprint, include_medication=False, include_warning=False, include_follow_up=False):
    order = _filter_sections_for_blueprint(
        blueprint,
        include_medication=include_medication,
        include_warning=include_warning,
        include_follow_up=include_follow_up,
    )
    if mode == "short":
        trimmed = []
        for key in order:
            if blocks.get(key):
                trimmed.append(key)
            if len(trimmed) >= 2:
                break
        if include_warning and blocks.get("warnings") and "warnings" not in trimmed:
            trimmed = [key for key in trimmed if key != "follow_ups"]
            if len(trimmed) >= 2:
                trimmed = trimmed[:1]
            trimmed.append("warnings")
        order = trimmed
    elif mode == "medium" and len(order) > 4:
        essentials = []
        for key in order:
            if blocks.get(key):
                essentials.append(key)
            if len(essentials) >= 4:
                break
        if include_warning and blocks.get("warnings") and "warnings" not in essentials:
            essentials = [key for key in essentials if key != "follow_ups"]
            essentials.append("warnings")
        order = essentials

    return [blocks[key] for key in order if blocks.get(key)], order


def _build_support_dataset_response(intent, topic, lang, repeated=False, previous_response="", sentiment="neutral", session_store=None, user_text=""):
    if intent not in {"symptom_report", "solution_request", "emotional_support", "general_query"}:
        return None

    detected = detect_health_subtopic(user_text, lang)
    entities = extract_context_entities(user_text, lang)
    condition, support_lang, alias_scores = _detect_support_condition(user_text, lang, topic, detected, entities)
    dataset = _support_dataset(lang, user_text=user_text)
    category = SUPPORT_CATEGORY_BY_CONDITION.get(condition)
    condition_data = dataset.get(category, {}).get(condition, {}) if dataset and category and condition else {}
    if not condition_data:
        return None

    severe = _has_severe_symptom_signal(user_text, lang)
    emergency = _has_emergency_signal(user_text, support_lang)
    mode = _support_length_mode(
        intent=intent,
        sentiment=sentiment,
        session_store=session_store or {},
        topic=topic,
        user_text=user_text,
        severe=severe,
        emergency=emergency,
    )
    include_medication, medication_reason = _should_include_medication(
        condition=condition,
        category=category,
        intent=intent,
        text=user_text,
        entities=entities,
        support_lang=support_lang,
    )
    include_warning, warning_reason = _should_include_warning(
        condition=condition,
        category=category,
        severe=severe,
        emergency=emergency,
        detected=detected,
    )
    style, recent_styles = _select_style(
        intent=intent,
        sentiment=sentiment,
        topic=topic,
        condition=condition,
        category=category,
        support_lang=support_lang,
        user_text=user_text,
        session_store=session_store,
    )
    memory = _response_memory(session_store)
    recent_phrases = set(_memory_list(memory, "recent_phrases")[-RECENT_PHRASE_LIMIT:])
    include_follow_up = mode != "short" and _supports_follow_up(
        style=style,
        blueprint="supportive_full",
        include_warning=include_warning,
    )
    blueprint, recent_blueprints, recent_structures = _select_blueprint(
        style=style,
        mode=mode,
        include_medication=include_medication,
        include_warning=include_warning,
        include_follow_up=include_follow_up,
        session_store=session_store,
    )
    include_follow_up = include_follow_up and "follow_ups" in SUPPORT_BLUEPRINTS.get(blueprint, [])

    selected = {}
    used_lines = set()
    for key in ["friendly_response", "symptom_explanation", "solutions", "medications", "warnings", "follow_ups"]:
        choice = _choose_support_line(
            condition_data.get(key, []),
            session_store=session_store,
            previous_response=previous_response,
            exclude_lines=used_lines,
            blocked_phrases=recent_phrases,
        )
        selected[key] = choice
        if choice:
            used_lines.add(choice)

    transition = _style_transition(style, support_lang, recent_phrases=recent_phrases)
    if transition:
        if blueprint == "question_first" and selected.get("follow_ups"):
            selected["follow_ups"] = _append_unique(transition.strip(), selected["follow_ups"])
        elif selected.get("friendly_response"):
            selected["friendly_response"] = f"{transition}{selected['friendly_response']}".strip()
        elif selected.get("solutions"):
            selected["solutions"] = f"{transition}{selected['solutions']}".strip()

    context_line = _entity_context_line(entities, support_lang)
    if context_line and style in {"analytical", "reassuring", "direct", "casual"}:
        selected["symptom_explanation"] = _append_unique(selected.get("symptom_explanation", ""), context_line)

    if include_warning and emergency:
        urgent_fallbacks = _symptom_language_data(lang).get("urgent_fallbacks", [])
        urgent_note = _choose_support_line(
            urgent_fallbacks,
            session_store=session_store,
            previous_response=previous_response,
            exclude_lines=used_lines,
            blocked_phrases=recent_phrases,
        )
        selected["warnings"] = _append_unique(selected.get("warnings", ""), urgent_note)

    parts, structure_order = _assemble_support_parts(
        mode=mode,
        blocks=selected,
        blueprint=blueprint,
        include_warning=include_warning,
        include_medication=include_medication,
        include_follow_up=include_follow_up,
    )

    if not parts:
        return None

    if style == "short" and parts and len(parts) > 1 and random.random() < 0.4:
        parts = parts[:1]
    elif style == "questioning" and selected.get("follow_ups") and selected["follow_ups"] not in parts:
        parts = [selected["follow_ups"]] + parts[:2]
    elif style == "supportive_friend" and selected.get("friendly_response") and selected["friendly_response"] not in parts[:1]:
        parts = [selected["friendly_response"]] + [part for part in parts if part != selected["friendly_response"]]

    if intent == "solution_request":
        if selected.get("solutions") and selected["solutions"] not in parts:
            parts.insert(0, selected["solutions"])
        if include_medication and selected.get("medications") and selected["medications"] not in parts:
            parts.append(selected["medications"])
        if include_warning and selected.get("warnings") and selected["warnings"] not in parts:
            parts.append(selected["warnings"])

    reasoning = _context_reasoning(entities)
    skipped_sections = [
        key for key in ["friendly_response", "symptom_explanation", "solutions", "medications", "warnings", "follow_ups"]
        if key not in structure_order
    ]
    LOGGER.info(
        "[RuleResponder] Support dataset condition=%s category=%s detected=%s aliases=%s entities=%s severity=%s emergency=%s mode=%s style=%s blueprint=%s medication=%s(%s) warning=%s(%s) skipped=%s blocked_phrases=%s recent_styles=%s blocks=%s",
        condition,
        category,
        detected,
        alias_scores,
        entities,
        severe,
        emergency,
        mode,
        style,
        blueprint,
        include_medication,
        medication_reason,
        include_warning,
        warning_reason,
        skipped_sections,
        sorted(recent_phrases),
        recent_styles,
        {key: bool(value) for key, value in selected.items()},
    )
    return {
        "kind": detected.get("kind") if detected else ("emotional" if category == "mental_emotional" else "support"),
        "subtopic": condition,
        "category": category,
        "entities": entities,
        "reasoning": reasoning,
        "mode": mode,
        "style": style,
        "blueprint": blueprint,
        "parts": parts,
        "selected_blocks": selected,
        "medication_reason": medication_reason,
        "warning_reason": warning_reason,
        "skipped_sections": skipped_sections,
        "structure_order": structure_order,
    }


def extract_context_entities(text, lang):
    symptom_data = _symptom_language_data(lang)
    entity_maps = symptom_data.get("context_entities", {})
    entities = {}
    for entity_type, item_map in entity_maps.items():
        matches = []
        for canonical_name, keywords in item_map.items():
            if any(_contains_keyword(text, keyword) for keyword in keywords):
                matches.append(canonical_name)
        if matches:
            entities[entity_type] = matches
    return entities


def _context_reasoning(entities):
    parts = []
    symptoms = entities.get("symptom", [])
    causes = entities.get("cause", [])
    supplements = entities.get("supplement", [])
    medicines = entities.get("medicine", [])
    severity = entities.get("severity", [])
    duration = entities.get("duration", [])
    emotional_context = entities.get("emotional_context", [])

    if symptoms and (causes or supplements):
        parts.append("symptom_with_context")
    if medicines:
        parts.append("medicine_context")
    if severity:
        parts.append("severity_context")
    if duration:
        parts.append("duration_context")
    if emotional_context:
        parts.append("emotional_context")
    return ",".join(parts) if parts else "symptom_only"


def _build_contextual_symptom_line(entities, lang):
    symptoms = entities.get("symptom", [])
    causes = entities.get("cause", [])
    supplements = entities.get("supplement", [])
    medicines = entities.get("medicine", [])
    severity = entities.get("severity", [])
    duration = entities.get("duration", [])
    if lang != "en":
        return ""

    symptom_label = symptoms[0].replace("_", " ") if symptoms else "symptoms"
    cause_label = causes[0].replace("_", " ") if causes else ""
    supplement_label = supplements[0].replace("_", " ") if supplements else ""
    medicine_label = medicines[0].replace("_", " ") if medicines else ""
    severity_label = severity[0].replace("_", " ") if severity else ""
    duration_label = duration[0].replace("_", " ") if duration else ""

    if symptom_label == "headache" and cause_label == "dehydration" and supplement_label:
        return (
            f"Headaches can sometimes happen when dehydration combines with supplements like {supplement_label}, "
            "especially if water intake has been low."
        )
    if cause_label and supplement_label:
        return (
            f"The {symptom_label} could be getting pushed by both {cause_label} and {supplement_label}, "
            "so hydration, rest, and easing off the trigger for now may help."
        )
    if cause_label:
        line = f"{symptom_label.capitalize()} can sometimes be made worse by {cause_label}."
        if duration_label:
            line += f" Since this has been going on {duration_label.replace('_', ' ')}, it is worth watching whether it is easing."
        return line
    if supplement_label:
        return (
            f"Sometimes {symptom_label} shows up around supplements like {supplement_label}, especially if sleep, hydration, or dosing has been off."
        )
    if medicine_label:
        return f"It is useful to notice whether the {symptom_label} changed before or after taking {medicine_label}."
    if severity_label or duration_label:
        details = " and ".join(item.replace("_", " ") for item in [severity_label, duration_label] if item)
        return f"The fact that this feels {details} makes it worth taking a little more seriously."
    return ""


def _match_best_subtopic(text, keyword_map):
    if not text or not keyword_map:
        return None
    normalized_text = _normalize_text(text)
    scores = {}
    for subtopic, keywords in keyword_map.items():
        match_count = sum(1 for keyword in keywords if _contains_keyword(normalized_text, keyword))
        if match_count:
            scores[subtopic] = match_count
    if not scores:
        return None
    return max(scores, key=scores.get)


def detect_health_subtopic(text, lang):
    symptom_data = _symptom_language_data(lang)
    disease_subtopic = _match_best_subtopic(text, symptom_data.get("disease_keyword_map", {}))
    if disease_subtopic:
        return {"kind": "disease", "name": disease_subtopic}
    symptom_subtopic = _match_best_subtopic(text, symptom_data.get("keyword_map", {}))
    if symptom_subtopic:
        return {"kind": "symptom", "name": symptom_subtopic}
    return None


def _has_severe_symptom_signal(text, lang):
    symptom_data = _symptom_language_data(lang)
    severe_keywords = symptom_data.get("severe_keywords", [])
    return any(_contains_keyword(text, keyword) for keyword in severe_keywords)


def _build_symptom_response(intent, lang, repeated, previous_response, session_store, user_text):
    if intent not in {"symptom_report", "solution_request", "general_query"}:
        return None

    detected = detect_health_subtopic(user_text, lang)
    if not detected:
        return None
    subtopic = detected["name"]
    symptom_data = _symptom_language_data(lang)
    subtopic_data = symptom_data.get("subtopics", {}).get(subtopic, {})
    responses = subtopic_data.get("responses", [])
    if not responses:
        return None

    entities = extract_context_entities(user_text, lang)
    severe = _has_severe_symptom_signal(user_text, lang)
    language_data = RULE_RESPONSE_DATA.get(lang, RULE_RESPONSE_DATA["en"])
    intent_data = language_data.get(intent) or language_data.get("symptom_report") or {}
    opener_pool = (
        intent_data.get("repeat_openers")
        if repeated and intent_data.get("repeat_openers")
        else intent_data.get("openers", [])
    )
    opener = _choose(opener_pool or intent_data.get("openers", []) or [])
    middle = _choose(responses, exclude=previous_response)
    context_line = _build_contextual_symptom_line(entities, lang)
    if context_line:
        middle = f"{middle}\n\n{context_line}"

    base_closer = _choose(subtopic_data.get("closers", []) or intent_data.get("closers", []))
    if severe:
        urgent_note = _choose(symptom_data.get("urgent_fallbacks", []))
        closer = " ".join(part for part in [base_closer, urgent_note] if part)
    else:
        closer = base_closer or _choose(intent_data.get("closers", []))

    return {
        "kind": detected["kind"],
        "subtopic": subtopic,
        "entities": entities,
        "reasoning": _context_reasoning(entities),
        "opener": opener,
        "middle": middle,
        "closer": closer,
    }


def _length_mode(intent, sentiment, session_store, topic):
    history = session_store.get(CHAT_HISTORY_KEY, []) if hasattr(session_store, "get") else []
    repeated_topic = sum(
        1 for item in history[-6:]
        if topic and isinstance(item, dict) and item.get("topic") == topic
    )
    if intent == "emergency" or sentiment == "very_negative":
        return "short"
    if intent in {"general_query", "solution_request"} and repeated_topic < 2:
        return random.choice(["medium", "long"])
    return random.choice(["short", "medium"])


def _sentiment_prefix(lang, sentiment, recent_prefixes):
    banks = {
        "en": {
            "very_negative": ["I'm really concerned about you.", "I'm here with you.", "This feels really heavy."],
            "negative": ["I hear you.", "I'm with you.", "That sounds tough."],
            "positive": ["That's encouraging.", "I'm glad to hear that.", "That sounds like a positive shift."],
        },
        "hi": {
            "very_negative": ["Mujhe aapki chinta ho rahi hai.", "Main aapke saath hoon.", "Ye bahut heavy lag raha hai."],
            "negative": ["Main sun raha hoon.", "Main aapke saath hoon.", "Ye mushkil lag raha hai."],
            "positive": ["Ye achhi baat hai.", "Ye hopeful lag raha hai.", "Achha hai ki aapne share kiya."],
        },
        "hinglish": {
            "very_negative": ["Mujhe tumhari concern ho rahi hai.", "Main tumhare saath hoon.", "Ye kaafi heavy lag raha hai."],
            "negative": ["Main sun raha hoon.", "Main tumhare saath hoon.", "Ye tough lag raha hai."],
            "positive": ["Ye achhi sign hai.", "Good to hear that.", "Ye thoda encouraging lag raha hai."],
        },
    }
    choices = banks.get(lang, banks["en"]).get(sentiment, [])
    recent_fingerprints = {_text_fingerprint(item) for item in recent_prefixes if item}
    filtered = [item for item in choices if _text_fingerprint(item) not in recent_fingerprints]
    return _choose(filtered or choices, exclude=recent_prefixes[-1] if recent_prefixes else None)


def _pick_follow_up(intent_data, previous_response="", session_store=None):
    follow_ups = intent_data.get("follow_ups") or []
    if not follow_ups or random.random() >= FOLLOW_UP_PROBABILITY:
        return ""
    previous_tail = previous_response.split("\n\n")[-1] if previous_response else ""
    history = session_store.get(CHAT_HISTORY_KEY, []) if session_store else []
    recent_bot_lines = "\n".join(item.get("bot", "") for item in history[-4:] if isinstance(item, dict))
    candidates = [item for item in follow_ups if item and item != previous_tail and item not in recent_bot_lines]
    return random.choice(candidates) if candidates else _choose(follow_ups, exclude=previous_tail)


def _response_phrase_fingerprints(response):
    parts = [part.strip() for part in (response or "").split("\n\n") if part.strip()]
    fingerprints = []
    for part in parts:
        fingerprint = _text_fingerprint(part)
        if fingerprint:
            fingerprints.append(fingerprint)
    return fingerprints


def _build_response(intent, topic, lang, repeated=False, previous_response="", sentiment="neutral", session_store=None, user_text=""):
    route = _classify_response_route(intent, topic, lang, user_text=user_text)
    LOGGER.info(
        "[RuleResponder] route_decision category=%s subtopic=%s confidence=%.2f dataset_match=%s fallback_reason=%s intent=%s topic=%s",
        route.get("category"),
        route.get("subtopic"),
        route.get("confidence", 0.0),
        route.get("dataset_match", "none"),
        route.get("fallback_reason", "") or "none",
        intent,
        topic,
    )

    context_follow_up = _build_context_follow_up_response(
        intent=intent,
        topic=topic,
        lang=lang,
        session_store=session_store,
        user_text=user_text,
    )
    if context_follow_up:
        response_text = "\n\n".join(part for part in context_follow_up.get("parts", []) if part)
        LOGGER.info(
            "[RuleResponder] context_follow_up subtopic=%s category=%s source=%s text=%s",
            context_follow_up.get("subtopic"),
            context_follow_up.get("category"),
            context_follow_up.get("response_source"),
            _compact_text(response_text),
        )
        return response_text, "", {
            "style": context_follow_up.get("style", "context_follow_up"),
            "blueprint": context_follow_up.get("blueprint", "follow_up_continuation"),
            "mode": context_follow_up.get("mode", "medium"),
            "structure": context_follow_up.get("structure", ["follow_up_context"]),
            "kind": context_follow_up.get("kind", "follow_up"),
            "category": context_follow_up.get("category"),
            "subtopic": context_follow_up.get("subtopic"),
            "route_confidence": 0.99,
            "dataset_match": context_follow_up.get("subtopic"),
            "fallback_reason": "",
        }

    if route.get("category") == "positive_emotion":
        parts = _build_positive_response(lang, user_text=user_text, session_store=session_store)
        response_text = "\n\n".join(part for part in parts if part) or friendly_fallback_message(lang, user_text=user_text)
        return response_text, "", {
            "style": "warm_positive",
            "blueprint": "positive_support",
            "mode": "medium",
            "structure": ["validation", "reinforcement", "suggestions", "follow_up"],
            "kind": "positive",
            "category": route.get("category"),
            "subtopic": route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    if route.get("category") == "mental_emotional":
        parts = _build_mental_health_response(
            lang,
            subtopic=route.get("subtopic") or "general",
            user_text=user_text,
            session_store=session_store,
        )
        response_text = "\n\n".join(part for part in parts if part) or friendly_fallback_message(lang, user_text=user_text)
        return response_text, "", {
            "style": "empathetic_mental_health",
            "blueprint": "mental_health_support",
            "mode": "medium",
            "structure": ["validation", "effects", "suggestions", "follow_up"],
            "kind": "mental_health",
            "category": route.get("category"),
            "subtopic": route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    if route.get("category") == "ai_fallback":
        response_text = friendly_fallback_message(lang, user_text=user_text)
        return response_text, "", {
            "style": "friendly_fallback",
            "blueprint": "safe_fallback",
            "mode": "short",
            "structure": ["fallback"],
            "kind": "fallback",
            "category": route.get("category"),
            "subtopic": route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    language_data = RULE_RESPONSE_DATA.get(lang, RULE_RESPONSE_DATA["en"])
    intent_data = language_data.get(intent) or language_data.get("general_query") or {}
    topic_value = _topic_label(lang, topic)

    casual_payload = _build_casual_response(
        intent=intent,
        topic=topic,
        lang=lang,
        sentiment=sentiment,
        session_store=session_store,
        user_text=user_text,
    )
    if casual_payload:
        response_text = "\n\n".join(part for part in casual_payload.get("parts", []) if part)
        LOGGER.info(
            "[RuleResponder] Final assembled casual response kind=%s text=%s",
            casual_payload.get("subtopic"),
            _compact_text(response_text),
        )
        return response_text, "", {
            "style": casual_payload.get("style", "casual"),
            "blueprint": casual_payload.get("blueprint", "minimal_support"),
            "mode": casual_payload.get("mode", "short"),
            "structure": ["casual"] + (["follow_up"] if len(casual_payload.get("parts", [])) > 1 else []),
            "kind": "casual",
            "category": route.get("category"),
            "subtopic": route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    support_payload = _build_support_dataset_response(
        intent=intent,
        topic=topic,
        lang=lang,
        repeated=repeated,
        previous_response=previous_response,
        sentiment=sentiment,
        session_store=session_store,
        user_text=user_text,
    )

    symptom_payload = None
    if not support_payload and topic == "physical_discomfort":
        symptom_payload = _build_symptom_response(
            intent=intent,
            lang=lang,
            repeated=repeated,
            previous_response=previous_response,
            session_store=session_store,
            user_text=user_text,
        )

    if route.get("category") == "physical_symptom" and not support_payload and not symptom_payload:
        parts = _build_generic_physical_response(lang, user_text=user_text)
        response_text = "\n\n".join(part for part in parts if part)
        return response_text, "", {
            "style": "grounded_physical",
            "blueprint": "generic_physical_support",
            "mode": "medium",
            "structure": ["validation", "causes", "care", "medication", "warning", "follow_up"],
            "kind": "physical",
            "category": route.get("category"),
            "subtopic": route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    if support_payload:
        parts = support_payload.get("parts", [])
        response_text = "\n\n".join(part for part in parts if part)
        LOGGER.info(
            "[RuleResponder] Final assembled support response condition=%s category=%s mode=%s style=%s blueprint=%s text=%s",
            support_payload.get("subtopic"),
            support_payload.get("category"),
            support_payload.get("mode"),
            support_payload.get("style"),
            support_payload.get("blueprint"),
            _compact_text(response_text),
        )
        return response_text, "", {
            "style": support_payload.get("style", "support"),
            "blueprint": support_payload.get("blueprint", "supportive_full"),
            "mode": support_payload.get("mode", "medium"),
            "structure": support_payload.get("structure_order", []),
            "kind": support_payload.get("kind", "support"),
            "category": route.get("category"),
            "subtopic": support_payload.get("subtopic") or route.get("subtopic"),
            "route_confidence": route.get("confidence"),
            "dataset_match": support_payload.get("subtopic") or route.get("dataset_match"),
            "fallback_reason": route.get("fallback_reason"),
        }

    if symptom_payload:
        LOGGER.info(
            "[RuleResponder] Using %s-specific response for subtopic=%s entities=%s reasoning=%s",
            symptom_payload.get("kind", "symptom"),
            symptom_payload.get("subtopic", "unknown"),
            symptom_payload.get("entities", {}),
            symptom_payload.get("reasoning", "symptom_only"),
        )
        opener = symptom_payload.get("opener", "")
        middle = symptom_payload.get("middle", "")
        closer = symptom_payload.get("closer", "")
        structure_options = [
            [opener, middle, closer],
            [middle, closer],
        ]
    else:
        opener_pool = (
            intent_data.get("repeat_openers")
            if repeated and intent_data.get("repeat_openers")
            else intent_data.get("openers", [])
        )
        opener = _choose(opener_pool or intent_data.get("openers", []) or [])
        template = _choose(intent_data.get("templates", []) or [])
        closer = _choose(intent_data.get("closers", []) or [])
        middle = template.format(topic=topic_value) if template else ""
        structure_options = [
            [opener, middle, closer],
            [middle, closer],
            [opener, middle],
            [middle],
        ]

    if not any([opener, middle, closer]) and intent != "general_query":
        general_data = language_data.get("general_query") or {}
        opener = _choose(general_data.get("openers", []) or [])
        template = _choose(general_data.get("templates", []) or [])
        closer = _choose(general_data.get("closers", []) or [])
        middle = template.format(topic=topic_value) if template else ""
        structure_options = [
            [opener, middle, closer],
            [middle, closer],
            [opener, middle],
            [middle],
        ]

    memory = (session_store or {}).get(RULE_MEMORY_KEY, {}) if session_store else {}
    recent_prefixes = memory.get("recent_prefixes", []) or []
    tone_prefix = _sentiment_prefix(lang, sentiment, recent_prefixes)
    if tone_prefix:
        if opener:
            opener = f"{tone_prefix} {opener}"
        elif middle:
            middle = f"{tone_prefix} {middle}"
        elif closer:
            closer = f"{tone_prefix} {closer}"
        else:
            opener = tone_prefix

    valid_structures = [[part for part in option if part] for option in structure_options if any(option)]
    memory = (session_store or {}).get(RULE_MEMORY_KEY, {}) if session_store else {}
    recent_structures = _memory_list(memory, "recent_structures")
    filtered_structures = []
    for option in valid_structures:
        labels = []
        if opener and opener in option:
            labels.append("opener")
        if middle and middle in option:
            labels.append("middle")
        if closer and closer in option:
            labels.append("closer")
        structure_key = _structure_signature(labels)
        if structure_key not in recent_structures[-2:]:
            filtered_structures.append(option)
    parts = random.choice(filtered_structures or valid_structures) if valid_structures else [part for part in [opener, middle, closer] if part]

    mode = _length_mode(intent, sentiment, session_store or {}, topic)
    if mode == "short" and len(parts) > 2:
        parts = parts[:2]
    elif mode == "long" and closer and closer not in parts:
        parts.append(closer)

    follow_up = _pick_follow_up(intent_data, previous_response=previous_response, session_store=session_store)
    if follow_up and mode != "short" and random.random() < 0.65:
        parts.append(follow_up)

    if not parts:
        parts = [topic_value]

    response_text = "\n\n".join(part for part in parts if part)
    structure = []
    if opener and opener in parts:
        structure.append("opener")
    if middle and middle in parts:
        structure.append("middle")
    if closer and closer in parts:
        structure.append("closer")
    if follow_up and follow_up in parts:
        structure.append("follow_up")
    LOGGER.info(
        "[RuleResponder] Final assembled legacy response intent=%s topic=%s mode=%s text=%s",
        intent,
        topic,
        mode,
        _compact_text(response_text),
    )
    return response_text, tone_prefix, {
        "style": "legacy",
        "blueprint": "legacy_random",
        "mode": mode,
        "structure": structure,
        "kind": "legacy",
        "category": route.get("category"),
        "subtopic": route.get("subtopic"),
        "route_confidence": route.get("confidence"),
        "dataset_match": route.get("dataset_match"),
        "fallback_reason": route.get("fallback_reason"),
    }


def generate_response(intent, topic, sentiment, session, text=""):
    memory = session.get(RULE_MEMORY_KEY, {})
    if not isinstance(memory, dict):
        memory = {}
    last_intent = memory.get("last_intent")
    repeated = last_intent == intent
    last_responses = memory.get("last_responses", []) or []
    if not isinstance(last_responses, list):
        last_responses = []
    last_responses = [item for item in last_responses[-5:] if isinstance(item, str) and item.strip()]
    previous_response = last_responses[-1] if last_responses else ""
    lang = _resolve_language(session)

    attempts = 0
    response, tone_prefix, response_meta = _build_response(
        intent=intent,
        topic=topic,
        lang=lang,
        repeated=repeated,
        previous_response=previous_response,
        sentiment=sentiment,
        session_store=session,
        user_text=text,
    )
    while last_responses and response in last_responses and attempts < 12:
        response, tone_prefix, response_meta = _build_response(
            intent=intent,
            topic=topic,
            lang=lang,
            repeated=repeated,
            previous_response=previous_response,
            sentiment=sentiment,
            session_store=session,
            user_text=text,
        )
        attempts += 1

    recent_prefixes = memory.get("recent_prefixes", []) or []
    if not isinstance(recent_prefixes, list):
        recent_prefixes = []
    recent_prefixes = recent_prefixes + ([tone_prefix] if tone_prefix else [])
    last_responses = [_compact_text(item) for item in (last_responses + [response])[-5:]]
    recent_styles = _memory_list(memory, "recent_styles") + [response_meta.get("style", "legacy")]
    recent_blueprints = _memory_list(memory, "recent_blueprints") + [response_meta.get("blueprint", "legacy_random")]
    recent_structures = _memory_list(memory, "recent_structures") + [_structure_signature(response_meta.get("structure", []))]
    recent_phrases = _memory_list(memory, "recent_phrases") + _response_phrase_fingerprints(response)

    session[RULE_MEMORY_KEY] = {
        "last_intent": intent,
        "last_response": _compact_text(response),
        "last_responses": last_responses,
        "last_sentiment": sentiment,
        "last_language": lang,
        "last_symptom_text": _compact_text(text),
        "last_category": response_meta.get("category"),
        "last_subtopic": response_meta.get("subtopic"),
        "recent_prefixes": [item for item in recent_prefixes[-4:] if item],
        "recent_styles": [item for item in recent_styles[-RECENT_STYLE_LIMIT:] if item],
        "recent_blueprints": [item for item in recent_blueprints[-RECENT_BLUEPRINT_LIMIT:] if item],
        "recent_structures": [item for item in recent_structures[-RECENT_STRUCTURE_LIMIT:] if item],
        "recent_phrases": [item for item in recent_phrases[-RECENT_PHRASE_LIMIT:] if item],
    }
    session.modified = True
    return response
