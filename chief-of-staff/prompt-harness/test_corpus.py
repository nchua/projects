"""Test corpus for action item extraction prompt evaluation.

Each fixture represents a realistic email, Slack message, or GitHub notification.
Fields:
    id: unique identifier
    source: "gmail" | "github" | "slack"
    subject: email subject or message context
    sender: who sent it
    raw_text: the message body
    expected_has_action_items: whether this contains extractable action items
    expected_action_items: list of expected extractions (empty if none)
"""

FIXTURES: list[dict] = [
    # =========================================================================
    # CLEAR COMMITMENTS (you said you'd do something)
    # =========================================================================
    {
        "id": "commit_01",
        "source": "gmail",
        "subject": "Re: Q2 investor deck",
        "sender": "sarah@venture.co",
        "raw_text": (
            "Hey Nick,\n\n"
            "Great call today. As discussed, can you send over the updated "
            "investor deck by end of day Friday? We need the new ARR numbers "
            "and the product roadmap slide.\n\n"
            "Also, I'll loop in James from legal to review the terms sheet — "
            "expect an intro email from me tomorrow.\n\n"
            "Best,\nSarah"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Send updated investor deck to Sarah",
                "people": ["Sarah"],
                "deadline": "Friday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "commit_02",
        "source": "gmail",
        "subject": "Follow up: design review feedback",
        "sender": "alex@company.com",
        "raw_text": (
            "Nick,\n\n"
            "Thanks for the design review. A few things I need from you:\n\n"
            "1. Update the color palette based on our brand guidelines\n"
            "2. Share the Figma link with the engineering team\n"
            "3. Write up a brief summary of the changes for the changelog\n\n"
            "Can you get these done by Wednesday?\n\n"
            "— Alex"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Update color palette per brand guidelines",
                "people": ["Alex"],
                "deadline": "Wednesday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Share Figma link with engineering team",
                "people": ["Alex"],
                "deadline": "Wednesday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Write changelog summary of design changes",
                "people": ["Alex"],
                "deadline": "Wednesday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "commit_03",
        "source": "gmail",
        "subject": "Re: Dinner plans",
        "sender": "mike@gmail.com",
        "raw_text": (
            "Sounds great! I'll make the reservation at Nobu for Saturday at 7pm. "
            "Can you check with Lisa if she's free and let me know by Thursday?\n\n"
            "Also, I'll bring that book I mentioned — remind me if I forget.\n\n"
            "Mike"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Check with Lisa about Saturday dinner and reply to Mike",
                "people": ["Mike", "Lisa"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "commit_04",
        "source": "gmail",
        "subject": "Re: Apartment lease renewal",
        "sender": "landlord@property.com",
        "raw_text": (
            "Hi Nick,\n\n"
            "Your lease expires on April 30. Please review the attached renewal "
            "terms and return the signed document by April 15.\n\n"
            "If you have any questions, feel free to reach out.\n\n"
            "Regards,\nProperty Management"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Review and sign lease renewal",
                "people": ["landlord"],
                "deadline": "April 15",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "commit_05",
        "source": "gmail",
        "subject": "Re: Mentorship session notes",
        "sender": "intern@company.com",
        "raw_text": (
            "Hi Nick,\n\n"
            "Thanks for the session today! Just wanted to confirm — you mentioned "
            "you'd share some resources on system design and introduce me to your "
            "friend who works at Stripe. Looking forward to it!\n\n"
            "Best,\nJessica"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Share system design resources with Jessica",
                "people": ["Jessica"],
                "deadline": None,
                "commitment_type": "you_committed",
            },
            {
                "title": "Introduce Jessica to Stripe contact",
                "people": ["Jessica"],
                "deadline": None,
                "commitment_type": "you_committed",
            },
        ],
    },

    # =========================================================================
    # IMPLICIT ACTION ITEMS (requires reading between the lines)
    # =========================================================================
    {
        "id": "implicit_01",
        "source": "gmail",
        "subject": "Board meeting prep",
        "sender": "ceo@company.com",
        "raw_text": (
            "Team,\n\n"
            "Board meeting is next Tuesday. I need everyone to have their "
            "department updates ready by Monday EOD. Nick, your section should "
            "cover engineering velocity and the new feature pipeline.\n\n"
            "Let's make sure we're aligned.\n\n"
            "— David"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Prepare engineering velocity and feature pipeline update for board meeting",
                "people": ["David"],
                "deadline": "Monday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "implicit_02",
        "source": "slack",
        "subject": "#engineering channel",
        "sender": "teammate_chen",
        "raw_text": (
            "@nick the CI pipeline has been flaky all week — tests pass locally "
            "but fail in GitHub Actions about 30% of the time. Think it might be "
            "a race condition in the database setup. Could really use a second pair "
            "of eyes on this when you get a chance."
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Look into flaky CI pipeline race condition",
                "people": ["Chen"],
                "deadline": None,
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "implicit_03",
        "source": "gmail",
        "subject": "Quick question about API rate limits",
        "sender": "frontend_dev@company.com",
        "raw_text": (
            "Hey Nick,\n\n"
            "I'm hitting rate limit errors on the dashboard endpoint during peak "
            "hours. Is there a way to increase the limit or should I add client-side "
            "caching? Happy to implement either if you can point me in the right "
            "direction.\n\n"
            "Thanks,\nRyan"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Respond to Ryan about API rate limit issue and recommend approach",
                "people": ["Ryan"],
                "deadline": None,
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "implicit_04",
        "source": "slack",
        "subject": "DM from product manager",
        "sender": "pm_olivia",
        "raw_text": (
            "hey nick, just a heads up — the client demo moved to Thursday instead "
            "of Friday. We'll need the new onboarding flow deployed to staging by "
            "Wednesday night. Let me know if that's doable."
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Deploy onboarding flow to staging before Thursday demo",
                "people": ["Olivia"],
                "deadline": "Wednesday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "implicit_05",
        "source": "gmail",
        "subject": "Fwd: Conference speaker slot",
        "sender": "events@techconf.io",
        "raw_text": (
            "Hi Nick,\n\n"
            "We'd love to have you speak at TechConf 2026 on June 15. Your talk "
            "on 'Building with AI Agents' was a hit last year.\n\n"
            "Could you confirm your availability and send a talk abstract by "
            "May 1st?\n\n"
            "Looking forward to hearing from you!\n\n"
            "— TechConf Team"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Confirm availability and send talk abstract for TechConf",
                "people": ["TechConf Team"],
                "deadline": "May 1",
                "commitment_type": "they_requested",
            },
        ],
    },

    # =========================================================================
    # NON-ACTION ITEMS (should NOT extract anything)
    # =========================================================================
    {
        "id": "non_action_01",
        "source": "gmail",
        "subject": "Your weekly digest from Medium",
        "sender": "noreply@medium.com",
        "raw_text": (
            "Stories for you\n\n"
            "Top picks for Nick Chua\n\n"
            "How I Built a $10M SaaS in 18 Months — Jason Chen in Startup Grind\n"
            "The Future of AI Agents — Sarah Liu in Towards Data Science\n"
            "Why Rust is Replacing C++ — David Park in Better Programming\n\n"
            "Read more on Medium\n\n"
            "You're receiving this because you signed up for Medium Daily Digest.\n"
            "Unsubscribe | Help"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },
    {
        "id": "non_action_02",
        "source": "gmail",
        "subject": "Your Uber receipt",
        "sender": "noreply@uber.com",
        "raw_text": (
            "Thanks for riding with Uber\n\n"
            "Trip on March 20, 2026\n"
            "UberX | 12:34 PM\n\n"
            "From: 123 Main St, San Francisco\n"
            "To: 456 Market St, San Francisco\n\n"
            "Trip fare: $18.50\n"
            "Service fee: $2.50\n"
            "Total: $21.00\n\n"
            "Charged to Visa ****4242"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },
    {
        "id": "non_action_03",
        "source": "gmail",
        "subject": "GitHub Actions: Build succeeded",
        "sender": "noreply@github.com",
        "raw_text": (
            "Run #1234 of workflow 'CI' succeeded.\n\n"
            "Branch: main\n"
            "Commit: 9f2ab96 Fix unused import\n"
            "Duration: 2m 34s\n\n"
            "View workflow run: https://github.com/nchua/projects/actions/runs/1234"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },
    {
        "id": "non_action_04",
        "source": "gmail",
        "subject": "Your order has shipped!",
        "sender": "orders@amazon.com",
        "raw_text": (
            "Great news! Your package is on its way.\n\n"
            "Order #112-3456789\n"
            "Anker USB-C Hub, 7-in-1\n\n"
            "Estimated delivery: March 25, 2026\n"
            "Carrier: UPS\n"
            "Tracking: 1Z999AA10123456784\n\n"
            "Track your package: https://amazon.com/track"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },
    {
        "id": "non_action_05",
        "source": "slack",
        "subject": "#general channel",
        "sender": "hr_bot",
        "raw_text": (
            "Reminder: The office will be closed next Monday for the holiday. "
            "Enjoy your long weekend, everyone!"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },

    # =========================================================================
    # GITHUB NOTIFICATIONS
    # =========================================================================
    {
        "id": "github_01",
        "source": "github",
        "subject": "PR #42: Add REST API rate limiting",
        "sender": "teammate_chen",
        "raw_text": (
            "chen requested your review on PR #42: Add REST API rate limiting\n\n"
            "This PR adds rate limiting middleware to all API endpoints using "
            "slowapi. Includes per-user and per-IP limits with Redis backend.\n\n"
            "Files changed: 5\n"
            "+142 -12\n\n"
            "https://github.com/nchua/projects/pull/42"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Review PR #42: Add REST API rate limiting",
                "people": ["Chen"],
                "deadline": None,
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "github_02",
        "source": "github",
        "subject": "Issue #87: Database connection pool exhaustion in production",
        "sender": "oncall_bot",
        "raw_text": (
            "You were assigned to Issue #87: Database connection pool exhaustion in production\n\n"
            "Severity: High\n"
            "Reporter: monitoring-bot\n\n"
            "Production database connection pool hit 100% utilization at 3:42 AM. "
            "Several API requests timed out. Pool recovered after 8 minutes but "
            "this is the third occurrence this week.\n\n"
            "https://github.com/nchua/projects/issues/87"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Investigate and fix database connection pool exhaustion (Issue #87)",
                "people": [],
                "deadline": None,
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "github_03",
        "source": "github",
        "subject": "CI failed: main branch",
        "sender": "github-actions",
        "raw_text": (
            "Workflow 'CI' failed on branch main\n\n"
            "Commit: a1b2c3d Add new endpoint\n"
            "Author: nick\n"
            "Failed step: test_integration\n"
            "Error: AssertionError: Expected 200, got 422\n\n"
            "https://github.com/nchua/projects/actions/runs/5678"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Fix failing CI on main branch (test_integration)",
                "people": [],
                "deadline": None,
                "commitment_type": "they_requested",
            },
        ],
    },

    # =========================================================================
    # AMBIGUOUS / EDGE CASES
    # =========================================================================
    {
        "id": "ambiguous_01",
        "source": "gmail",
        "subject": "Re: Team offsite planning",
        "sender": "coworker@company.com",
        "raw_text": (
            "Hey all,\n\n"
            "Here's the plan for the offsite:\n"
            "- Sarah is booking the venue\n"
            "- Mike is handling catering\n"
            "- Nick, would be great if you could put together a short presentation "
            "on our Q1 wins\n"
            "- Everyone: please fill out the dietary preferences form by Friday\n\n"
            "Let me know if there are any conflicts.\n\n"
            "— Laura"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Prepare Q1 wins presentation for team offsite",
                "people": ["Laura"],
                "deadline": None,
                "commitment_type": "they_requested",
            },
            {
                "title": "Fill out dietary preferences form for offsite",
                "people": ["Laura"],
                "deadline": "Friday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "ambiguous_02",
        "source": "gmail",
        "subject": "Fwd: Meeting notes from product sync",
        "sender": "pm@company.com",
        "raw_text": (
            "FYI — forwarding the notes from today's sync. Relevant bits for you:\n\n"
            "- We're leaning toward Option B for the pricing model\n"
            "- The mobile team wants to ship by end of month\n"
            "- There was some discussion about whether the API supports batch "
            "operations — nobody was sure. Might be worth checking.\n\n"
            "No action needed from you unless you want to weigh in on the "
            "pricing discussion.\n\n"
            "— Pat"
        ),
        "expected_has_action_items": False,
        "expected_action_items": [],
    },
    {
        "id": "ambiguous_03",
        "source": "slack",
        "subject": "DM from CEO",
        "sender": "ceo_david",
        "raw_text": (
            "Great work on the demo today. Investors were really impressed with "
            "the AI features. Let's grab coffee this week to talk about next steps "
            "for the fundraise."
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Schedule coffee with David to discuss fundraise next steps",
                "people": ["David"],
                "deadline": "this week",
                "commitment_type": "mutual",
            },
        ],
    },

    # =========================================================================
    # MULTI-ACTION ITEMS IN ONE MESSAGE
    # =========================================================================
    {
        "id": "multi_01",
        "source": "gmail",
        "subject": "Before you leave for vacation",
        "sender": "manager@company.com",
        "raw_text": (
            "Nick,\n\n"
            "Before your PTO starts on Thursday, can you make sure to:\n\n"
            "1. Hand off the API migration to Ryan — he'll need access to the "
            "staging environment and a brief walkthrough\n"
            "2. Update the on-call runbook with the new alerting thresholds\n"
            "3. Set your Slack status and email auto-responder\n"
            "4. Send me a quick summary of where everything stands so I can "
            "cover for you\n\n"
            "Have a great trip!\n\n"
            "— Karen"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Hand off API migration to Ryan with staging access and walkthrough",
                "people": ["Karen", "Ryan"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Update on-call runbook with new alerting thresholds",
                "people": ["Karen"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Set Slack status and email auto-responder for PTO",
                "people": ["Karen"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Send status summary to Karen before PTO",
                "people": ["Karen"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
        ],
    },
    {
        "id": "multi_02",
        "source": "gmail",
        "subject": "Action items from Monday standup",
        "sender": "scrum_master@company.com",
        "raw_text": (
            "Hi team,\n\n"
            "Here are this week's action items from standup:\n\n"
            "Nick:\n"
            "- Investigate the memory leak in the worker process\n"
            "- Pair with Jessica on the OAuth integration\n"
            "- Update the deployment docs\n\n"
            "Alex:\n"
            "- Finalize the design for the settings page\n"
            "- Create tickets for the Q2 roadmap\n\n"
            "Ryan:\n"
            "- Fix the broken E2E tests\n"
            "- Review Nick's PR on rate limiting\n\n"
            "Let's sync on progress at Thursday's standup.\n\n"
            "— Tom"
        ),
        "expected_has_action_items": True,
        "expected_action_items": [
            {
                "title": "Investigate memory leak in worker process",
                "people": ["Tom"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Pair with Jessica on OAuth integration",
                "people": ["Tom", "Jessica"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
            {
                "title": "Update deployment docs",
                "people": ["Tom"],
                "deadline": "Thursday",
                "commitment_type": "they_requested",
            },
        ],
    },
]


def get_fixtures(
    source: str | None = None,
    has_action_items: bool | None = None,
) -> list[dict]:
    """Filter fixtures by source and/or whether they have action items."""
    results = FIXTURES
    if source is not None:
        results = [f for f in results if f["source"] == source]
    if has_action_items is not None:
        results = [f for f in results if f["expected_has_action_items"] == has_action_items]
    return results


def get_fixture_by_id(fixture_id: str) -> dict | None:
    """Get a single fixture by ID."""
    for f in FIXTURES:
        if f["id"] == fixture_id:
            return f
    return None
