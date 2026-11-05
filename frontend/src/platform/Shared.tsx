import { Activity, Download, FileText, Square, RotateCcw } from 'lucide-react'
import { type Job, type MetricRow, type Notice, useResource, post, message, human, date, bytes } from './api'

export function Badge({value}: {value: string}) { return <span className={`nv-badge ${value}`}>{human(value)}</span> }
export function Empty({title, children}: {title: string; children?: React.ReactNode}) { return <div className="nv-empty"><Activity size={28}/><h3>{title}</h3><p>{children}</p></div> }
export function Card({title, aside, children, className = ''}: {title?: string; aside?: React.ReactNode; children: React.ReactNode; className?: string}) { return <section className={`nv-card ${className}`}>{title && <div className="nv-card-heading"><h2>{title}</h2>{aside}</div>}{children}</section> }
export function Plot({rows, series, title}: {rows: MetricRow[]; series: [string, string][]; title: string}) {
  if (!rows.length) return <Empty title="No recorded epochs yet">The chart fills from the experiment’s actual results.csv.</Empty>
  const palette = ['#2563eb', '#0e9f8b', '#8b5cf6', '#e08b12']
  const values = rows.flatMap(r => series.map(([key]) => r[key]).filter(Number.isFinite))
  if (!values.length) return <Empty title="Metrics unavailable">This experiment has not written the selected metrics.</Empty>
  const max = Math.max(...values), min = Math.min(0, ...values), range = Math.max(max-min, .01)
  return <div className="nv-chart"><svg viewBox="0 0 760 250" role="img" aria-label={title}>
    {[0,1,2,3,4].map(n => <g key={n}><line x1="45" y1={20+n*48} x2="735" y2={20+n*48} stroke="#dce6f3"/><text x="3" y={24+n*48} fill="#6b7d95" fontSize="11">{(max-n*range/4).toFixed(2)}</text></g>)}
    {series.map(([key], i) => <polyline key={key} fill="none" stroke={palette[i%palette.length]} strokeWidth="2.5" points={rows.map((r,n) => Number.isFinite(r[key]) ? `${45+n*690/Math.max(rows.length-1,1)},${20+(max-r[key])*192/range}` : '').join(' ')}/>)}
    <text x="45" y="240" fill="#6b7d95" fontSize="11">Epoch {rows[0].epoch ?? 1}</text><text x="680" y="240" fill="#6b7d95" fontSize="11">{rows.at(-1)?.epoch ?? rows.length}</text>
  </svg><div className="nv-chart-legend">{series.map(([key,label],i) => <span key={key}><i style={{background:palette[i%palette.length]}}/>{label}</span>)}</div></div>
}

export function JobMonitor({id, notify}: {id: string; notify: Notice}) {
  const {data: job, error} = useResource<Job | null>(`/jobs/${id}`, null, 0, 2000)
  const {data: logs} = useResource<{text: string}>(`/jobs/${id}/logs`, {text:''}, 0, 2500)
  const action = async (suffix: string) => { try { await post(`/jobs/${id}/${suffix}`); notify(`${human(suffix)} requested`) } catch(e) { notify(message(e), true) } }
  if (error) return <p role="alert" className="nv-error">{error}</p>
  if (!job) return <p>Loading job…</p>
  return <Card title={`${human(job.kind)} job`} aside={<Badge value={job.status}/>}>
    <div className="nv-job-meta"><span>{job.stage}</span><span>{date(job.created_at)}</span></div>
    {job.progress !== null && <><progress max="100" value={job.progress}/><small>{job.progress.toFixed(1)}% of recorded work</small></>}
    {job.error && <p className="nv-error" role="alert">{job.error}</p>}
    <p className="nv-help">Elapsed {Math.round(job.elapsed_seconds||0)} seconds{job.process_memory_bytes?` · Worker memory ${bytes(job.process_memory_bytes)}`:''}</p>
    <div className="nv-actions">{['running','queued'].includes(job.status) && <button className="nv-secondary" onClick={() => void action('stop')}><Square size={14}/>Request stop</button>}{['failed','stopped','interrupted'].includes(job.status) && (job.kind!=='train'||job.resumable) && <button className="nv-secondary" onClick={() => void action(job.kind === 'train' ? 'resume' : 'retry')}><RotateCcw size={14}/>{job.kind === 'train' ? 'Resume preserved checkpoint' : 'Retry safe job'}</button>}</div>
    {!!job.metrics?.length && <div className="nv-two"><Plot rows={job.metrics} title="Validation metrics by epoch" series={[["metrics/mAP50(B)","mAP50"],["metrics/mAP50-95(B)","mAP50:95"],["metrics/precision(B)","Precision"],["metrics/recall(B)","Recall"]]}/><Plot rows={job.metrics} title="Training and validation box loss" series={[["train/box_loss","Train box loss"],["val/box_loss","Validation box loss"]]}/></div>}
    <details open><summary><FileText size={15}/> Worker log</summary><pre className="nv-log">{logs.text || 'Waiting for the worker to write logs…'}</pre></details>
  </Card>
}

export function JobsTable({jobs, onSelect}: {jobs: Job[]; onSelect: (id: string) => void}) {
  return jobs.length ? <div className="nv-table-wrap"><table><thead><tr><th>Job</th><th>Status</th><th>Stage</th><th>Created</th><th/></tr></thead><tbody>{jobs.map(job => <tr key={job.id}><td><strong>{human(job.kind)}</strong><small>{job.id.slice(0,12)}</small></td><td><Badge value={job.status}/></td><td>{job.stage}</td><td>{date(job.created_at)}</td><td><button className="nv-text" onClick={() => onSelect(job.id)}>Inspect →</button></td></tr>)}</tbody></table></div> : <Empty title="No jobs recorded">New imports, preparation, training, and evaluation jobs appear here.</Empty>
}

export function EvidenceLinks() {
  return <div className="nv-actions"><a className="nv-secondary" href="/api/platform/evidence/task01" download><Download size={14}/>Task 1 audit</a><a className="nv-secondary" href="/api/platform/evidence/task02" download>Task 2 error analysis</a><a className="nv-secondary" href="/api/platform/evidence/task03" download>Annotation validation</a></div>
}

export async function requestReport(kind: string, notify: Notice) { try { const result = await post<Job>('/reports',{kind}); notify(`Report job ${result.id.slice(0,8)} queued. Download it from Reports when complete.`) } catch(e) { notify(message(e), true) } }
