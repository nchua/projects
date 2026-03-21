// Enums
export type UnitType = "concept" | "cloze" | "explanation" | "application" | "connection" | "generative";
export type Rating = "forgot" | "struggled" | "got_it" | "easy";
export type InboxStatus = "pending" | "accepted" | "rejected";
export type ConceptTier = "new" | "learning" | "reviewing" | "mastered";

// Auth
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  email: string;
  display_name: string | null;
}

// Topics
export interface TopicResponse {
  id: number;
  name: string;
  description: string | null;
  target_retention: number;
  created_at: string;
  concept_count: number;
  mastery_pct: number;
}

// Concepts
export interface ConceptResponse {
  id: number;
  topic_id: number;
  name: string;
  description: string | null;
  mastery_score: number;
  tier: ConceptTier;
  created_at: string;
  unit_count: number;
}

// Review Cards (from GET /learning-units/due)
export interface ReviewCard {
  id: number;
  concept_id: number;
  type: UnitType;
  front_content: string;
  back_content: string;
  topic_name: string;
  source_name: string | null;
}

// Learning Units (full)
export interface LearningUnitResponse {
  id: number;
  concept_id: number;
  type: UnitType;
  front_content: string;
  back_content: string;
  difficulty: number;
  stability: number;
  retrievability: number;
  review_count: number;
  lapse_count: number;
  ai_generated: boolean;
  auto_accepted: boolean;
  created_at: string;
}

// Reviews
export interface ReviewCreate {
  learning_unit_id: number;
  rating: Rating;
  time_to_reveal_ms?: number;
  time_reading_ms?: number;
}

export interface ReviewResponse {
  id: number;
  learning_unit_id: number;
  rating: Rating;
  time_to_reveal_ms: number | null;
  time_reading_ms: number | null;
  reviewed_at: string;
  next_review_at: string | null;
}

export interface SessionSummary {
  total_reviewed: number;
  recalled: number;
  struggled: number;
  forgot: number;
  session_duration_seconds: number | null;
  strongest_topic: string | null;
  weakest_topic: string | null;
}

// Inbox
export interface InboxItemResponse {
  id: number;
  learning_unit_id: number;
  confidence_score: number;
  status: InboxStatus;
  created_at: string;
  front_content: string;
  back_content: string;
  unit_type: UnitType;
  source_name: string | null;
}

// Source
export interface SourceResponse {
  id: number;
  type: string;
  uri: string | null;
  name: string;
  last_synced_at: string | null;
  created_at: string;
}
