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

export interface Source {
  title: string;
  url: string;
  snippet?: string;
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
  detected_keys: string[];
  default_demo_mode: boolean;
  quality_threshold: number;
  fallback_chains: Record<string, string[]>;
  brand_voice: BrandVoice;
  key_providers: string[];
  env: string;
}

export interface ClientSettings {
  demo_mode: boolean;
  api_keys: Record<string, string>;
  llm_primary: "openai" | "anthropic" | "gemini";
  research_primary: "serpapi" | "perplexity" | "tavily";
  quality_threshold: number;
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

export type StreamEvent =
  | { event: "start"; data: { thread_id: string; providers: Record<string, string[]>; offline: boolean } }
  | { event: "node"; data: { node: string; trace: TraceEntry | null; plan?: string[]; topic?: string } }
  | { event: "done"; data: ConversationState }
  | { event: "error"; data: { message: string } };
