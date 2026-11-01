export type AgentName = "query_handler" | "research" | "strategist" | "blog" | "linkedin" | "image";

export interface TraceEntry {
  agent: string;
  status: "ok" | "error" | "skipped";
  detail: string;
  provider?: string | null;
  duration_s?: number | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  agents?: string[];
  ts?: number;
}

export interface Quality {
  content_type: string;
  score: number;
  grade: string;
  dimensions: Record<string, number>;
  suggestions: string[];
  details?: Record<string, unknown>;
}

export interface Credibility {
  domain: string;
  score: number;
  tier: "high" | "medium" | "low";
  reasons: string[];
}

export interface Source {
  title: string;
  url: string;
  snippet?: string;
  credibility?: Credibility;
}

export type ClaimStatus = "supported" | "weak" | "unverified" | "uncited" | "invalid_citation";

export interface ClaimCheck {
  claim: string;
  kind: "finding" | "statistic";
  citations: number[];
  status: ClaimStatus;
  note: string;
}

export interface Verification {
  claims: ClaimCheck[];
  summary: {
    avg_source_credibility: number;
    high_credibility_sources: number;
    low_credibility_sources: number;
    claims_checked: number;
    supported: number;
    needs_review: number;
  };
}

export interface Research {
  topic: string;
  summary: string;
  key_findings: string[];
  statistics: string[];
  trends: string[];
  audience_insights: string[];
  content_angles: string[];
  keywords: string[];
  sources: Source[];
  search_providers: string[];
  analysis_provider: string;
  offline_demo?: boolean;
  verification?: Verification;
  quality: Quality;
}

export interface SEO {
  keyword_density: number;
  word_count: number;
  meta_length: number;
  h1_count: number;
  h2_count: number;
  readability: { flesch_reading_ease: number; flesch_kincaid_grade: number };
  internal_link_suggestions: { anchor_text: string; suggested_url: string; reason: string }[];
  issues: string[];
}

export interface Blog {
  title: string;
  slug: string;
  markdown: string;
  meta_description: string;
  primary_keyword: string;
  secondary_keywords: string[];
  template: string;
  word_count: number;
  seo: SEO;
  quality: Quality;
  provider: string;
  revision: number;
  edited_by_human?: boolean;
}

export interface LinkedInPost {
  text: string;
  hashtags: string[];
  template: string;
  char_count: number;
  quality: Quality;
  provider: string;
  revision: number;
}

export interface ImageAsset {
  src?: string;
  url?: string;
  provider: string;
  model: string;
  width: number;
  height: number;
  format?: string;
  enhanced_prompt: string;
  alt_text: string;
  attempts?: { provider: string; ok: boolean; error?: string; latency_s?: number }[];
  quality: Quality;
}

export interface BrandVoice {
  name: string;
  tone: string;
  audience: string;
  style_rules: string[];
  banned_phrases: string[];
  preferred_terms: Record<string, string>;
}

export interface ConversationState {
  thread_id: string;
  messages: ChatMessage[];
  topic?: string;
  plan?: string[];
  trace?: TraceEntry[];
  errors?: { agent: string; error: string }[];
  research?: Research | null;
  strategy_report?: string | null;
  content_brief?: Record<string, unknown> | null;
  blog?: Blog | null;
  blog_series: Blog[];
  linkedin?: LinkedInPost | null;
  image?: ImageAsset | null;
  brand_voice?: BrandVoice | null;
}

export interface AppConfig {
  brand_voice: BrandVoice;
  env: string;
  email_delivery: "email" | "console";
}

export interface User {
  id: number;
  email: string;
  name: string;
  is_admin: boolean;
  created_at?: number;
}

export interface CodeSent {
  sent: boolean;
  email: string;
  purpose: "login" | "signup";
  delivery: "email" | "console";
  expires_in: number;
  resend_after: number;
  dev_code?: string;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  created_at: number;
  updated_at: number;
}

export type LLMProvider = "openai" | "anthropic" | "gemini";
export type ResearchProvider = "serpapi" | "perplexity" | "tavily";

export interface ServerSettings {
  demo_mode: boolean | null;
  llm_primary: LLMProvider | null;
  research_primary: ResearchProvider | null;
  quality_threshold: number | null;
}

export interface Usage {
  calls: number;
  failures: number;
  total_cost_usd: number;
  total_tokens: number;
  cache: { entries: number; hits: number; misses: number };
  providers: Record<string, string[]>;
  offline: boolean;
}

export interface AdminOverview {
  settings: ServerSettings;
  effective: { demo_mode: boolean; llm_primary: string | null; research_primary: string | null; quality_threshold: number };
  detected_keys: string[];
  key_providers: string[];
  fallback_chains: Record<string, string[]>;
  usage: Usage;
  tracing: boolean;
  email_delivery: "email" | "console";
  env: string;
  users: { email: string; name: string; created_at: number; last_login: number | null; conversations: number; is_admin: boolean }[];
  totals: { users: number; conversations: number };
}

export type StreamEvent =
  | { event: "start"; data: { thread_id: string } }
  | { event: "node"; data: { node: string; trace: TraceEntry | null; plan?: string[]; topic?: string } }
  | { event: "done"; data: ConversationState }
  | { event: "error"; data: { message: string } };
