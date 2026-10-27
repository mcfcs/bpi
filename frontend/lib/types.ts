export type Tier = "A" | "B" | "C";
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
  reason: string;
  response?: string | null;
}

export interface Brief {
  id: string;
  question: string;
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
  dropped_claims: number;
  regenerated: boolean;
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
}

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
  method_type: "quant" | "qual" | "mixed" | null;
  sample_size: number | null;
  fieldwork_end: string | null;
  population: { age_min: number | null; age_max: number | null; regions: string[]; segment: string | null } | null;
  robustness_tier: Tier | null;
  tier_override: Tier | null;
  tier_override_reason: string | null;
  effective_tier: Tier | null;
  tier_breakdown: TierBreakdown | null;
  findings: FindingRow[];
  finding_count?: number;
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
}

export interface CoverageObjective {
  text: string;
  coverage: "covered" | "partial" | "gap";
  finding_ids: string[];
}

export interface CoverageCheck {
  id: string;
  title: string;
  created_at: string;
  requested_by?: string;
  adapter?: string | null;
  submission?: Record<string, unknown> | null;
  submitted_at?: string | null;
  result: { objectives: CoverageObjective[]; recommended_new_scope: string };
  findings?: Record<string, SourceView>;
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
