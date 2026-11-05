import { useEffect, useState } from 'react'

export type Box = { id: string; class_name: string; xyxy: number[]; confidence?: number }
export type ImageRecord = { id: string; dataset_id: string; filename: string; pool: string; status: string; source_group: string; confirmed_group: string | null; assigned_split: string | null; confirmed: number | null; independent: number | null; evidence: string | null; image_url: string; issues: { severity: string; code: string; message: string }[]; boxes: Box[]; width: number; height: number }
export type Dataset = { id: string; name: string; version: string; source: string; pool: string; created_at: string; state: string; images: number; approved: number; classes: Record<string, string>; summary: { source_boxes?: number; issues?: number; class_distribution?: Record<string, number> } }
export type Model = { id: string; name: string; architecture: string; checkpoint: string; sha256: string; bytes: number; created_at: string; pretrained: boolean; active: boolean; dataset_id: string | null; metrics: Record<string, number | string | null>; configuration: Record<string, unknown> }
export type Version = { id: string; name: string; created_at: string; state: string; summary: { ready: boolean; counts: Record<string, number>; independent_test: boolean; warnings: string[] }; manifest: { image_id: string; split: string; pool: string }[] }
export type MetricRow = Record<string, number>
export type Job = { id: string; kind: string; status: string; stage: string; progress: number | null; created_at: string; updated_at: string; error: string | null; payload: Record<string, unknown>; result: Record<string, unknown>; metrics?: MetricRow[]; cancel_requested: number; resumable?: boolean; elapsed_seconds?: number; process_memory_bytes?: number }
export type Hardware = { cpu_count: number; ram_available: number; ram_total: number; ram_used_percent: number; disk_free: number; devices: string[]; gpus: {name: string}[]; python: string; packages: Record<string, string>; cpu_percent: number }
export type Overview = { active_model: Model | null; model_state: {state: string; ready: boolean; reason: string}; datasets: number; images: number; approved_objects: number; source_annotated_objects: number; review_status: Record<string, number>; pending_reviews: number; quality_issue_count: number; quality_issues: {code: string; severity: string; message: string; filename: string; image_id: string}[]; jobs: Job[]; hardware: Hardware; inference_average_ms: number | null; inference_sample_count: number; versions: number }
export type Inference = { job_id: string; kind: string; status: string; created_at: number; stats: {object_count?: number; frame_level_detection_instances?: number; average_model_call_ms?: number; timeline?: {frame: number; seconds: number; count: number}[]}; result_url: string; download_url: string; model_sha256?: string }
export type Evaluation = { id: string; model_id: string; version_id: string; created_at: string; kind: string; result: {precision: number; recall: number; map50: number; map50_95: number; images: number; scope: string; gallery: {image_id: string; image: string; categories: string[]; tp: number; fp: number; fn: number}[]} }
export type Check = { ready: boolean; errors: string[]; warnings: string[]; counts?: Record<string, number>; duration_note?: string }
export type Notice = (text: string, error?: boolean) => void

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/platform${path}`, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.errors?.join('\n') || JSON.stringify(detail || body))
  }
  return body as T
}
export const post = <T>(path: string, body: unknown = {}) => api<T>(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
export function useResource<T>(path: string, initial: T, tick: number, interval = 0) {
  const [data, setData] = useState(initial)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    const load = () => api<T>(path, {signal: controller.signal}).then(value => { setData(value); setError('') }).catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
    void load()
    const timer = interval ? window.setInterval(() => void load(), interval) : undefined
    return () => { controller.abort(); window.clearInterval(timer) }
  }, [path, tick, interval])
  return {data, error, setData}
}
export const bytes = (value: number) => value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : `${(value / 1024 ** 2).toFixed(1)} MB`
export const percent = (value: unknown) => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—'
export const date = (value: string | number) => new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString()
export const human = (value: string) => value.replaceAll('_', ' ')
export const message = (e: unknown) => e instanceof Error ? e.message : 'Request failed'
