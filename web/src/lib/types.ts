/**
 * TypeScript mirrors of the projections in `server/views.py`.
 *
 * These describe the wire format, not a second model layer. Every derived value that a
 * component might be tempted to recompute - `canApprove`, `isUsable`, `completeness` -
 * arrives as a field, because the Python side owns those rules and a duplicate in
 * TypeScript would be a second definition free to drift from the first.
 */

export type Stage = "describe" | "clarify" | "review" | "executed" | "refused";

export type Provenance =
  | "user_supplied"
  | "planner_inferred"
  | "unknown"
  | "unsupported";

export type PlanStatus =
  | "draft"
  | "needs_clarification"
  | "ready_for_review"
  | "approved"
  | "rejected"
  | "executed"
  | "superseded";

export type ValidationStatus =
  | "valid"
  | "missing"
  | "schema_invalid"
  | "incomparable_period"
  | "incomparable_geography"
  | "incomparable_unit"
  | "incomparable_source";

export type TraceAuthority =
  | "user_supplied"
  | "agent_inference"
  | "deterministic_validation"
  | "api_evidence"
  | "human_approval"
  | "deterministic_calculation"
  | "explanation_layer"
  | "system";

export type LimitationSeverity = "info" | "caution" | "blocking";

export type DataClass =
  | "atlas_evidence"
  | "public_market_data"
  | "public_company_benchmark"
  | "simulated_retailer_data"
  | "user_supplied_proprietary_data"
  | "user_assumption"
  | "agent_interpretation";

export interface DataClassBadge {
  data_class: DataClass;
  label: string;
  short_note: string;
}

export interface Geography {
  slug: string;
  display_name: string;
  geography_type: string;
  lat?: number | null;
  lon?: number | null;
  data_class?: DataClassBadge;
}

export interface MetricDefinition {
  metric_id: string;
  display_name: string;
  atlas_datapoint: string;
  atlas_item_code: string | null;
  category: string;
  category_label: string;
  unit: string;
  direction: string;
  weight: number;
  source: string;
  expected_periods: string[];
  supported_geography_types: string[];
  normalization: string;
  retail_rationale: string;
  notes: string | null;
  atlas_collection: string | null;
  atlas_item_datapoint: string | null;
  is_count: boolean;
  is_rate: boolean;
}

export interface Capability {
  capability_id: string;
  display_name: string;
  kind: string;
  status: "available" | "unavailable";
  description: string;
  required_data: string[];
  expected_provider: string | null;
  unavailable_because: string | null;
  produces: string | null;
  deterministic: boolean;
  is_available: boolean;
}

export interface CategoryInfo {
  id: string;
  label: string;
  description: string;
  guidance: string;
}

export interface StrategyProfileInfo {
  profile_id: string;
  display_name: string;
  description: string;
  when_to_use: string;
  category_weights: Record<string, number>;
}

export interface Catalog {
  categories: CategoryInfo[];
  metrics: MetricDefinition[];
  capabilities: Capability[];
  strategy_profiles: StrategyProfileInfo[];
  geographies: Geography[];
  data_classes: DataClassBadge[];
  presets: { label: string; slugs: string[] }[];
  objective_examples: { label: string; objective: string }[];
  llm_models: { id: string; caption: string }[];
  stage_steps: { stage: Stage; label: string }[];
  authority_labels: Record<TraceAuthority, string>;
  demo_token_scope_note: string;
}

export interface ServerSettings {
  atlas_token_present: boolean;
  is_demo_token: boolean;
  atlas_base_url: string;
  llm_enabled: boolean;
  llm_model: string;
  default_llm_model: string;
}

export interface Health {
  status: string;
  settings: ServerSettings;
  demo_token_scope_note: string;
}

// ------------------------------------------------------------------------------ plan

/**
 * A value together with where it came from. The generic mirrors `Attributed[T]` in
 * `models/strategy.py`; panels read `ProfileRow` instead, which is the same data
 * pre-flattened with a label.
 */
export interface Attributed<T> {
  value: T | null;
  provenance: Provenance;
  note: string | null;
}

export interface RetailStrategyProfile {
  retailer_type: Attributed<string>;
  store_format: Attributed<string>;
  target_customer_segments: Attributed<string[]>;
  strategic_priorities: Attributed<string[]>;
  secondary_priorities: Attributed<string[]>;
  hard_constraints: Attributed<string[]>;
  preferred_market_type: Attributed<string>;
  trade_area_definition: Attributed<string>;
  risk_tolerance: Attributed<string>;
  requested_dimensions: Attributed<string[]>;
  notes: string | null;
}

export interface ProfileRow {
  name: string;
  label: string;
  value: string | null;
  provenance: Provenance;
  note: string | null;
  is_known: boolean;
  is_assumption: boolean;
}

export interface ClarificationQuestion {
  question_id: string;
  question: string;
  missing_decision: string;
  why_it_matters: string;
  affects: string[];
  required: boolean;
  safe_default: string | null;
  answer: string | null;
}

export interface Assumption {
  subject: string;
  assumption: string;
  basis: string;
  provenance: Provenance;
  reversible_by: string | null;
}

export interface UnsupportedRequirement {
  requirement: string;
  why_unavailable: string;
  would_require: string;
  capability_id: string | null;
}

export interface RejectedField {
  field: string;
  offending_value: string;
  reason: string;
}

export interface PlanCheck {
  name: string;
  passed: boolean;
  detail: string;
  blocking: boolean;
}

export interface PlanValidationReport {
  status: "not_validated" | "passed" | "failed";
  checks: PlanCheck[];
  warnings: string[];
  disclosures: string[];
  passed: boolean;
  failures: PlanCheck[];
}

export interface PlanEdit {
  field: string;
  before: unknown;
  after: unknown;
  edited_at: string;
}

export interface ApprovalRecord {
  approved: boolean;
  approved_at: string | null;
  approved_by: string;
  edits: PlanEdit[];
  note: string | null;
}

export interface PlannerProvenance {
  planner: string;
  model: string | null;
  fell_back: boolean;
  fallback_reason: string | null;
  rejected_fields: RejectedField[];
  description: string;
  is_deterministic: boolean;
}

export interface Plan {
  plan_id: string;
  version: number;
  created_at: string;
  status: PlanStatus;
  original_request: string;
  sanitized_request: string;
  retail_strategy_profile: RetailStrategyProfile;
  candidate_geographies: Geography[];
  selected_metric_ids: string[];
  category_weights: Record<string, number>;
  metric_weight_overrides: Record<string, number>;
  assumptions: Assumption[];
  clarification_questions: ClarificationQuestion[];
  unsupported_requirements: UnsupportedRequirement[];
  excluded_requirements: string[];
  planner_rationale: string;
  expected_outputs: string[];
  evidence_requirements: string[];
  approval_record: ApprovalRecord;
  parent_plan_id: string | null;
  revision_summary: string | null;
  planner_provenance: PlannerProvenance;
  validation: PlanValidationReport;
  can_approve: boolean;
  can_execute: boolean;
  unanswered_required_question_ids: string[];
  profile_rows: ProfileRow[];
}

export interface PlanRevision {
  revision_id: string;
  parent_plan_id: string;
  parent_version: number;
  requested_change: string;
  changed_fields: string[];
  before_values: Record<string, unknown>;
  proposed_values: Record<string, unknown>;
  rationale: string;
  expected_effect: string;
  validation: PlanValidationReport;
  requires_confirmation: boolean;
  unsupported_parts: string[];
  created_at: string;
  is_actionable: boolean;
}

// ---------------------------------------------------------------------------- result

export interface EvidenceItem {
  evidence_id: string;
  metric: MetricDefinition;
  geography: Geography;
  atlas_datapoint: string;
  raw_value: number | null;
  period: string | null;
  source: string | null;
  reported_geography: string | null;
  margin_of_error: number | null;
  validation_status: ValidationStatus;
  validation_notes: string[];
  call_id: string | null;
  normalized_value: number | null;
  weighted_contribution: number | null;
  is_usable: boolean;
  geography_context_shifted: boolean;
  citation: string;
  data_class?: DataClassBadge;
}

export interface ExcludedMetric {
  metric_id: string;
  display_name: string;
  atlas_datapoint: string;
  reason: string;
  status: ValidationStatus;
  affected_geographies: string[];
}

export interface RawCall {
  call_id: string;
  method: string;
  url: string;
  request_body: Record<string, unknown> | null;
  response_body: Record<string, unknown> | null;
  status_code: number | null;
  elapsed_seconds: number | null;
  attempts: number;
  error: string | null;
  timestamp: string;
}

export interface EvidencePackage {
  package_id: string;
  geographies: Geography[];
  items: EvidenceItem[];
  excluded_metrics: ExcludedMetric[];
  raw_calls: RawCall[];
  created_at: string;
  completeness: number;
  usable_count: number;
  raw_call_count: number;
  data_class?: DataClassBadge;
}

export interface ScoreBreakdown {
  metric_id: string;
  display_name: string;
  category: string;
  evidence_id: string | null;
  raw_value: number | null;
  normalized_value: number | null;
  effective_weight: number;
  weighted_contribution: number | null;
  included: boolean;
  exclusion_reason: string | null;
}

export interface CategoryScore {
  category: string;
  score: number | null;
  category_weight: number;
  effective_category_weight: number;
  metrics_included: number;
  metrics_total: number;
  contributions: ScoreBreakdown[];
}

export interface RankedRegion {
  geography: Geography;
  rank: number;
  overall_score: number | null;
  category_scores: CategoryScore[];
  evidence_completeness: number;
  missing_metric_ids: string[];
  data_class?: DataClassBadge;
}

export interface Recommendation {
  leading_region: Geography | null;
  ranked_regions: RankedRegion[];
  narrative: string;
  caveats: string[];
  confidence_label: string;
  evidence_completeness: number;
  citations: string[];
  generated_by: string;
}

export interface Refusal {
  question: string;
  reason: string;
  unsupported_because: string[];
  required_inputs: string[];
  offered_alternative: string;
  supported_capabilities: string[];
}

export interface Limitation {
  title: string;
  detail: string;
  severity: LimitationSeverity;
}

export interface WeightAdjustment {
  category: string;
  metric_id: string;
  original_weight: number;
  reason: string;
}

export interface TraceEntry {
  step: string;
  detail: string;
  payload: Record<string, unknown> | null;
  authority: TraceAuthority;
  timestamp: string;
  authority_label?: string;
}

export interface AnalysisResult {
  plan: {
    question: string;
    geographies: Geography[];
    metric_ids: string[];
    category_weights: Record<string, number>;
    rationale: string;
    answerable: boolean;
    interpreted_by: string;
  } | null;
  evidence: EvidencePackage | null;
  recommendation: Recommendation | null;
  refusal: Refusal | null;
  limitations: Limitation[];
  weight_adjustments: WeightAdjustment[];
  trace: TraceEntry[];
  reproducibility_hash: string | null;
  proposal: Plan | null;
  refused: boolean;
  plan_version: number;
  authority_counts: Record<string, number>;
}

// ----------------------------------------------------------------------- comparison

export interface WeightChange {
  category: string;
  before: number;
  after: number;
  change: number;
}

export interface PlanDiff {
  from_plan_id: string;
  from_version: number;
  to_plan_id: string;
  to_version: number;
  weight_changes: WeightChange[];
  metrics_added: string[];
  metrics_removed: string[];
  regions_added: string[];
  regions_removed: string[];
  override_changes: string[];
  assumptions_added: string[];
  assumptions_removed: string[];
  revision_summary: string | null;
  is_empty: boolean;
  description: string[];
}

export interface RankDelta {
  slug: string;
  display_name: string;
  baseline_rank: number;
  comparison_rank: number;
  baseline_score: number | null;
  comparison_score: number | null;
  rank_change: number;
  score_change: number | null;
}

export interface ResultDiff {
  plan_diff: PlanDiff;
  deltas: RankDelta[];
  previous_hash: string | null;
  new_hash: string | null;
  leader_changed: boolean;
  previous_leader: string | null;
  new_leader: string | null;
  attribution: string[];
  evidence_changed: boolean;
}

// ---------------------------------------------------------------------- sensitivity

export interface RegionScore {
  slug: string;
  display_name: string;
  rank: number;
  overall_score: number | null;
}

export interface ProfileRanking {
  profile_id: string;
  display_name: string;
  reproducibility_hash: string;
  regions: RegionScore[];
  insufficient_evidence: boolean;
  insufficient_reason: string | null;
  winner: RegionScore | null;
}

export interface ProfileComparison {
  baseline: ProfileRanking;
  profiles: ProfileRanking[];
  deltas: Record<string, RankDelta[]>;
  stable: boolean;
  stability_note: string;
  winners: Record<string, string>;
}

export interface MetricInfluence {
  slug: string;
  display_name: string;
  metric_id: string;
  metric_name: string;
  category: string;
  normalized_value: number;
  contribution: number;
  share_of_score: number;
}

export interface FlipPoint {
  category: string;
  current_weight: number;
  flips: boolean;
  required_weight: number | null;
  direction: string | null;
  note: string;
}

export interface SensitivityReport {
  comparison: ProfileComparison;
  influences: MetricInfluence[];
  flip_points: FlipPoint[];
  resolution: number;
  assumption_sensitive: boolean;
}

// ------------------------------------------------------------------------ workflow

export interface ExecutedVersion {
  label: string;
  version: number;
  plan: Plan;
  result: AnalysisResult;
}

export interface WorkflowState {
  stage: Stage;
  notice: string | null;
  objective: string;
  geographies: string[];
  retailer_type: string | null;
  store_format: string | null;
  target_segments: string | null;
  can_approve: boolean;
  plan: Plan | null;
  planning_trace: TraceEntry[];
  refusal: Refusal | null;
  pending_revision: PlanRevision | null;
  versions: ExecutedVersion[];
  plan_diff: PlanDiff | null;
  result_diff: ResultDiff | null;
}

// ------------------------------------------------------------------------ assistant

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  generated_by?: string;
  refused?: boolean;
  notes?: string[];
}

export interface AssistantReply {
  text: string;
  generated_by: string;
  refused: boolean;
  notes: string[];
  proposes_revision: boolean;
  revision: PlanRevision | null;
}

export interface AssistantState {
  messages: ChatMessage[];
  context: {
    suggestions: string[];
    has_result: boolean;
    region_names: string[];
    fact_count: number;
  };
  llm_enabled: boolean;
}

export interface AssistantAskResponse {
  reply: AssistantReply;
  messages: ChatMessage[];
  state: WorkflowState;
}

export interface MarketDiscoveryArtifact {
  artifact_version: string;
  feature_set_version: string;
  model_version: string;
  seed: number;
  config_hash: string;
  k: number;
  min_population: number;
  n_counties_fit: number;
  n_counties_total: number;
  data_class: DataClassBadge;
  quality: {
    k: number;
    inertia: number;
    silhouette: number;
    selection_rule: string;
    candidate_scores: Record<string, number>;
  };
  provenance_notes: string[];
  feature_ids: string[];
  dropped_correlated: string[];
  features: MarketFeatureDef[];
}

export interface MarketFeatureDef {
  feature_id: string;
  display_name: string;
  acs_variables: string[];
  source_url: string;
  period: string;
  unit: string;
  transform: string;
  retail_rationale: string;
  missing_policy: string;
  caveats: string;
  higher_is: string;
}

export interface ArchetypeCluster {
  cluster_id: string;
  label: string;
  member_count: number;
  centroid_features: Record<string, number>;
  distinctive_high: string[];
  distinctive_low: string[];
  data_class: DataClassBadge;
}

export interface ArchetypeMarket {
  geoid: string;
  name: string;
  cluster_id: string;
  label: string;
  distance_to_centroid: number;
  pca_x: number;
  pca_y: number;
  lat: number;
  lon: number;
  population: number;
  in_clustering_universe: boolean;
  assignment_method: string;
  data_class: DataClassBadge;
  atlas_slugs: string[];
}

export interface ArchetypePeer {
  geoid: string;
  name: string;
  cluster_id: string;
  label: string;
  distance: number;
  population: number;
}

export interface MarketArchetypeProfile {
  market_id: string;
  geoid: string;
  name: string;
  cluster_id: string;
  label: string;
  profile: Record<string, number | null>;
  centroid_profile: Record<string, number>;
  nearest_markets: ArchetypePeer[];
  distance_to_centroid: number;
  pca_x: number;
  pca_y: number;
  quality: MarketDiscoveryArtifact["quality"];
  caveats: string[];
  data_class: DataClassBadge;
  assignment_method: string;
  atlas_slug: string | null;
}

export interface PcaPoint {
  geoid: string;
  name: string;
  cluster_id: string;
  label: string;
  pca_x: number;
  pca_y: number;
  population: number;
  in_clustering_universe: boolean;
  data_class: DataClassBadge;
}

export interface RetailerSimulationMeta {
  simulator_version: string;
  brand: string;
  benchmark_version: string;
  data_class: DataClassBadge;
  provenance_notes: string[];
}

export interface RetailerBenchmark {
  metric: string;
  value: number;
  unit: string;
  source_name: string;
  source_url: string | null;
  source_period: string | null;
  verification_state: "VERIFIED" | "DEMO_DEFAULT" | "UNVERIFIED_DISABLED";
  usage: string;
  data_class: DataClassBadge;
}

export interface RetailerBenchmarkCatalog {
  version: string;
  brand: string;
  provenance_notes: string[];
  benchmarks: RetailerBenchmark[];
  active_count: number;
  disabled_count: number;
  data_class: DataClassBadge;
}

export interface RetailerScenarioWire {
  store_count: number;
  format_mix: Record<string, number>;
  seed: number;
  sales_target_usd: number;
  margin_min_pct: number;
  margin_max_pct: number;
  data_class: DataClassBadge;
}

export interface SimulatedStore {
  store_id: string;
  name: string;
  format: string;
  city: string;
  state: string;
  lat: number;
  lon: number;
  sq_ft: number;
  annual_sales_usd: number;
  gross_margin_pct: number;
  host_geoid?: string | null;
  host_name?: string | null;
  host_cluster_id?: string | null;
  data_class: DataClassBadge;
}

export interface SimilarMarketProfile {
  cluster_id: string | null;
  cluster_label: string | null;
  focus_market_name: string | null;
  store_count: number;
  median_annual_sales_usd: number | null;
  iqr_annual_sales_usd: { q1: number; q3: number } | null;
  median_gross_margin_pct: number | null;
  store_ids: string[];
  note: string;
  data_class: DataClassBadge;
}

export interface MonthlyPerformance {
  month: number;
  label: string;
  total_sales_usd: number;
  store_count: number;
  data_class: DataClassBadge;
}

export interface SegmentShare {
  segment_id: string;
  label: string;
  share_pct: number;
  data_class: DataClassBadge;
}

export interface ReconciliationLine {
  metric: string;
  target: number;
  generated: number;
  tolerance_pct: number;
  passed: boolean;
  note: string;
  data_class: DataClassBadge;
}

export interface RetailerSimulationArtifact {
  brand: string;
  simulator_version: string;
  seed: number;
  scenario: RetailerScenarioWire;
  stores: SimulatedStore[];
  monthly: MonthlyPerformance[];
  segments: SegmentShare[];
  reconciliation: ReconciliationLine[];
  assumptions: string[];
  provenance_notes: string[];
  data_class: DataClassBadge;
  reconciliation_passed: boolean;
  similar_market_profile?: SimilarMarketProfile | null;
}

export interface RetailerSimulationRunRequest {
  store_count?: number;
  format_mix?: Record<string, number>;
  seed?: number;
  sales_target_usd?: number;
  focus_market_id?: string | null;
  margin_min_pct?: number;
  margin_max_pct?: number;
}

export interface FeatureContribution {
  feature_id: string;
  display_name: string;
  candidate_value: number | null;
  store_value: number | null;
  weight: number;
  signed_contribution: number;
}

export interface AnalogPerformanceSummary {
  median_annual_sales_usd: number;
  iqr_annual_sales_usd: [number, number];
  median_gross_margin_pct: number;
  iqr_gross_margin_pct: [number, number];
  data_class: DataClassBadge;
}

export interface AnalogMatch {
  store_id: string;
  store_name: string;
  format: string;
  host_geoid: string;
  host_name: string;
  similarity: number;
  distance: number;
  contributions: FeatureContribution[];
  mismatches: string[];
  performance_summary: AnalogPerformanceSummary | null;
  data_class: DataClassBadge;
}

export interface AnalogAggregateRange {
  min_similarity: number;
  max_similarity: number;
  median_similarity: number;
  data_class: DataClassBadge;
}

export interface AnalogSearchResult {
  candidate_market_id: string;
  candidate_geoid: string;
  candidate_name: string;
  candidate_cluster_id: string;
  matches: AnalogMatch[];
  aggregate_range: AnalogAggregateRange | null;
  analogy_strength: "strong" | "moderate" | "weak" | "insufficient";
  warnings: string[];
  feature_ids: string[];
  matcher_version: string;
  feature_set_version: string;
  context_pack: string[];
  data_class: DataClassBadge;
  data_class_notes?: {
    candidate_profile: DataClassBadge;
    match_features: DataClassBadge;
    performance_summary: DataClassBadge;
  };
}

export interface AnalogMatchingMeta {
  matcher_version: string;
  feature_set_version: string;
  matching_features: Array<Record<string, unknown>>;
  thresholds: {
    min_strong_similarity: number;
    min_moderate_similarity: number;
    min_peer_count: number;
    default_top_k: number;
    max_top_k: number;
  };
  data_class: DataClassBadge;
  provenance_notes: string[];
}

export interface AnalogMatchingSearchRequest {
  market_id: string;
  top_k?: number;
  preferred_format?: string | null;
  scenario?: RetailerSimulationRunRequest;
}
