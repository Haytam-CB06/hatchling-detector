import { useCallback, useState } from 'react'
import { Activity, ArrowRight, Bell, BookOpen, Boxes, ChevronLeft, Cpu, Database, Eye, FileText, FlaskConical, GitCompareArrows, Layers3, LayoutDashboard, Menu, RefreshCw, ScanSearch, ShieldCheck, Sparkles, Upload, Video, X } from 'lucide-react'
import App from './App'
import ReviewWorkspace from './ReviewWorkspace'
import HistoryPanel from './platform/HistoryPanel'
import { DatasetsPage, PreparationPage, QualityPage } from './platform/DatasetPages'
import { EvaluationPage, ImprovementPage, MonitoringPage, RegistryPage, ReportsPage, TrainingPage } from './platform/ExperimentPages'
import { Badge, Card, Empty, JobsTable, Plot, JobMonitor } from './platform/Shared'
import { useResource, post, message, percent, bytes, type Dataset, type Model, type Version, type Evaluation, type Overview, type Job, type MetricRow } from './platform/api'
import './platform.css'

const navigation = [
  {group:'WORKSPACE',items:[['/','Overview',LayoutDashboard],['/datasets','Dataset library',Database],['/quality','Quality control',ShieldCheck],['/review','Annotation review',Eye]]},
  {group:'EXPERIMENTS',items:[['/prepare','Dataset preparation',Layers3],['/training','Model training',Cpu],['/models','Model registry',Boxes],['/evaluation','Evaluation',GitCompareArrows]]},
  {group:'APPLICATION',items:[['/inference','Image & video inference',ScanSearch],['/improvement','Active learning',Sparkles],['/monitoring','Video monitoring',Video],['/reports','Reports & history',FileText]]},
] as const
const pages:Record<string,[string,string]>={
  '/':['Project overview','A clear view of your data, experiments, and active detector.'],
  '/datasets':['Dataset library','Import, inspect, and trace every source dataset.'], '/quality':['Dataset quality','Find annotation and image issues before preparing an experiment.'],
  '/review':['Human annotation review','Correct model suggestions and save explicit human decisions.'], '/prepare':['Dataset preparation','Build reproducible versions from approved labels and confirmed source events.'],
  '/training':['Model training','Configure bounded experiments and follow real training progress.'], '/models':['Model registry','Compare preserved checkpoints and select the active detector.'],
  '/evaluation':['Model evaluation','Measure predictions against verified annotations.'], '/inference':['Image & video inference','Test the active detector on actual images and recordings.'],
  '/improvement':['Active learning','Connect difficult predictions to the next human review cycle.'], '/monitoring':['Video monitoring','Inspect recording timelines and the camera integration boundary.'],
  '/reports':['Reports & experiment history','Export technical evidence from the current project records.'],
}

export default function Platform() {
  const path=window.location.pathname.replace(/\/$/,'')||'/'
  const [collapsed,setCollapsed]=useState(localStorage.getItem('nazar-sidebar')==='collapsed'),[tick,setTick]=useState(0),[toast,setToast]=useState<{text:string;error:boolean}|null>(null),[job,setJob]=useState('')
  const notify=useCallback((text:string,error=false)=>setToast({text,error}),[])
  const refresh=useCallback(()=>setTick(v=>v+1),[])
  const {data:overview,error:overviewError}=useResource<Overview|null>('/overview',null,tick,12000)
  const {data:datasets}=useResource<Dataset[]>('/datasets',[],tick,10000)
  const {data:models}=useResource<Model[]>('/models',[],tick,10000)
  const {data:versions}=useResource<Version[]>('/versions',[],tick,10000)
  const {data:jobs}=useResource<Job[]>('/jobs',[],tick,5000)
  const {data:evaluations}=useResource<Evaluation[]>('/evaluations',[],tick,10000)
  const active=models.find(m=>m.active)
  const {data:history}=useResource<MetricRow[]>(active?`/models/${active.id}/history`:'',[],tick)
  const [title,description]=pages[path]||pages['/']
  const toggle=()=>{setCollapsed(v=>!v);localStorage.setItem('nazar-sidebar',collapsed?'expanded':'collapsed')}
  const activate=async(id:string)=>{try{await post(`/models/${id}/activate`);notify('Selected model loaded and checksum verified');refresh()}catch(e){notify(message(e),true)}}
  return <div className={`nv-shell ${collapsed?'collapsed':''}`}>
    <aside className="nv-nav"><a href="/" className="nv-brand"><div className="nv-logo"><Eye size={25}/></div>{!collapsed&&<div><strong>NAZAR<span>VISION</span></strong><small>AI LIFECYCLE PLATFORM</small></div>}</a><button className="nv-collapse" onClick={toggle} aria-label="Toggle sidebar">{collapsed?<Menu size={17}/>:<ChevronLeft size={17}/>}</button>
      <nav aria-label="Model lifecycle navigation">{navigation.map(section=><div className="nv-nav-group" key={section.group}>{!collapsed&&<span>{section.group}</span>}{section.items.map(([url,label,Icon])=><a href={url} key={url} className={url===path?'active':''} title={label}><Icon size={18}/>{!collapsed&&<span>{label}</span>}{!collapsed&&url==='/review'&&!!overview?.pending_reviews&&<b>{overview.pending_reviews}</b>}</a>)}</div>)}</nav>
      {!collapsed&&<div className="nv-nav-footer"><div className="nv-university"><BookOpen size={17}/><div>Final International University<small>Software Engineering Project</small></div></div><span className="nv-local"><i/>LOCAL WORKSPACE</span></div>}
    </aside>
    <div className="nv-body"><header className="nv-topbar"><div className="nv-breadcrumb">Workspace <span>/</span><strong>{title}</strong></div><div className="nv-actions"><span className={`nv-model-state ${overview?.model_state.ready?'ready':''}`}><i/>{overview?.model_state.ready?'Model ready':overview?.model_state.state||'Connecting'}</span><button className="nv-icon" onClick={refresh} aria-label="Refresh project records"><RefreshCw size={17}/></button><a className="nv-avatar" href="/reports" title="Project reports">NV</a></div></header>
      <main className="nv-content"><div className="nv-page-heading"><div><span className="nv-kicker">NAZAR VISION WORKSPACE</span><h1>{title}</h1><p>{description}</p></div>{path==='/'&&<a className="nv-primary" href="/datasets"><Upload size={16}/>Import dataset</a>}</div>
      {overviewError&&<div className="nv-error" role="alert">Backend connection: {overviewError}</div>}
      {path==='/'&&<>
        <div className="nv-welcome"><div><span className="nv-kicker">FROM DATA TO DEPLOYMENT</span><h2>Build a detector you can trust.</h2><p>Review the evidence, prepare clean data, and follow every experiment in one workspace.</p><a href="/prepare">Continue dataset preparation <ArrowRight size={16}/></a></div><div className="nv-welcome-mark"><ScanSearch size={94} strokeWidth={1}/><span>SEA TURTLE HATCHLINGS</span></div></div>
        <div className="nv-stat-grid">{[[Database,'Dataset images',overview?.images,'Across imported source datasets'],[Eye,'Awaiting human review',overview?.pending_reviews,'Unreviewed, draft, or uncertain'],[ShieldCheck,'Approved objects',overview?.approved_objects,'Verified hatchling boxes'],[Layers3,'Prepared versions',overview?.versions,'Immutable YOLO snapshots']].map(([Icon,label,value,note])=>{const I=Icon as typeof Database;return <div className="nv-stat" key={String(label)}><div><span>{String(label)}</span><I size={19}/></div><strong>{typeof value==='number'?value.toLocaleString():'—'}</strong><small>{String(note)}</small></div>})}</div>
        <div className="nv-dashboard-grid"><Card title="Active detector" aside={<Badge value={overview?.model_state.state||'loading'}/>}><div className="nv-active-model"><div className="nv-model-icon"><Cpu size={28}/></div><div><h3>{active?.name||'Indexing registry…'}</h3><p>{active?.architecture||'Waiting for checkpoint metadata'}</p></div><a className="nv-text" href="/models">Manage →</a></div><div className="nv-four-metrics">{[['precision','Precision'],['recall','Recall'],['map50','mAP50'],['map50_95','mAP50:95']].map(([key,label])=><div key={key}><strong>{percent(active?.metrics[key])}</strong><span>{label}</span></div>)}</div><p className="nv-help">{String(active?.metrics.scope||'No logged validation metrics available.')}.</p><div className="nv-model-meta"><span>Dataset: {active?.configuration.data?String(active.configuration.data).split(/[\\/]/).slice(-2).join('/'):'Not recorded'}</span><span>{overview?.inference_average_ms?`${overview.inference_average_ms.toFixed(1)} ms average / ${overview.inference_sample_count} image calls`:'No image inference timing recorded'}</span></div><Plot rows={history} title="Recorded validation accuracy" series={[["metrics/mAP50(B)","mAP50"],["metrics/mAP50-95(B)","mAP50:95"]]}/></Card>
        <div className="nv-stack"><Card title="Review progress" aside={<Eye size={18}/>}><div className="nv-review-number"><strong>{(overview?.review_status.verified_positive||0)+(overview?.review_status.verified_negative||0)}</strong><span>/ {overview?.images||0} approved</span></div><progress max={overview?.images||1} value={(overview?.review_status.verified_positive||0)+(overview?.review_status.verified_negative||0)}/><div className="nv-key-values"><span>Approved positives<b>{overview?.review_status.verified_positive||0}</b></span><span>Verified negatives<b>{overview?.review_status.verified_negative||0}</b></span><span>Pending decisions<b>{overview?.pending_reviews||0}</b></span></div><a className="nv-primary wide" href="/review">Open annotation review <ArrowRight size={15}/></a></Card><Card title="Local compute" aside={<Activity size={18}/>}><div className="nv-key-values"><span>Processing device<b>{overview?.hardware.gpus.length?'CUDA GPU':'CPU'}</b></span><span>Available memory<b>{overview?bytes(overview.hardware.ram_available):'—'}</b></span><span>Free project storage<b>{overview?bytes(overview.hardware.disk_free):'—'}</b></span><span>Logical cores<b>{overview?.hardware.cpu_count??'—'}</b></span></div></Card></div></div>
        <Card title="Your model development workflow"><div className="nv-pipeline">{[['/datasets','Import data',Database],['/review','Review labels',Eye],['/prepare','Prepare data',Layers3],['/training','Train model',Cpu],['/evaluation','Evaluate',FlaskConical],['/models','Activate',Boxes],['/inference','Test media',ScanSearch],['/improvement','Improve',Sparkles]].map(([url,label,Icon],n)=>{const I=Icon as typeof Database;return <a href={String(url)} key={String(url)}><b>{String(n+1).padStart(2,'0')}</b><I size={22}/><strong>{String(label)}</strong></a>})}</div></Card>
        <div className="nv-two nv-align-start"><Card title="Recent background work"><JobsTable jobs={jobs.slice(0,5)} onSelect={setJob}/></Card><Card title="Data readiness" aside={<Bell size={18}/>}><div className="nv-alert"><ShieldCheck size={20}/><div><strong>{overview?.quality_issue_count??0} original-source quality flags</strong><p>Review findings before preparing a new experiment.</p><a href="/quality" className="nv-text">Inspect quality findings →</a></div></div><div className="nv-alert"><Layers3 size={20}/><div><strong>Source-event evidence is required</strong><p>Filename-based groups do not establish independent validation. Confirm groups and partitions in the preparation wizard.</p><a href="/prepare" className="nv-text">Review grouping →</a></div></div>{overview?.model_state.reason&&<p className="nv-error">{overview.model_state.reason}</p>}</Card></div>{job&&<JobMonitor id={job} notify={notify}/>}
      </>}
      {path==='/datasets'&&<DatasetsPage datasets={datasets} models={models} tick={tick} notify={notify} refresh={refresh}/>}
      {path==='/quality'&&<QualityPage tick={tick} notify={notify}/>}
      {path==='/review'&&<ReviewWorkspace/>}
      {path==='/prepare'&&<PreparationPage datasets={datasets} versions={versions} tick={tick} notify={notify} refresh={refresh}/>}
      {path==='/training'&&<TrainingPage models={models} versions={versions} jobs={jobs} hardware={overview?.hardware} notify={notify} refresh={refresh}/>}
      {path==='/models'&&<RegistryPage models={models} notify={notify} refresh={refresh}/>}
      {path==='/evaluation'&&<EvaluationPage models={models} versions={versions} jobs={jobs} evaluations={evaluations} notify={notify} refresh={refresh}/>}
      {path==='/inference'&&<><Card title="Active inference model" aside={<a className="nv-text" href="/improvement">Review inference candidates →</a>}><div className="nv-actions"><select aria-label="Select active inference model" value={active?.id||''} onChange={e=>void activate(e.target.value)}>{models.filter(m=>!m.pretrained).map(model=><option key={model.id} value={model.id}>{model.name}</option>)}</select><code>{active?.sha256.slice(0,24)||'Loading checksum'}…</code><Badge value={overview?.model_state.state||'loading'}/></div></Card><div className="nv-inference"><App key={active?.id}/></div></>}
      {path==='/improvement'&&<ImprovementPage tick={tick} notify={notify} refresh={refresh}/>}
      {path==='/monitoring'&&<MonitoringPage tick={tick}/>}
      {path==='/reports'&&<><ReportsPage tick={tick} notify={notify}/><HistoryPanel tick={tick} notify={notify}/></>}
      {!pages[path]&&<Empty title="Page not found"><a href="/">Return to project overview</a></Empty>}
      <div className="nv-footer"><span>NAZAR VISION · FINAL INTERNATIONAL UNIVERSITY</span><span>Reproducible data. Reviewed annotations. Real model outputs.</span></div>
      </main>
    </div>{toast&&<div className={`nv-toast ${toast.error?'error':''}`} role={toast.error?'alert':'status'}><span>{toast.text}</span><button aria-label="Dismiss notification" onClick={()=>setToast(null)}><X size={16}/></button></div>}
  </div>
}
