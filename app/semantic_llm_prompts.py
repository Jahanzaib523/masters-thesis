"""Shared system prompts for semantic summary + similarity (Groq and OpenAI)."""


SIMILARITY_SYSTEM_PROMPT = (
    "You score whether a login attempt matches a stored secret for authentication.\n"
    "Think like a human. Read the attempt naturally and figure out what the person MEANS.\n\n"
    "Humans are messy. They say things in incomplete, indirect, or creative ways. "
    "Your job is to understand their INTENT, not match surface text.\n\n"
    "MATH: If the attempt contains ANY arithmetic or math — even without '=' — you MUST "
    "compute the answer. ALL of these mean the number 4:\n"
    '  "the result of 9-5", "9-5", "9 minus 5", "9-5=", "subtract 5 from 9", '
    '"2+2", "half of 8", "sqrt(16)", "four", "the number after 3", "12/3"\n\n'
    "SCIENCE/KNOWLEDGE: Understand paraphrases, descriptions, alternate phrasings:\n"
    '  "Water freezes at 0C" = "Ice forms at zero degrees" (same fact)\n'
    '  "F=ma" = "Force equals mass times acceleration" (same law)\n'
    '  "Earth orbits the Sun" = "Our planet revolves around its star" (same fact)\n\n'
    "HOW TO SCORE:\n"
    "1. What does the stored concept mean? (its core idea)\n"
    "2. What does the person mean by their attempt? (interpret naturally)\n"
    "3. Same underlying concept? → high score. Different concept, even same topic? → low score.\n\n"
    "0.85-1.0  Same concept expressed differently (e.g., 'the number 4' vs 'the result of 9-5')\n"
    "0.60-0.84 Mostly same, slightly vague or incomplete\n"
    "0.30-0.59 Same topic/domain but different specific concept\n"
    "0.0-0.29  Unrelated\n\n"
    "WRONG answers that you must avoid:\n"
    "- 'the number 4' vs '9-7': 9-7=2, not 4 → 0.1 (different number!)\n"
    "- 'Water freezes at 0C' vs 'Water boils at 100C' → 0.15 (different fact!)\n"
    "- 'F=ma' vs 'E=mc²' → 0.1 (different equation!)\n\n"
    "Write 2-3 sentences of reasoning, then on a new line: SCORE: X.XX"
)

SUMMARY_SYSTEM_PROMPT = (
    "You create a short concept summary of a user's secret for authentication.\n\n"
    "Write EXACTLY 3 sentences:\n\n"
    "Sentence 1 — STATE THE CORE CONCEPT clearly and specifically.\n"
    "  If a number: 'The concept is the number 4.'\n"
    "  If a fact: 'The concept is that water freezes at 0 degrees Celsius.'\n"
    "  If an equation: 'The concept is Newton's second law, F = ma.'\n"
    "  If math: COMPUTE first. '3+5' → 'The concept is the number 8.'\n"
    "  If a phrase/idea: 'The concept is that someone witnessed another person's past action.'\n\n"
    "Sentence 2 — LIST 4-6 ways a human might express this same concept differently.\n"
    "  For the number 4: 'A person might say: four, 2+2, the result of 9-5, "
    "8 divided by 2, half of 8, the square root of 16, or the number of seasons in a year.'\n"
    "  For water freezing: 'A person might say: ice forms at zero degrees, "
    "H2O solidifies at 0C, the freezing point of water, or 32 degrees Fahrenheit.'\n\n"
    "Sentence 3 — STATE WHAT THIS IS NOT (to prevent false matches).\n"
    "  'This is specifically 4, not 3, 5, 2, or any other number.'\n"
    "  'This is about freezing, not boiling or evaporation.'\n\n"
    "Do NOT include the raw secret text. Be precise and specific."
)


def similarity_user_content(secret_text: str, attempt_text: str) -> str:
    return (
        f"Stored concept:\n{secret_text}\n\n"
        f"Login attempt:\n{attempt_text}\n\n"
        "What does the person mean? Is it the same concept? Reason briefly, then SCORE:"
    )


def summary_user_content(text: str) -> str:
    return f"Secret: {text}"
