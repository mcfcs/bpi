export type Tier = "A" | "B" | "C";
export type Provenance = "synthetic" | "public" | "internal";
export type MethodType = "quant" | "qual" | "mixed";
export type Role = "bu_user" | "bu_approver" | "si_analyst";

export interface Profile {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  team_id: string;
  team_name: string;
}

export interface SourceView {
  finding_id: string;
  study_id: string;
  study_code: string;
  study_title: string;
  owner_team: string;
  text: string;
  finding_type: "quant_stat" | "qual_theme" | "verbatim" | null;
  metric_key: string | null;
  value: number | null;
  unit: string | null;
  base_n: number | null;
  subgroup: Record<string, string> | null;
  subgroup_label: string;
  method_type: "quant" | "qual" | "mixed" | null;
  method_label: string;
  sample_size: number | null;
  fieldwork_end: string | null;
  region_label: string;
  population_label: string;
  tier: Tier | null;
  tier_overridden: boolean;
  /** Report page the finding was read from; null when the extractor could not place it. */
  page: number | null;
  source_excerpt: string | null;
  /** "SI-2026-014 · p.3", or the bare code when there is no page. */
  cite_label: string | null;
  /** Set only when the study has a report PDF. Needs a signed link to open (see openReport). */
  document_url: string | null;
  provenance: Provenance | null;
  publisher: string | null;
  /** "Survey · n=1,200", "6 FGDs · 48 participants", "Tracking survey · n=2,000". */
  method_detail?: string;
  /** "Sep 2025", or "date not stated". */
  fieldwork_label?: string;
  evidence_kind?: "quant" | "qual";
  /** What the tier was scored from: "Recency only (qualitative: ...)" for qualitative studies. */
  tier_basis?: string | null;
  /** "Metro Manila (urban)", "provincial cities", "nationwide". */
  area_label?: string | null;
  access_level?: "open" | "restricted";
  /** Emotion cue read from a qualitative theme or verbatim's own words. */
  emotion?: EmotionCue | null;
}

/** A feeling participants voiced, detected in code from their wording (a lexicon, not a model). */
export interface EmotionCue {
  key: string;
  label: string;
  tone: "negative" | "positive" | "neutral" | string;
  basis: "lexicon" | string;
  cues?: string[];
}

export interface Evidence {
  finding_id: string;
  stance: "supports" | "contradicts" | "context";
}

export interface Claim {
  text: string;
  kind: "headline" | "breakdown" | "qualitative_insight";
  evidence: Evidence[];
  verbatim_ids: string[];
  qual_only: boolean;
  emotions?: EmotionCue[];
  /** Topics of unresolved conflicts whose figures this claim cites. */
  disputed?: string[];
}

export type DiffersBy = "age" | "region" | "segment" | "period" | "method";

export interface ContextNote {
  topic: string;
  finding_ids: string[];
  differs_by: DiffersBy[];
  explanation: string;
}

export interface ChartBar {
  finding_id: string;
  /** Part of an unresolved conflict: an S&I analyst is checking this figure. */
  disputed?: boolean;
  study_id: string;
  study_code: string;
  label: string;
  detail: string;
  value: number;
  unit: string;
  base_n: number | null;
  tier: Tier | null;
  study_title: string;
  sample_size: number | null;
  method_type: "quant" | "qual" | "mixed" | null;
  region_label: string;
  fieldwork_end: string | null;
}

export interface ChartSpec {
  metric_key: string;
  title: string;
  unit: string;
  bars: ChartBar[];
}

export interface RestrictedMatch {
  study_id: string;
  code: string;
  title: string;
  owner_team: string;
  similarity: number;
  request_status: "pending" | "approved" | "denied" | null;
}

export interface Escalation {
  id: string;
  status: "open" | "answered" | "closed";
  reason: "user_request" | "unresolved_conflict" | "low_confidence" | string;
  response?: string | null;
  note?: string | null;
  responded_by?: string | null;
  responded_at?: string | null;
  created_at?: string;
  /** Set when the same open question was sent again; the open escalation comes back unchanged. */
  duplicate?: boolean;
  /** Set when a new brief joined a check S&I already had open from an earlier brief. */
  existing?: boolean;
}

export type Audience = "executive" | "analyst" | "plain";

export interface AudienceSummary {
  text: string;
  finding_ids: string[];
}

export interface PreparedFor {
  name: string;
  team: string;
  role: string;
  role_label: string;
  focus_metrics: string[];
  team_study_codes: string[];
  note: string | null;
}

/** A qualitative theme that runs against a survey finding on the same topic: colour, never a conflict. */
export interface QualContrast {
  finding_id: string;
  topic: string;
  quant_finding_ids: string[];
}

export interface GapItem {
  code: string;
  text: string;
  ask: string | null;
}

export interface EscalationDraft {
  brief_id: string;
  question: string;
  found: string;
  study_codes: string[];
  confidence: "high" | "medium" | "low" | null;
  gaps: { id: string; text: string; ask: string | null; checked: boolean }[];
  differences: {
    kind: "unresolved_conflict" | "context_difference" | "within_study";
    topic: string;
    label: string;
    differs_by: DiffersBy[];
    explanation: string;
    study_codes: string[];
  }[];
  suggested_question: string;
  note: string;
}

export interface Brief {
  id: string;
  question: string;
  /** Set on a follow-up: the brief it continues. */
  follow_up_of?: { id: string; question: string } | null;
  created_at: string;
  generated_by: string | null;
  generator_note: string | null;
  no_headline_message: string | null;
  disclaimer: string | null;
  claims: Claim[];
  context_notes: ContextNote[];
  unresolved_conflicts: ContextNote[];
  topic_labels: Record<string, string>;
  chart_requests: string[];
  gaps: string[];
  charts: ChartSpec[];
  confidence: { level: "high" | "medium" | "low"; reasons: string[] };
  sources: Record<string, SourceView>;
  restricted_matches: RestrictedMatch[];
  escalation: Escalation | null;
  /** Every escalation on this brief, oldest first (stored briefs only). */
  escalations?: Escalation[];
  dropped_claims: number;
  regenerated: boolean;
  /** Two trends or patterns inside one study, each for its own group of respondents. */
  study_patterns?: ContextNote[];
  summaries?: Partial<Record<Audience, AudienceSummary>>;
  prepared_for?: PreparedFor | null;
  qual_contrasts?: QualContrast[];
  gap_items?: GapItem[];
}

export interface BriefSummary {
  id: string;
  question: string;
  confidence: string | null;
  created_at: string;
}

export interface TierBreakdown {
  method_points: number;
  sample_points: number;
  recency_points: number;
  age_months: number;
  score: number;
  tier: Tier;
}

export interface FindingRow {
  id: string;
  ordinal: number;
  text: string;
  theme: string | null;
  finding_type: "quant_stat" | "qual_theme" | "verbatim" | null;
  metric_key: string | null;
  value: number | null;
  unit: "%" | "rank" | "score" | null;
  base_n: number | null;
  subgroup: Record<string, string> | null;
  direction: "high" | "low" | "neutral" | null;
  page?: number | null;
  source_excerpt?: string | null;
  cite_label?: string | null;
  document_url?: string | null;
}

export interface StudyDocument {
  id: string;
  filename: string;
  page_count: number | null;
  byte_size: number;
  source_kind: Provenance | string;
  license: string | null;
  source_url: string | null;
  url: string;
}

interface StudyListBase {
  id: string;
  code: string;
  title: string;
  owner_team: string;
  access_level: "open" | "restricted";
  method_type: MethodType | null;
  year: number | null;
  provenance: Provenance;
  publisher: string | null;
  has_document: boolean;
  request_status: "pending" | "approved" | "denied" | null;
}

/** A catalogue row the caller may read: the full card. */
export interface ReadableStudy extends StudyListBase {
  can_read: true;
  summary: string | null;
  sample_size: number | null;
  fieldwork_end: string | null;
  population: StudyDetail["population"];
  effective_tier: Tier | null;
  finding_count: number;
  document: StudyDocument | null;
}

/** A restricted study: catalogue metadata only, never its findings. */
export interface RestrictedStudy extends StudyListBase {
  can_read: false;
}

export type StudyListItem = ReadableStudy | RestrictedStudy;

export interface StudyDetail {
  id: string;
  code: string;
  title: string;
  summary: string | null;
  owner_team_id: string;
  owner_team: string;
  access_level: "open" | "restricted";
  review_status: "pending_review" | "approved" | "rejected";
  source_name: string | null;
  source_text?: string | null;
  created_at: string;
  reviewed_at: string | null;
  review_note: string | null;
  method_type: MethodType | null;
  sample_size: number | null;
  fieldwork_end: string | null;
  provenance?: Provenance;
  publisher?: string | null;
  document?: StudyDocument | null;
  population: { age_min: number | null; age_max: number | null; regions: string[]; segment: string | null } | null;
  robustness_tier: Tier | null;
  tier_override: Tier | null;
  tier_override_reason: string | null;
  effective_tier: Tier | null;
  tier_breakdown: TierBreakdown | null;
  findings: FindingRow[];
  finding_count?: number;
  /** Checkpoint 1 aids, on pending studies for S&I only. */
  privacy?: PrivacyFlags;
  overlaps?: StudyOverlap[];
}

/** Findings that may identify a person (privacy.py pattern rules). */
export interface PrivacyFlags {
  findings: { finding_id: string; ordinal: number; text: string; matches: { kind: string; label: string; match: string; start: number; end: number }[] }[];
  source_matches: number;
}

/** An approved study a pending one overlaps (overlap.py), compared in code. */
export interface StudyOverlap {
  study_id: string;
  code: string;
  title: string;
  tier: Tier | null;
  owner_team: string;
  place: string;
  fieldwork_end: string | null;
  topics: string[];
  matches: number;
  verdict: "repeat" | "newer_wave" | "same_topic";
  verdict_text: string;
  differs_by: string[];
  figures: { metric: string; new: string; old: string }[];
}

export interface AccessRequest {
  id: string;
  study_id: string;
  study_code: string | null;
  study_title: string | null;
  owner_team: string | null;
  purpose: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
  decided_at: string | null;
  decision_note: string | null;
  requester: string;
  requester_team: string;
  mine: boolean;
  can_decide: boolean;
}

export interface EscalationRow {
  id: string;
  brief_id: string | null;
  question: string | null;
  confidence: string | null;
  reason: "user_request" | "unresolved_conflict" | "low_confidence";
  note: string | null;
  status: "open" | "answered" | "closed";
  response: string | null;
  created_at: string;
  responded_at: string | null;
  requested_by: string;
  requester_team: string;
  responded_by: string | null;
  /** The first request in this conversation: the same person asking about the same question again. */
  thread_id: string;
}

export type CoverageState = "covered" | "covered_stale" | "partial" | "gap";

export interface CoverageCaveat {
  code: "conflict" | "restricted_match" | string;
  text: string;
  studies?: { study_id: string; code: string; title: string; owner_team: string }[];
}

export interface CoverageObjective {
  text: string;
  coverage: CoverageState;
  finding_ids: string[];
  coverage_label?: string;
  new_problem?: boolean;
  newest_fieldwork?: string | null;
  caveats?: CoverageCaveat[];
}

export interface CoverageCheck {
  id: string;
  title: string;
  created_at: string;
  requested_by?: string;
  adapter?: string | null;
  submission?: Record<string, unknown> | null;
  submitted_at?: string | null;
  result: { objectives: CoverageObjective[]; recommended_new_scope: string; new_problems?: string[] };
  findings?: Record<string, SourceView>;
}

/** A check a requester sent to S&I, as S&I's inbox lists it. */
export interface SubmittedCheck {
  id: string;
  title: string;
  created_at: string;
  submitted_at: string;
  adapter: string | null;
  requested_by: string;
  requester_team: string;
  new_problems: number;
  objectives: number;
}

/** GET /api/audit/summary: counts from the audit log for S&I. */
export interface UsageSummary {
  value?: UsageValue;
  days: number;
  briefs: {
    total: number;
    confidence: { high: number; medium: number; low: number };
    by_team: { team: string; count: number }[];
    restricted_also_matched: number;
    regenerated: number;
    dropped_claims: number;
    written_by_model: number;
    written_from_templates: number;
  };
  most_asked: { question: string; count: number }[];
  unanswered: { question: string; team: string; asked_at: string }[];
  unanswered_total: number;
  escalations: { automatic: number; from_users: number; open: number; answered: number };
  access_requests: { pending: number; approved: number; denied: number };
  coverage_checks: { run: number; sent_to_si: number };
}

export interface AuditRow {
  id: number;
  occurred_at: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown>;
  actor: string;
}

export interface Team {
  id: string;
  name: string;
  kind: "si" | "bu";
}

/** "A new study answers your question": an earlier unanswered question of the reader's. */
export interface AnswerAlert {
  id: string;
  brief_id: string;
  study_id: string;
  question: string;
  created_at: string;
  read_at: string | null;
  /** Null when the reader has since lost access to the study. */
  study_code: string | null;
  study_title: string | null;
}


export interface GapRow {
  family: string;
  label: string;
  cells: Record<string, CoverageState>;
  best: CoverageState;
  studies: string[];
  newest_fieldwork: string | null;
  asked: number;
  /** Questions no readable study answered whose closest topic is this one. */
  unanswered: number;
  teams: string[];
  attention: boolean;
}

export interface GapMap {
  columns: string[];
  rows: GapRow[];
  days: number;
  studies_read: number;
  unanswered: { question: string; team: string; last_asked: string; times: number; topic: string | null }[];
}

/** What briefs delivered (usage.value): counts, plus hours saved as a labelled estimate. */
export interface UsageValue {
  briefs: number;
  answered: number;
  answered_without_analyst: number;
  share_without_analyst: number | null;
  cross_team: number;
  studies_reused: number;
  already_covered: number;
  alerts_sent: number;
  alerts_opened: number;
  hours_saved: number;
  minutes_per_question: number;
}
