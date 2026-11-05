import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Check, Download, Plus, Save, Trash2 } from 'lucide-react'
import './review.css'

type Box = { id: string; prediction_id?: string | null; class_name: string; xyxy: [number, number, number, number]; confidence?: number | null }
type ImageItem = { id: string; pool: 'training' | 'evaluation'; dataset_id?: string; filename: string; source_title: string; source_page: string; source_group: string; source_role: string; source_path: string; width: number; height: number; image_url: string; status: string; reviewer: string; notes: string; reviewed_at: string | null; revision: number; predictions: Box[]; boxes: Box[]; original_annotations?: Box[]; suggestions?: Box[] }
type Drag = { kind: 'draw' | 'move' | 'resize'; id?: string; handle?: string; start: [number, number]; original?: [number, number, number, number] }

const classes = ['hatchling', 'adult_turtle', 'crab', 'bird', 'other']
const statuses = ['unreviewed', 'in_review', 'verified_positive', 'verified_negative', 'needs_correction', 'ambiguous', 'rejected', 'excluded']
const formatStatus = (value: string) => value.replaceAll('_', ' ')
const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Request failed'

async function readJson(response: Response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`)
  return body
}

export default function ReviewWorkspace() {
  const [queue, setQueue] = useState<ImageItem[]>([])
  const [active, setActive] = useState<ImageItem | null>(null)
  const [boxes, setBoxes] = useState<Box[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [tool, setTool] = useState<'select' | 'draw'>('select')
  const [status, setStatus] = useState('in_review')
  const [reviewer, setReviewer] = useState('')
  const [notes, setNotes] = useState('')
  const [filter, setFilter] = useState('all')
  const [poolFilter, setPoolFilter] = useState('all')
  const [datasetFilter, setDatasetFilter] = useState(new URLSearchParams(window.location.search).get('dataset') || 'all')
  const [datasets, setDatasets] = useState<{id: string; name: string}[]>([])
  const [zoom, setZoom] = useState(1)
  const [history, setHistory] = useState<{revision: number; status: string; reviewer: string; saved_at: string}[]>([])
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [dirty, setDirty] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)
  const dragRef = useRef<Drag | null>(null)

  const refreshQueue = () => fetch('/api/review/images').then(readJson).then(setQueue).catch(error => setError(messageOf(error)))
  useEffect(() => { void refreshQueue() }, [])
  useEffect(() => { fetch('/api/platform/datasets').then(readJson).then(setDatasets).catch(()=>{}) }, [])
  useEffect(() => { const id=new URLSearchParams(window.location.search).get('image'); if(id && queue.some(i=>i.id===id) && !active) void open(id) }, [queue])
  useEffect(() => { if(active) fetch(`/api/review/images/${active.id}/history`).then(readJson).then(setHistory).catch(()=>{}) }, [active?.id,active?.revision])
  useEffect(() => { const before=(event: BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue=''}};window.addEventListener('beforeunload',before);return()=>window.removeEventListener('beforeunload',before) }, [dirty])

  const open = async (id: string) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    try {
      const item = await readJson(await fetch(`/api/review/images/${id}`)) as ImageItem
      setActive(item)
      setBoxes((item.revision ? item.boxes : item.original_annotations?.length ? item.original_annotations : item.suggestions?.length ? item.suggestions : item.predictions).map(box => ({ ...box, xyxy: [...box.xyxy] as Box['xyxy'] })))
      setStatus(item.revision ? item.status : 'in_review')
      setReviewer(item.reviewer || localStorage.getItem('nazar-reviewer') || '')
      setNotes(item.notes)
      setSelected(null)
      setTool('select')
      setZoom(1)
      setDirty(false)
      setError('')
      setNotice('')
    } catch (error) { setError(messageOf(error)) }
  }

  const point = (event: React.PointerEvent<SVGSVGElement>): [number, number] => {
    const rect = svgRef.current!.getBoundingClientRect()
    return [Math.max(0, Math.min(active!.width, (event.clientX - rect.left) * active!.width / rect.width)),
      Math.max(0, Math.min(active!.height, (event.clientY - rect.top) * active!.height / rect.height))]
  }
  const startDraw = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!active || tool !== 'draw' || event.target !== svgRef.current) return
    const start = point(event)
    const id = crypto.randomUUID()
    dragRef.current = { kind: 'draw', id, start }
    setBoxes(previous => [...previous, { id, class_name: 'hatchling', xyxy: [start[0], start[1], start[0], start[1]] }])
    setSelected(id)
    svgRef.current?.setPointerCapture(event.pointerId)
    setDirty(true)
  }
  const beginEdit = (event: React.PointerEvent<SVGElement>, box: Box, kind: 'move' | 'resize', handle?: string) => {
    if (tool !== 'select') return
    event.stopPropagation()
    dragRef.current = { kind, id: box.id, handle, start: point(event as unknown as React.PointerEvent<SVGSVGElement>), original: [...box.xyxy] }
    setSelected(box.id)
    svgRef.current?.setPointerCapture(event.pointerId)
  }
  const move = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag || !active) return
    const [x, y] = point(event)
    setBoxes(previous => previous.map(box => {
      if (box.id !== drag.id) return box
      if (drag.kind === 'draw') return { ...box, xyxy: [Math.min(drag.start[0], x), Math.min(drag.start[1], y), Math.max(drag.start[0], x), Math.max(drag.start[1], y)] }
      const [x1, y1, x2, y2] = drag.original!
      if (drag.kind === 'move') {
        const dx = Math.max(-x1, Math.min(active.width - x2, x - drag.start[0]))
        const dy = Math.max(-y1, Math.min(active.height - y2, y - drag.start[1]))
        return { ...box, xyxy: [x1 + dx, y1 + dy, x2 + dx, y2 + dy] }
      }
      const left = drag.handle?.includes('l') ? Math.min(x, x2 - 1) : x1
      const right = drag.handle?.includes('r') ? Math.max(x, x1 + 1) : x2
      const top = drag.handle?.includes('t') ? Math.min(y, y2 - 1) : y1
      const bottom = drag.handle?.includes('b') ? Math.max(y, y1 + 1) : y2
      return { ...box, xyxy: [left, top, right, bottom] }
    }))
    setDirty(true)
  }
  const end = () => {
    const drag = dragRef.current
    if (drag?.kind === 'draw') setBoxes(previous => previous.filter(box => box.id !== drag.id || (box.xyxy[2] - box.xyxy[0] >= 2 && box.xyxy[3] - box.xyxy[1] >= 2)))
    dragRef.current = null
  }
  const updateBox = (id: string, changes: Partial<Box>) => { setBoxes(previous => previous.map(box => box.id === id ? { ...box, ...changes } : box)); setDirty(true) }
  const removeBox = (id: string) => { setBoxes(previous => previous.filter(box => box.id !== id)); setSelected(null); setDirty(true) }

  const save = async () => {
    if (!active) return
    setBusy(true); setError(''); setNotice('')
    try {
      const payload = { status, reviewer, notes, revision: active.revision,
        boxes: boxes.map(({ id, prediction_id, class_name, xyxy }) => ({ id, prediction_id: prediction_id || null, class_name, xyxy })) }
      const result = await readJson(await fetch(`/api/review/images/${active.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })) as ImageItem
      setActive(result); setBoxes(result.boxes); setDirty(false); setNotice(`Saved revision ${result.revision}. Reopen this image to verify persistence.`)
      if(reviewer.trim()) localStorage.setItem('nazar-reviewer',reviewer.trim())
      await refreshQueue()
    } catch (error) { setError(messageOf(error)) } finally { setBusy(false) }
  }
  useEffect(()=>{const key=(event: KeyboardEvent)=>{const element=event.target as HTMLElement;if(element.matches('input,select,textarea'))return;if((event.ctrlKey||event.metaKey)&&event.key==='s'){event.preventDefault();void save()}if(event.key==='Delete'&&selected){event.preventDefault();removeBox(selected)}if(event.key==='Escape')setSelected(null)};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[active,selected,boxes,status,reviewer,notes])
  const exportVerified = async (purpose: 'training' | 'evaluation') => {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await readJson(await fetch(`/api/review/exports?purpose=${purpose}`, { method: 'POST' }))
      setNotice(`Exported ${result.images} verified ${purpose} images and ${result.hatchling_boxes} hatchling boxes to ${result.path}`)
    } catch (error) { setError(messageOf(error)) } finally { setBusy(false) }
  }
  const search = query.trim().toLowerCase()
  const shown = queue.filter(item => (poolFilter === 'all' || item.pool === poolFilter)
    && (datasetFilter === 'all' || item.dataset_id === datasetFilter)
    && (filter === 'all' || item.status === filter)
    && (!search || [item.filename, item.source_title, item.source_group, item.source_path]
      .some(value => value.toLowerCase().includes(search))))
  const current = boxes.find(box => box.id === selected)
  const handleSize = active ? Math.max(4, active.width * 0.009) : 6
  const modelConfidence = (box: Box) => box.confidence ?? active?.predictions.find(prediction => prediction.id === box.prediction_id)?.confidence

  return <div className="review-app">
    <header className="review-top"><div><a href="/" className="review-back"><ArrowLeft size={17} /> Project overview</a><h1>Annotation review</h1><p>Training candidates and frozen evaluation media stay in separate pools.</p></div><div className="review-export-actions"><button onClick={() => void exportVerified('training')} disabled={busy}><Download size={17} /> Export training labels</button><button onClick={() => void exportVerified('evaluation')} disabled={busy}><Download size={17} /> Export evaluation labels</button></div></header>
    <div className="review-layout">
      <aside className="review-queue"><div className="review-queue-head"><strong>Image queue</strong><span>{shown.length} of {queue.length}</span></div><select aria-label="Filter dataset" value={datasetFilter} onChange={event=>setDatasetFilter(event.target.value)}><option value="all">All datasets</option>{datasets.map(dataset=><option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select><select aria-label="Filter review pool" value={poolFilter} onChange={event => setPoolFilter(event.target.value)}><option value="training">Training candidates</option><option value="evaluation">Frozen evaluation</option><option value="all">Both pools</option></select><input aria-label="Search images" placeholder="Filename or source group" value={query} onChange={event => setQuery(event.target.value)} /><select aria-label="Filter review status" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All statuses</option>{statuses.map(value => <option key={value} value={value}>{formatStatus(value)}</option>)}</select><div className="review-items">{shown.length ? shown.map(item => <button key={item.id} className={active?.id === item.id ? 'active' : ''} onClick={() => void open(item.id)}><strong>{item.filename}</strong><small>{item.pool} · {formatStatus(item.status)} · {item.source_group || 'unknown group'}</small></button>) : <p className="review-no-results">No images match these filters.</p>}</div></aside>
      <main className="review-main">{!active ? <div className="review-empty">Choose an image from the queue to inspect its predictions and begin review.</div> : <>
        <div className="review-meta"><div><h2>{active.source_title || active.filename}</h2><p>{active.width} × {active.height} · {active.source_group || 'No source group'} · source tag: {active.source_role}</p><p>{active.pool === 'evaluation' ? 'Frozen evaluation image: never use its export for model training.' : 'Training candidate: verify annotations and confirm the source event before preparation.'}</p>{active.source_page && <a href={active.source_page} target="_blank" rel="noreferrer">Source page</a>}</div><span className={`review-badge ${active.status}`}>{active.pool} · {formatStatus(active.status)} · revision {active.revision}</span></div>
        <div className="review-controls"><button className={tool === 'select' ? 'on' : ''} onClick={() => setTool('select')}>Select / move</button><button className={tool === 'draw' ? 'on' : ''} onClick={() => setTool('draw')}><Plus size={15} /> Draw hatchling</button><label>Zoom <select aria-label="Image zoom" value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[.5,1,1.5,2,3].map(n=><option key={n} value={n}>{n*100}%</option>)}</select></label><span>Drag corners to resize · Delete removes · Ctrl+S saves</span></div>
        <div className="review-viewport"><div className="review-image-wrap" style={{width:`${zoom*100}%`,maxWidth:'none'}}><img src={active.image_url} alt={active.source_title || active.filename} draggable={false} /><svg ref={svgRef} viewBox={`0 0 ${active.width} ${active.height}`} onPointerDown={startDraw} onPointerMove={move} onPointerUp={end} onPointerCancel={end} style={{ cursor: tool === 'draw' ? 'crosshair' : 'default' }}>
          {active.predictions.map(box => <rect key={box.id} x={box.xyxy[0]} y={box.xyxy[1]} width={box.xyxy[2] - box.xyxy[0]} height={box.xyxy[3] - box.xyxy[1]} className="prediction-box" pointerEvents="none" />)}
          {boxes.map(box => <g key={box.id}><rect x={box.xyxy[0]} y={box.xyxy[1]} width={box.xyxy[2] - box.xyxy[0]} height={box.xyxy[3] - box.xyxy[1]} className={`review-box ${selected === box.id ? 'selected' : ''}`} onPointerDown={event => beginEdit(event, box, 'move')} /><text x={box.xyxy[0]} y={Math.max(16, box.xyxy[1] - 5)} className="review-label" pointerEvents="none">{box.class_name}{modelConfidence(box) != null ? ` ${((modelConfidence(box) ?? 0) * 100).toFixed(0)}%` : ''}</text>{selected === box.id && ['lt', 'rt', 'lb', 'rb'].map(handle => <rect key={handle} x={(handle.includes('l') ? box.xyxy[0] : box.xyxy[2]) - handleSize} y={(handle.includes('t') ? box.xyxy[1] : box.xyxy[3]) - handleSize} width={handleSize * 2} height={handleSize * 2} className="review-handle" onPointerDown={event => beginEdit(event, box, 'resize', handle)} />)}</g>)}
        </svg></div></div><div className="review-legend"><span>Dashed amber: original model prediction</span><span>Solid green: editable review annotation</span></div>
        {active.original_annotations!==undefined&&<button className="nv-secondary" onClick={()=>{if(!dirty||window.confirm('Replace the editable copy with source label candidates? Saved review history is preserved.')){setBoxes(active.original_annotations!.map(box=>({...box,xyxy:[...box.xyxy]})));setStatus('in_review');setDirty(true);setSelected(null)}}}>Load source label candidates</button>}
        <div className="review-panels"><section><h3>Boxes ({boxes.length})</h3><p>Model predictions are suggestions until you save a verified review.</p>{boxes.map((box, index) => <div className={`review-box-row ${selected === box.id ? 'selected' : ''}`} key={box.id} onClick={() => setSelected(box.id)}><strong>#{index + 1}</strong><select aria-label={`Class for box ${index + 1}`} value={box.class_name} onChange={event => updateBox(box.id, { class_name: event.target.value })}>{!classes.includes(box.class_name) && <option value={box.class_name}>Source: {box.class_name} (map class)</option>}{classes.map(name => <option key={name}>{name}</option>)}</select><span>{modelConfidence(box) == null ? 'Added' : `${((modelConfidence(box) ?? 0) * 100).toFixed(1)}% model`}</span><button aria-label={`Delete box ${index + 1}`} onClick={event => { event.stopPropagation(); removeBox(box.id) }}><Trash2 size={16} /></button></div>)}{current && <small>Selected: {current.xyxy.map(value => value.toFixed(1)).join(', ')}</small>}</section>
        <section><h3>Review decision</h3><label>Status<select aria-label="Review status" value={status} onChange={event => { setStatus(event.target.value); setDirty(true) }}><option value="in_review">In review</option><option value="verified_positive">Approve positive</option><option value="verified_negative">Approve negative</option><option value="needs_correction">Needs correction</option><option value="ambiguous">Ambiguous / uncertain</option><option value="rejected">Reject unusable image</option><option value="excluded">Duplicate / excluded</option></select></label><p>A verified negative must have no hatchling boxes. Uncertain, rejected, and excluded images cannot enter training exports.</p><label>Reviewer name<input value={reviewer} onChange={event => { setReviewer(event.target.value); setDirty(true) }} placeholder="Required for approval or exclusion" /></label><label>Notes<textarea value={notes} onChange={event => { setNotes(event.target.value); setDirty(true) }} placeholder="Why did you change this annotation?" /></label><button className="review-save" disabled={busy||(['verified_positive','verified_negative','rejected','excluded'].includes(status)&&!reviewer.trim())} onClick={() => void save()}>{status.startsWith('verified') ? <Check size={16} /> : <Save size={16} />} Save review</button><small>{active.reviewed_at ? `Last saved ${new Date(active.reviewed_at).toLocaleString()}` : 'Not reviewed yet'}{dirty ? ' · Unsaved changes' : ''}</small>{!!active.suggestions?.length&&<button className="nv-secondary" onClick={()=>{if(!dirty||confirm('Replace the editable copy with model suggestions?')){setBoxes(active.suggestions!.map(b=>({...b,xyxy:[...b.xyxy]})));setStatus('in_review');setDirty(true)}}}>Load latest unverified model suggestions</button>}<details><summary>Immutable review history ({history.length})</summary>{history.map(event=><p key={event.revision}>Revision {event.revision} · {formatStatus(event.status)} · {event.reviewer||'Reviewer not recorded'} · {new Date(event.saved_at).toLocaleString()}</p>)}</details></section></div>
      </>}</main>
    </div>{error && <div role="alert" className="review-toast error">{error}</div>}{notice && <div role="status" className="review-toast">{notice}</div>}
  </div>
}
