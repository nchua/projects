"""Extraction prompts and preprocessing for the action item harness.

Two-tier approach per spec:
    1. TRIAGE (Haiku): Quick yes/no — does this message contain action items?
    2. EXTRACTION (Sonnet): Full structured extraction of action items.

Also includes data minimization preprocessing functions.
"""

import re
import hashlib


# =============================================================================
# PRECOMPILED REGEX PATTERNS
# =============================================================================

_RE_HTML_TAGS = re.compile(r"<[^>]+>")
_RE_QUOTED_REPLY = re.compile(r"^On\s.+wrote:\s*$")
_RE_SIG_PATTERNS = [
    re.compile(r"\n--\s*\n.*", re.DOTALL | re.IGNORECASE),
    re.compile(r"\nSent from my (?:iPhone|iPad|Galaxy|Pixel).*", re.DOTALL | re.IGNORECASE),
    re.compile(r"\nGet Outlook for (?:iOS|Android).*", re.DOTALL | re.IGNORECASE),
]
_RE_FOOTER_PATTERNS = [
    re.compile(r"\n.*[Uu]nsubscribe.*", re.DOTALL),
    re.compile(r"\n.*[Yy]ou(?:'re| are) receiving this.*", re.DOTALL),
    re.compile(r"\n.*[Mm]anage (?:your )?(?:preferences|subscription).*", re.DOTALL),
    re.compile(r"\n.*[Cc]lick here to (?:unsubscribe|opt.out).*", re.DOTALL),
]
_RE_BLANK_LINES = re.compile(r"\n{3,}")


# =============================================================================
# DATA MINIMIZATION / PREPROCESSING
# =============================================================================


def strip_email_noise(raw_text: str | None) -> str:
    """Remove signatures, quoted replies, marketing footers, and HTML tags.

    This is the data minimization step — we send only the useful content
    to Claude, reducing cost and data exposure.
    """
    if not raw_text:
        return ""

    text = raw_text

    # For production, use html2text or BeautifulSoup instead of regex
    text = _RE_HTML_TAGS.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')

    lines = text.split("\n")
    cleaned_lines: list[str] = []
    in_quote = False
    for line in lines:
        stripped = line.strip()
        if _RE_QUOTED_REPLY.match(stripped):
            in_quote = True
            continue
        if stripped.startswith("-----Original Message-----"):
            in_quote = True
            continue
        if stripped.startswith("---------- Forwarded message"):
            in_quote = True
            continue
        if stripped.startswith(">"):
            continue
        if in_quote:
            if stripped == "":
                in_quote = False
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    for pattern in _RE_SIG_PATTERNS:
        text = pattern.sub("", text)

    for pattern in _RE_FOOTER_PATTERNS:
        text = pattern.sub("", text)

    text = _RE_BLANK_LINES.sub("\n\n", text)

    return text.strip()


def truncate_for_api(text: str, max_chars: int = 8000) -> str:
    """Truncate at the last whitespace before max_chars to avoid mid-word cuts."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    return truncated + "\n\n[truncated]"


def preprocess_body(raw_text: str | None, max_chars: int = 8000) -> str:
    """Strip noise and truncate in one call. Use this to avoid double-processing."""
    return truncate_for_api(strip_email_noise(raw_text), max_chars)


def hash_content(text: str) -> str:
    """SHA-256 hash of content for dedup checking."""
    return hashlib.sha256(text.encode()).hexdigest()


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

# Default user name — parameterized for backend porting
DEFAULT_USER_NAME = "Nick"

TRIAGE_SYSTEM_PROMPT_TEMPLATE = """\
You are an email/message triage assistant. Your ONLY job is to determine whether \
a message contains actionable items that the recipient ({user_name}) needs to act on.

Answer with a JSON object: {{"has_action_items": true/false, "reasoning": "one sentence"}}

Action items include:
- Direct requests to {user_name} ("Can you...", "Please...", "I need you to...")
- Commitments {user_name} made that someone is referencing ("You mentioned you'd...")
- Assignments (PR reviews, issues, tasks assigned to {user_name})
- Questions that need a response from {user_name}
- Invitations or RSVPs requiring a reply
- Deadlines directed at {user_name}

NOT action items:
- Newsletters, digests, marketing emails
- Receipts, shipping confirmations, order updates
- Automated notifications that are purely informational (build succeeded, etc.)
- FYI messages where the sender explicitly says "no action needed"
- Messages where someone else is assigned the work (unless {user_name} is also mentioned)
- General announcements (office closed, holiday reminders)
"""

EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an action item extraction assistant. Given an email or message, extract \
all actionable items that the recipient ({user_name}) needs to act on.

For each action item, return:
- title: Short imperative phrase (e.g., "Send investor deck to Sarah"). Max 80 chars.
- description: Brief context on why this matters or what's involved. 1-2 sentences.
- people: Names of people involved (the requester, collaborators, or affected parties). \
Extract just first names or identifiers.
- deadline: The deadline if one is mentioned. Use the exact phrasing from the message \
(e.g., "Friday", "by end of day Wednesday", "May 1st"). null if no deadline mentioned.
- confidence: How confident you are this is a real action item (0.0 to 1.0). \
Use 0.9+ for explicit requests, 0.7-0.9 for implicit ones, below 0.7 for ambiguous.
- priority: "high" for urgent/time-sensitive, "medium" for standard requests, \
"low" for nice-to-haves or vague asks.
- commitment_type: One of:
  - "you_committed" — {user_name} said he would do something and someone is reminding/referencing it
  - "they_requested" — Someone is asking {user_name} to do something
  - "mutual" — Both parties agreed to do something together
  - "fyi" — Informational but might require future action

Rules:
1. Only extract items that {user_name} personally needs to act on. Skip tasks assigned to others.
2. If a message lists tasks for multiple people, only extract {user_name}'s tasks.
3. Merge closely related sub-tasks into a single action item when they're part of the same deliverable.
4. For email threads, focus on the most recent message — older quoted content is context only.
5. If the sender says "no action needed" or "FYI only", do not extract action items.

Respond with a JSON object:
{{
  "action_items": [
    {{
      "title": "...",
      "description": "...",
      "people": ["..."],
      "deadline": "..." or null,
      "confidence": 0.0-1.0,
      "priority": "high|medium|low",
      "commitment_type": "you_committed|they_requested|mutual|fyi"
    }}
  ]
}}

If there are no action items, return: {{"action_items": []}}"""

_USER_TEMPLATE = """\
Source: {source}
Subject: {subject}
From: {sender}

---
{body}
---

{instruction}"""


# =============================================================================
# PUBLIC API
# =============================================================================


def get_triage_system_prompt(user_name: str = DEFAULT_USER_NAME) -> str:
    """Get the triage system prompt with the user's name."""
    return TRIAGE_SYSTEM_PROMPT_TEMPLATE.format(user_name=user_name)


def get_extraction_system_prompt(user_name: str = DEFAULT_USER_NAME) -> str:
    """Get the extraction system prompt with the user's name."""
    return EXTRACTION_SYSTEM_PROMPT_TEMPLATE.format(user_name=user_name)


# Pre-formatted with default user name for the harness
TRIAGE_SYSTEM_PROMPT = get_triage_system_prompt()
EXTRACTION_SYSTEM_PROMPT = get_extraction_system_prompt()


def _format_user_prompt(
    fixture: dict,
    instruction: str,
    user_name: str = DEFAULT_USER_NAME,
    preprocessed_body: str | None = None,
) -> str:
    """Shared formatter — avoids duplicate preprocessing across triage/extraction."""
    body = preprocessed_body if preprocessed_body is not None else preprocess_body(fixture["raw_text"])
    return _USER_TEMPLATE.format(
        source=fixture["source"],
        subject=fixture["subject"],
        sender=fixture["sender"],
        body=body,
        instruction=instruction.format(user_name=user_name),
    )


def format_triage_prompt(
    fixture: dict, user_name: str = DEFAULT_USER_NAME, preprocessed_body: str | None = None
) -> str:
    """Format a test fixture into the triage user prompt."""
    return _format_user_prompt(
        fixture,
        "Does this message contain action items for {user_name}? Respond with JSON only.",
        user_name,
        preprocessed_body,
    )


def format_extraction_prompt(
    fixture: dict, user_name: str = DEFAULT_USER_NAME, preprocessed_body: str | None = None
) -> str:
    """Format a test fixture into the extraction user prompt."""
    return _format_user_prompt(
        fixture,
        "Extract all action items for {user_name} from this message. Respond with JSON only.",
        user_name,
        preprocessed_body,
    )
