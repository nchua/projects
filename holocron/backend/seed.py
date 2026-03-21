"""Seed the database with sample topics, concepts, and cards for testing."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.topic import Topic
from app.models.concept import Concept
from app.models.learning_unit import LearningUnit, UnitType
from app.models.review import Review  # noqa: F401 — needed for relationship resolution
from app.models.source import Source, SourceType


def seed() -> None:
    """Create sample data for development and testing."""
    db = SessionLocal()

    try:
        # Create test user
        user = db.query(User).filter(User.email == "test@example.com").first()
        if not user:
            user = User(
                email="test@example.com",
                hashed_password=hash_password("TestPass123!"),
                display_name="Nick",
            )
            db.add(user)
            db.flush()

        # Create source
        manual_source = Source(
            user_id=user.id,
            type=SourceType.MANUAL,
            name="Manual Input",
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(manual_source)
        db.flush()

        # --- Topic 1: AI Tools ---
        ai_topic = Topic(
            user_id=user.id,
            name="AI Tools",
            description="Applied AI tools, frameworks, and workflows",
        )
        db.add(ai_topic)
        db.flush()

        ai_concepts = [
            {
                "name": "Chain of Thought Prompting",
                "description": (
                    "Breaking complex reasoning into"
                    " step-by-step intermediate results"
                ),
                "cards": [
                    {
                        "type": UnitType.CONCEPT,
                        "front": (
                            "What is chain-of-thought (CoT)"
                            " prompting and why does it"
                            " improve LLM performance?"
                        ),
                        "back": (
                            "CoT prompting breaks complex"
                            " reasoning into intermediate"
                            " steps. It works because it"
                            " forces the model to show its"
                            " work, allocating more compute"
                            " to each step and reducing"
                            " compounding errors."
                        ),
                    },
                    {
                        "type": UnitType.CLOZE,
                        "front": (
                            "Chain-of-thought prompting"
                            " improves LLM performance by"
                            " forcing the model to {{blank}}"
                            " its reasoning into intermediate"
                            " steps, which allocates more"
                            " {{blank}} to each step."
                        ),
                        "back": "break down; compute",
                    },
                ],
            },
            {
                "name": "RAG (Retrieval-Augmented Generation)",
                "description": "Combining retrieval systems with generative models",
                "cards": [
                    {
                        "type": UnitType.CONCEPT,
                        "front": "What is RAG and what problem does it solve?",
                        "back": (
                            "RAG (Retrieval-Augmented"
                            " Generation) combines a"
                            " retrieval system with a"
                            " generative model. It solves"
                            " the knowledge cutoff problem"
                            " by grounding generation in"
                            " retrieved, up-to-date documents"
                            " rather than relying solely on"
                            " training data."
                        ),
                    },
                    {
                        "type": UnitType.CLOZE,
                        "front": (
                            "RAG solves the {{blank}}"
                            " problem by grounding"
                            " generation in {{blank}}"
                            " documents rather than relying"
                            " solely on {{blank}} data."
                        ),
                        "back": "knowledge cutoff; retrieved, up-to-date; training",
                    },
                ],
            },
            {
                "name": "Function Calling / Tool Use",
                "description": "Enabling LLMs to invoke structured APIs",
                "cards": [
                    {
                        "type": UnitType.CONCEPT,
                        "front": (
                            "How does function calling"
                            " (tool use) work in"
                            " modern LLMs?"
                        ),
                        "back": (
                            "The model is given function"
                            " schemas as part of its"
                            " context. When it determines a"
                            " function is needed, it outputs"
                            " a structured JSON call instead"
                            " of text. The system executes"
                            " the function and returns"
                            " results for the model to"
                            " incorporate."
                        ),
                    },
                ],
            },
        ]

        for c_data in ai_concepts:
            concept = Concept(
                topic_id=ai_topic.id,
                name=c_data["name"],
                description=c_data["description"],
            )
            db.add(concept)
            db.flush()

            for card in c_data["cards"]:
                unit = LearningUnit(
                    concept_id=concept.id,
                    type=card["type"],
                    front_content=card["front"],
                    back_content=card["back"],
                    source_id=manual_source.id,
                    auto_accepted=True,
                    next_review_at=datetime.now(timezone.utc),
                )
                db.add(unit)

        # --- Topic 2: Business Strategy ---
        biz_topic = Topic(
            user_id=user.id,
            name="Business Strategy",
            description="Strategy frameworks, mental models, and business analysis",
        )
        db.add(biz_topic)
        db.flush()

        biz_concepts = [
            {
                "name": "Aggregation Theory",
                "description": "Ben Thompson's framework for platform dominance",
                "cards": [
                    {
                        "type": UnitType.CONCEPT,
                        "front": (
                            "What is Aggregation Theory"
                            " and what are its three key"
                            " characteristics?"
                        ),
                        "back": (
                            "Aggregation Theory (Ben"
                            " Thompson / Stratechery)"
                            " explains how platforms win by"
                            " aggregating demand. Three"
                            " characteristics: (1) direct"
                            " relationship with users,"
                            " (2) zero marginal cost to"
                            " serve, (3) network effects"
                            " from supplier aggregation."
                        ),
                    },
                ],
            },
            {
                "name": "Jobs to Be Done",
                "description": (
                    "Clayton Christensen's framework for"
                    " understanding customer motivation"
                ),
                "cards": [
                    {
                        "type": UnitType.CONCEPT,
                        "front": "What is the 'Jobs to Be Done' framework?",
                        "back": (
                            "JTBD (Clayton Christensen)"
                            " says customers don't buy"
                            " products — they 'hire' them"
                            " to do a job. Understanding"
                            " the functional, social, and"
                            " emotional dimensions of the"
                            " job reveals real competitive"
                            " alternatives and innovation"
                            " opportunities."
                        ),
                    },
                    {
                        "type": UnitType.CLOZE,
                        "front": (
                            "The Jobs to Be Done framework"
                            " says customers {{blank}}"
                            " products to do a {{blank}}."
                            " The three dimensions are"
                            " {{blank}}, {{blank}},"
                            " and {{blank}}."
                        ),
                        "back": "hire; job; functional, social, emotional",
                    },
                ],
            },
        ]

        for c_data in biz_concepts:
            concept = Concept(
                topic_id=biz_topic.id,
                name=c_data["name"],
                description=c_data["description"],
            )
            db.add(concept)
            db.flush()

            for card in c_data["cards"]:
                unit = LearningUnit(
                    concept_id=concept.id,
                    type=card["type"],
                    front_content=card["front"],
                    back_content=card["back"],
                    source_id=manual_source.id,
                    auto_accepted=True,
                    next_review_at=datetime.now(timezone.utc),
                )
                db.add(unit)

        db.commit()
        print(
            f"Seeded: 2 topics, "
            f"{len(ai_concepts) + len(biz_concepts)}"
            " concepts, cards created"
        )

    finally:
        db.close()


if __name__ == "__main__":
    seed()
