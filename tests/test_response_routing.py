import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LEGACY_CHAT_DB_ENABLED"] = "false"

from app import detect_priority_route, detect_topic, resolve_turn_analysis
from rule_responder import RULE_LANGUAGE_KEY, generate_response
from services.ai_handler import update_session_chat_history


class FakeSession(dict):
    def __init__(self):
        super().__init__()
        self.modified = False


def build_reply(message):
    lang = "en"
    topic = detect_topic(message, lang)
    route = detect_priority_route(message, lang, {"matched": False, "matched_keywords": [], "intent": "general_query"})
    session = FakeSession()
    session[RULE_LANGUAGE_KEY] = lang
    response = generate_response(route["intent"], topic, "neutral", session, text=message)
    return route, response


def run_turn(session, message):
    lang = "en"
    session[RULE_LANGUAGE_KEY] = lang
    analysis = resolve_turn_analysis(message, lang, session)
    response = generate_response(
        analysis["resolved_intent"],
        analysis["topic"],
        analysis["sentiment"],
        session,
        text=message,
    )
    meta = {
        "intent": analysis["resolved_intent"],
        "sentiment": analysis["sentiment"],
        "topic": analysis["topic"],
        "category": analysis["detected_category"],
        "subtopic": analysis["route_subtopic"],
        "entities": analysis["extracted_entities"],
    }
    update_session_chat_history(session, message, response, meta)
    return analysis, response


class ResponseRoutingTests(unittest.TestCase):
    def test_vague_symptom_gets_clarifying_question(self):
        session = FakeSession()
        analysis, response = run_turn(session, "I feel sick")
        lowered = response.lower()
        self.assertEqual(analysis["detected_category"], "physical_symptom")
        self.assertTrue("what symptoms" in lowered or "do you have fever" in lowered or "since when" in lowered)
        self.assertNotIn("i did not get enough signal", lowered)

    def test_mental_health_routes_and_language(self):
        for message in ["I have depression", "I feel lonely", "I feel emotionally exhausted"]:
            route, response = build_reply(message)
            lowered = response.lower()
            self.assertEqual(route["category"], "mental_emotional")
            self.assertTrue(response.strip())
            self.assertNotIn("monitor the symptom", lowered)
            self.assertNotIn("track when it began", lowered)
            self.assertNotIn("observe the condition", lowered)

    def test_positive_emotions_route_cleanly(self):
        for message in ["I am happy", "I feel excited"]:
            route, response = build_reply(message)
            lowered = response.lower()
            self.assertEqual(route["category"], "positive_emotion")
            self.assertTrue(response.strip())
            self.assertNotIn("i am having trouble responding right now", lowered)

    def test_physical_routes_stay_physical(self):
        for message in ["I have fever", "my stomach hurts"]:
            route, response = build_reply(message)
            self.assertEqual(route["category"], "physical_symptom")
            self.assertTrue(response.strip())

    def test_casual_routes_stay_casual(self):
        for message in ["hello", "how are you"]:
            route, response = build_reply(message)
            self.assertEqual(route["category"], "casual_conversation")
            self.assertTrue(response.strip())

    def test_crisis_routes_first(self):
        route, response = build_reply("I want to die")
        self.assertEqual(route["category"], "crisis")
        self.assertEqual(route["intent"], "emergency")
        self.assertTrue(response.strip())

    def test_follow_up_continues_dehydration_context(self):
        session = FakeSession()
        first_analysis, first_response = run_turn(session, "I have dehydration")
        second_analysis, second_response = run_turn(session, "Can you elaborate urine color?")
        lowered = second_response.lower()
        self.assertEqual(first_analysis["detected_category"], "physical_symptom")
        self.assertTrue(second_analysis["follow_up_detected"])
        self.assertTrue(second_analysis["context_applied"])
        self.assertEqual(second_analysis["detected_category"], "physical_symptom")
        self.assertIn("urine", lowered)
        self.assertIn("hydr", lowered)
        self.assertNotIn("i'm here with you", lowered)
        self.assertNotEqual(first_response, second_response)

    def test_follow_up_continues_emotional_context(self):
        session = FakeSession()
        first_analysis, _ = run_turn(session, "I feel sad")
        second_analysis, second_response = run_turn(session, "why does it feel heavy sometimes?")
        lowered = second_response.lower()
        self.assertEqual(first_analysis["detected_category"], "mental_emotional")
        self.assertTrue(second_analysis["follow_up_detected"])
        self.assertTrue(second_analysis["context_applied"])
        self.assertEqual(second_analysis["resolved_intent"], "emotional_support")
        self.assertTrue("feel" in lowered or "emotional" in lowered or "heavy" in lowered)

    def test_follow_up_continues_headache_medication_context(self):
        session = FakeSession()
        first_analysis, _ = run_turn(session, "I have headache")
        second_analysis, second_response = run_turn(session, "what medicine helps?")
        lowered = second_response.lower()
        self.assertEqual(first_analysis["detected_category"], "physical_symptom")
        self.assertTrue(second_analysis["follow_up_detected"])
        self.assertTrue(second_analysis["context_applied"])
        self.assertEqual(second_analysis["resolved_intent"], "solution_request")
        self.assertTrue("paracetamol" in lowered or "ibuprofen" in lowered or "medicine" in lowered)

    def test_direct_medication_request_stays_medical(self):
        session = FakeSession()
        analysis, response = run_turn(session, "what medicine should I take for fever?")
        lowered = response.lower()
        self.assertEqual(analysis["detected_category"], "physical_symptom")
        self.assertEqual(analysis["resolved_intent"], "solution_request")
        self.assertNotIn("i'm here with you", lowered)
        self.assertTrue("paracetamol" in lowered or "ibuprofen" in lowered or "rest" in lowered or "fluids" in lowered)
        self.assertLessEqual(len([p for p in response.split(".") if p.strip()]), 4)

    def test_what_medicine_helps_fever_stays_medical(self):
        session = FakeSession()
        analysis, response = run_turn(session, "what medicine helps fever?")
        lowered = response.lower()
        self.assertEqual(analysis["detected_category"], "physical_symptom")
        self.assertIn(analysis["resolved_intent"], {"symptom_report", "solution_request"})
        self.assertNotIn("keep it light", lowered)
        self.assertNotIn("talk about something real", lowered)
        self.assertTrue("paracetamol" in lowered or "acetaminophen" in lowered or "medicine" in lowered or "fever" in lowered)

    def test_should_i_consult_doctor_answers_directly(self):
        session = FakeSession()
        _, _ = run_turn(session, "I have fever")
        analysis, response = run_turn(session, "Should I consult a doctor?")
        lowered = response.lower()
        self.assertEqual(analysis["resolved_intent"], "symptom_report")
        self.assertTrue(lowered.startswith("yes") or lowered.startswith("usually") or lowered.startswith("it depends"))
        self.assertLessEqual(len([p for p in response.split(".") if p.strip()]), 3)

    def test_concise_casual_reply(self):
        session = FakeSession()
        _, response = run_turn(session, "hi")
        self.assertLessEqual(len([p for p in response.split(".") if p.strip()]), 2)

    def test_casual_interruption_switches_out_of_dehydration(self):
        session = FakeSession()
        _, _ = run_turn(session, "I have dehydration")
        second_analysis, second_response = run_turn(session, "tell me a joke")
        lowered = second_response.lower()
        self.assertTrue(second_analysis["casual_interruption"])
        self.assertEqual(second_analysis["detected_category"], "casual_conversation")
        self.assertFalse(second_analysis["context_applied"])
        self.assertNotIn("hydration", lowered)
        self.assertNotIn("dehydration", lowered)
        self.assertNotIn("i'm here with you", lowered)
        self.assertTrue("joke" in lowered or "laugh" in lowered or "therapy" in lowered or "stress" in lowered)

    def test_resume_previous_topic_after_casual_interruption(self):
        session = FakeSession()
        _, _ = run_turn(session, "I have dehydration")
        _, _ = run_turn(session, "tell me a joke")
        third_analysis, third_response = run_turn(session, "okay back to dehydration")
        lowered = third_response.lower()
        self.assertTrue(third_analysis["resume_requested"])
        self.assertTrue(third_analysis["context_applied"])
        self.assertEqual(third_analysis["detected_category"], "physical_symptom")
        self.assertTrue("dehydr" in lowered or "fluid" in lowered or "ors" in lowered)

    def test_all_good_resets_emotional_mode(self):
        session = FakeSession()
        _, _ = run_turn(session, "I feel sad")
        second_analysis, second_response = run_turn(session, "all good")
        lowered = second_response.lower()
        self.assertTrue(second_analysis["topic_switch_detected"])
        self.assertEqual(second_analysis["message_topic"], "unrelated_topic_switch")
        self.assertFalse(second_analysis["context_applied"])
        self.assertNotIn("sad", lowered)
        self.assertNotIn("heavy", lowered)

    def test_lonely_then_hello_switches_to_casual(self):
        session = FakeSession()
        _, _ = run_turn(session, "I feel lonely")
        second_analysis, second_response = run_turn(session, "hello")
        lowered = second_response.lower()
        self.assertEqual(second_analysis["detected_category"], "casual_conversation")
        self.assertTrue(second_analysis["casual_interruption"])
        self.assertNotIn("lonely", lowered)
        self.assertNotIn("heavy", lowered)

    def test_happy_then_funny_stays_casual(self):
        session = FakeSession()
        _, _ = run_turn(session, "I am happy")
        second_analysis, second_response = run_turn(session, "tell me something funny")
        lowered = second_response.lower()
        self.assertEqual(second_analysis["detected_category"], "casual_conversation")
        self.assertTrue(second_analysis["casual_interruption"])
        self.assertNotIn("i'm here with you", lowered)
        self.assertTrue("joke" in lowered or "funny" in lowered or "stress" in lowered or "bottle" in lowered)

    def test_hello_is_normal_greeting(self):
        session = FakeSession()
        analysis, response = run_turn(session, "hi")
        lowered = response.lower()
        self.assertEqual(analysis["detected_category"], "casual_conversation")
        self.assertIn(analysis["message_topic"], {"casual_greeting", "unrelated_topic_switch"})
        self.assertNotIn("sad", lowered)
        self.assertNotIn("dehydration", lowered)

    def test_joke_reply_is_not_therapy_style(self):
        session = FakeSession()
        analysis, response = run_turn(session, "tell me a joke")
        lowered = response.lower()
        self.assertEqual(analysis["detected_category"], "casual_conversation")
        self.assertTrue("joke" in lowered or "funny" in lowered or "laugh" in lowered or "bottle" in lowered)
        self.assertNotIn("i'm here with you", lowered)

    def test_short_answer_enforcement_for_simple_medical_question(self):
        session = FakeSession()
        _, _ = run_turn(session, "I have cold")
        _, response = run_turn(session, "cold medicine?")
        self.assertLessEqual(len([p for p in response.split(".") if p.strip()]), 4)


if __name__ == "__main__":
    unittest.main()
