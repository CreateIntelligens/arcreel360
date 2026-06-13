/** 費用明細：貨幣 → 金額 對映 */
export type CostBreakdown = Record<string, number>;

/** 按型別拆分的費用 */
export interface CostByType {
  image?: CostBreakdown;
  video?: CostBreakdown;
  character_and_clue?: CostBreakdown;
}

/** 單個 segment 的費用 */
export interface SegmentCost {
  segment_id: string;
  duration_seconds: number;
  estimate: { image: CostBreakdown; video: CostBreakdown };
  actual: { image: CostBreakdown; video: CostBreakdown };
}

/** 單集費用 */
export interface EpisodeCost {
  episode: number;
  title: string;
  segments: SegmentCost[];
  totals: { estimate: CostByType; actual: CostByType };
}

/** 模型資訊 */
export interface ModelInfo {
  provider: string;
  model: string;
}

/** 費用估算 API 響應 */
export interface CostEstimateResponse {
  project_name: string;
  models: { image: ModelInfo; video: ModelInfo };
  episodes: EpisodeCost[];
  project_totals: { estimate: CostByType; actual: CostByType };
}
