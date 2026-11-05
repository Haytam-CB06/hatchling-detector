import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowDownToLine, CheckCircle2, CircleHelp, Clock3, CloudUpload, Crosshair, FileVideo2, Image as ImageIcon, RotateCcw, ScanSearch, Settings2, ShieldCheck, X } from 'lucide-react'

type ModelInfo = {
  state: 'loading' | 'ready' | 'unavailable'
  ready: boolean
  reason: string
  model_name: string
  architecture: string | null
  classes: Record<string, string>
  device: string
  image_size: number
}

type Detection = { class_id: number; class_name: string; confidence: number; box_xyxy: number[] }
type Job = {
  job_id: string
  kind: 'image' | 'video'
  status: 'queued' | 'processing' | 'completed' | 'failed'
  stage: 'queued' | 'inference' | 'encoding' | 'completed' | 'failed'
  processed_frames: number
  estimated_total_frames: number | null
  progress_percent: number | null
  detections: Detection[] | null
  stats: Record<string, number | string | string[]> | null
  error: string | null
  result_url: string | null
  download_url: string | null
  source_metadata?: { width: number; height: number; fps: number; duration_seconds: number | null }
}

const imageTypes = ['image/jpeg', 'image/png', 'image/webp']
const videoExtensions = ['mp4', 'mov', 'avi']

function prettySize(size: number) {
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(0)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function responseJson(response: Response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`)
  return body
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><div className="metric-value">{value}</div><div className="metric-label">{label}</div></div>
}

export default function App() {
  const [model, setModel] = useState<ModelInfo | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [mediaKind, setMediaKind] = useState<'image' | 'video' | null>(null)
  const [dimensions, setDimensions] = useState('—')
  const [duration, setDuration] = useState<string | null>(null)
  const [videoPreviewError, setVideoPreviewError] = useState(false)
  const [confidence, setConfidence] = useState(0.25)
  const [iou, setIou] = useState(0.45)
  const [job, setJob] = useState<Job | null>(null)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const pollTimer = useRef<number | null>(null)
  const runToken = useRef(0)

  useEffect(() => {
    let active = true
    const refresh = () => fetch('/api/model/info').then(responseJson).then((info: ModelInfo) => {
      if (active) setModel(info)
    }).catch(() => {
      if (active) setModel({ state: 'unavailable', ready: false, reason: 'Backend is offline', model_name: 'best.pt', architecture: null, classes: {}, device: '—', image_size: 640 })
    })
    refresh()
    const timer = window.setInterval(refresh, 4000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
    if (pollTimer.current) window.clearInterval(pollTimer.current)
  }, [preview])

  const clearPolling = () => {
    if (pollTimer.current) window.clearInterval(pollTimer.current)
    pollTimer.current = null
  }

  const selectFile = useCallback((next: File | null) => {
    clearPolling()
    runToken.current++
    setWorking(false)
    setJob(null)
    setError(null)
    setDimensions('Reading media…')
    setDuration(null)
    setVideoPreviewError(false)
    if (!next) { setFile(null); setMediaKind(null); setPreview(null); return }
    const ext = next.name.split('.').pop()?.toLowerCase() || ''
    const kind = imageTypes.includes(next.type) || ['jpg', 'jpeg', 'png', 'webp'].includes(ext) ? 'image' : videoExtensions.includes(ext) ? 'video' : null
    if (!kind) { setError('Choose a JPG, PNG, WEBP, MP4, MOV, or AVI file.'); setFile(null); setPreview(null); setMediaKind(null); return }
    const limit = kind === 'image' ? 20 : 150
    if (next.size > limit * 1024 * 1024) { setError(`This ${kind} exceeds the ${limit} MB limit.`); setFile(null); setPreview(null); setMediaKind(null); return }
    setFile(next)
    setMediaKind(kind)
    setPreview(URL.createObjectURL(next))
  }, [])

  const reset = () => {
    selectFile(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  const beginPolling = (jobId: string, token: number) => {
    clearPolling()
    const poll = async () => {
      try {
        const result = await responseJson(await fetch(`/api/jobs/${jobId}`)) as Job
        if (runToken.current !== token) return
        setJob(result)
        if (result.status === 'completed' || result.status === 'failed') {
          clearPolling(); setWorking(false)
          if (result.status === 'failed') setError(result.error || 'Video processing failed.')
        }
      } catch (err) {
        if (runToken.current === token) { clearPolling(); setWorking(false); setError(err instanceof Error ? err.message : 'Could not read job progress.') }
      }
    }
    pollTimer.current = window.setInterval(poll, 900)
    void poll()
  }

  const runDetection = async () => {
    if (!file || !mediaKind || !model?.ready || working) return
    const token = ++runToken.current
    setWorking(true); setError(null); setJob(null)
    const form = new FormData()
    form.set('file', file)
    form.set('confidence', String(confidence))
    form.set('iou', String(iou))
    try {
      const response = await fetch(`/api/detect/${mediaKind}`, { method: 'POST', body: form })
      const result = await responseJson(response) as Job
      if (runToken.current !== token) return
      setJob(result)
      if (mediaKind === 'video') beginPolling(result.job_id, token)
      else setWorking(false)
    } catch (err) {
      if (runToken.current === token) { setWorking(false); setError(err instanceof Error ? err.message : 'Detection failed.') }
    }
  }

  const completed = job?.status === 'completed' && job.result_url
  const noDetections = Boolean(completed) && (mediaKind === 'image'
    ? (job?.detections?.length ?? 0) === 0
    : mediaKind === 'video' && Number(job?.stats?.frame_level_detection_instances ?? 0) === 0)
  const statusLabel = model?.state === 'ready' ? 'Model Ready' : model?.state === 'loading' ? 'Model Loading' : 'Model Unavailable'
  const statusClass = model?.state === 'ready' ? 'ready' : model?.state === 'loading' ? 'loading' : 'unavailable'

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><Crosshair size={23} strokeWidth={2.3} /></div><div><div className="brand-name">NAZAR <span>VISION</span></div><div className="brand-sub">AI DETECTION STUDIO</div></div></div>
      <div style={{display:'flex',alignItems:'center',gap:18}}><a href="/review" style={{color:'#8fe4be',fontSize:12,fontWeight:700}}>Annotation review →</a><div className={`status-pill ${statusClass}`}><span className="status-dot" />{statusLabel}</div></div>
    </header>

    <main className="main-content">
      <section className="hero">
        <div className="eyebrow"><span className="eyebrow-line" /> COMPUTER VISION WORKSPACE <span className="eyebrow-line" /></div>
        <h1>See what the model <em>sees.</em></h1>
        <p>Upload a photo or video and test the trained sea turtle hatchling detector. Review the original and annotated result, inspect real predictions, and download your output.</p>
      </section>

      <div className="workspace-grid">
        <aside className="sidebar">
          <div className="panel upload-panel">
            <div className="panel-heading"><div className="step-number">01</div><div><h2>Input media</h2><p>Choose a file to analyze</p></div></div>
            <input ref={fileInput} id="media-input" type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.avi,image/jpeg,image/png,image/webp,video/mp4" hidden onChange={event => selectFile(event.target.files?.[0] || null)} />
            <div className={`dropzone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`} role="button" tabIndex={0} aria-label="Upload image or video" onClick={() => fileInput.current?.click()} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') fileInput.current?.click() }} onDragEnter={event => { event.preventDefault(); setDragging(true) }} onDragOver={event => event.preventDefault()} onDragLeave={event => { event.preventDefault(); setDragging(false) }} onDrop={event => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files?.[0] || null) }}>
              <div className="upload-icon"><CloudUpload size={28} /></div>
              <strong>{file ? 'Change media file' : 'Drop your media here'}</strong>
              <span>or click to browse your files</span>
              <div className="format-chips"><b>JPG</b><b>PNG</b><b>WEBP</b><b>MP4</b><b>MOV</b><b>AVI</b></div>
            </div>
            {file && <div className="file-card"><div className="file-symbol">{mediaKind === 'image' ? <ImageIcon size={19} /> : <FileVideo2 size={19} />}</div><div className="file-main"><strong title={file.name}>{file.name}</strong><span>{mediaKind?.toUpperCase()} · {prettySize(file.size)} · {dimensions}{duration ? ` · ${duration}` : ''}</span></div><button className="icon-button" title="Remove file" onClick={reset}><X size={17} /></button></div>}
          </div>

          <div className="panel controls-panel">
            <div className="panel-heading"><div className="step-number">02</div><div><h2>Detection settings</h2><p>Fine-tune model sensitivity</p></div></div>
            <div className="control-row"><label htmlFor="confidence">Confidence threshold <CircleHelp size={14} /></label><span>{Math.round(confidence * 100)}%</span></div>
            <input id="confidence" type="range" min="0.05" max="0.95" step="0.01" value={confidence} onChange={event => setConfidence(Number(event.target.value))} />
            <div className="range-labels"><span>More detections</span><span>Fewer false alarms</span></div>
            <div className="control-row iou-row"><label htmlFor="iou">IoU threshold <CircleHelp size={14} /></label><span>{iou.toFixed(2)}</span></div>
            <input id="iou" type="range" min="0.05" max="0.95" step="0.01" value={iou} onChange={event => setIou(Number(event.target.value))} />
            <div className="range-labels"><span>Stricter suppression</span><span>More overlapping boxes</span></div>
            <div className="model-mini"><Settings2 size={17} /><div><strong>{model?.model_name || 'Checking model…'}</strong><span>{model?.architecture || model?.reason || 'Connecting to backend…'} · {model?.device || '—'}</span></div></div>
            <button className="run-button" onClick={runDetection} disabled={!file || !model?.ready || working}><ScanSearch size={19} />{working ? 'Detection in progress…' : 'Run Detection'}<span>→</span></button>
            <button className="reset-button" onClick={reset}><RotateCcw size={15} /> Reset workspace</button>
          </div>
          <div className="sidebar-note"><ShieldCheck size={16} /><span>Real inference with the trained {model?.classes?.['0'] || 'hatchling'} model. Predictions may contain errors; review every result.</span></div>
        </aside>

        <section className="results-area">
          <div className="results-head"><div><div className="small-label">ANALYSIS WORKSPACE</div><h2>Detection preview</h2></div><div className="result-state"><span className={completed ? 'green-dot' : 'muted-dot'} />{noDetections ? 'No hatchlings detected' : completed ? 'Analysis complete' : working ? 'Processing' : 'Awaiting media'}</div></div>
          {error && <div className="error-banner" role="alert"><strong>Something needs attention</strong><span>{error}</span><button onClick={() => setError(null)} aria-label="Dismiss error"><X size={15} /></button></div>}
          <div className="preview-grid">
            <div className="preview-card"><div className="preview-title"><div><span className="preview-index">A</span> Original media</div><span className="preview-tag">INPUT</span></div><div className="media-frame">
              {preview && mediaKind === 'image' ? <img src={preview} alt="Original uploaded media" onLoad={event => { const target = event.currentTarget; setDimensions(`${target.naturalWidth} × ${target.naturalHeight}`) }} /> : preview && mediaKind === 'video' ? videoPreviewError ? <div className="empty-preview"><div className="empty-icon"><FileVideo2 size={29} /></div><strong>Original preview unavailable</strong><span>This browser cannot play the source codec. Detection can still process it.</span></div> : <video src={preview} controls playsInline preload="metadata" onLoadedMetadata={event => { const target = event.currentTarget; setDimensions(`${target.videoWidth} × ${target.videoHeight}`); if (Number.isFinite(target.duration)) setDuration(`${target.duration.toFixed(1)}s`) }} onError={() => { setVideoPreviewError(true); setDimensions('Codec preview unavailable') }} /> : <div className="empty-preview"><div className="empty-icon"><ImageIcon size={29} /></div><strong>No media uploaded yet</strong><span>Your original image or video will appear here</span></div>}
            </div></div>
            <div className="preview-card"><div className="preview-title"><div><span className="preview-index accent">B</span> Detection result</div><span className="preview-tag accent-tag">AI OUTPUT</span></div><div className="media-frame">
              {completed && mediaKind === 'image' ? <div className="result-media-wrap"><img key={job.job_id} src={job.result_url!} alt={noDetections ? 'Analyzed image with no hatchling boxes' : 'Annotated hatchling detection result'} />{noDetections && <div className="no-detections-overlay" role="status">No hatchlings detected</div>}</div> : completed && mediaKind === 'video' ? <div className="result-media-wrap"><video key={job.job_id} src={job.result_url!} controls playsInline preload="metadata" />{noDetections && <div className="no-detections-overlay" role="status">No hatchlings detected</div>}</div> : <div className="empty-preview"><div className="empty-icon result-icon">{working ? <Activity size={29} /> : <Crosshair size={29} />}</div><strong>{working ? 'Analyzing your media' : 'Ready for detection'}</strong><span>{working ? 'The model is processing real frames' : 'Your annotated result will appear here'}</span></div>}
            </div></div>
          </div>
          {working && mediaKind === 'video' && job && <div className="progress-panel"><div className="progress-top"><span>{job.stage === 'encoding' ? 'Encoding browser-compatible MP4' : 'Processing video frames'}</span><strong>{job.processed_frames}{job.estimated_total_frames ? ` / ${job.estimated_total_frames}` : ''}{job.progress_percent !== null ? ` · ${job.progress_percent}% frames` : ''}</strong></div><div className="progress-track"><div style={{ width: `${job.progress_percent ?? 0}%` }} /></div><p>{job.stage === 'encoding' ? 'All frames are processed. FFmpeg is assembling the downloadable video.' : 'Progress reflects frames actually processed by the backend.'}</p></div>}
          {completed && <div className={`results-footer ${noDetections ? 'no-match-footer' : ''}`}><div className="result-confirm"><CheckCircle2 size={19} /><div><strong>{noDetections ? 'No hatchlings detected' : 'Detection complete'}</strong><span>{noDetections ? 'The model returned no boxes at this threshold. If a hatchling is visible, lower confidence and run again.' : 'Bounding boxes and confidence labels are embedded in the output.'}</span></div></div><a className="download-button" href={job.download_url!}><ArrowDownToLine size={17} /> Download {mediaKind === 'image' ? 'image' : 'video'}</a></div>}
          <div className="stats-panel"><div className="stats-heading"><div><div className="small-label">MODEL OUTPUT</div><h3>Detection statistics</h3></div><Activity size={18} /></div>
            {completed && job.stats ? mediaKind === 'image' ? <><div className="metric-grid"><Metric label="Detected objects" value={Number(job.stats.object_count)} /><Metric label="Model call" value={`${job.stats.model_call_ms} ms`} /><Metric label="Resolution" value={`${job.stats.width} × ${job.stats.height}`} /></div><div className="detection-list"><strong>Detections</strong>{job.detections?.length ? job.detections.map((d, i) => <div className="detection-item" key={i}><span className="class-dot" /><span>{d.class_name}</span><b>{(d.confidence * 100).toFixed(1)}%</b></div>) : <p>No hatchlings detected at the selected confidence threshold.</p>}</div></> : <><div className="metric-grid video-metrics"><Metric label="Frames processed" value={Number(job.stats.frames_processed)} /><Metric label="Frame-level detections" value={Number(job.stats.frame_level_detection_instances)} /><Metric label="Frames with boxes" value={Number(job.stats.frames_with_detections)} /><Metric label="Avg. model call" value={`${job.stats.average_model_call_ms} ms`} /><Metric label="Total processing" value={`${job.stats.total_processing_seconds} s`} /><Metric label="Video duration" value={`${job.stats.duration_seconds} s`} /></div><p className="stats-note">{noDetections ? 'No hatchlings detected at the selected confidence threshold. ' : 'Frame-level detections count boxes across frames, not unique animals. '}{String(job.stats.audio)}.</p></> : <div className="stats-empty"><Clock3 size={20} /><span>Run detection to see real model statistics.</span></div>}
          </div>
        </section>
      </div>
      <footer><span>NAZAR VISION · FINAL INTERNATIONAL UNIVERSITY</span><span>Hatchling detection research prototype</span></footer>
    </main>
  </div>
}
