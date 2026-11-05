import { useState } from 'react'
import { useResource, date, human, type Job, type Notice } from './api'
import { Card, Empty, JobMonitor, JobsTable } from './Shared'

type Event = { id: string; kind: string; entity_id: string; data_json: string; created_at: string }

export default function HistoryPanel({tick, notify}: {tick: number; notify: Notice}) {
  const {data: jobs, error: jobsError} = useResource<Job[]>('/jobs', [], tick, 5000)
  const {data: events, error: eventError} = useResource<Event[]>('/history', [], tick, 10000)
  const [selected, setSelected] = useState('')
  return <>
    <Card title="Experiment and background-job history">
      {jobsError && <p role="alert" className="nv-error">{jobsError}</p>}
      <JobsTable jobs={jobs} onSelect={setSelected}/>
    </Card>
    {selected && <JobMonitor id={selected} notify={notify}/>}
    <Card title="Source decisions and model history">
      {eventError && <p role="alert" className="nv-error">{eventError}</p>}
      {events.length ? <div className="nv-table-wrap"><table>
        <thead><tr><th>Recorded action</th><th>Entity</th><th>Timestamp</th><th>Evidence</th></tr></thead>
        <tbody>{events.map(event => <tr key={event.id}>
          <td>{human(event.kind)}</td><td><code>{event.entity_id.slice(0,16)}</code></td>
          <td>{date(event.created_at)}</td>
          <td><details><summary>Inspect recorded details</summary><pre className="nv-log light">{JSON.stringify(JSON.parse(event.data_json),null,2)}</pre></details></td>
        </tr>)}</tbody>
      </table></div> : <Empty title="No recorded source decisions">Dataset inspections, group assignments, model registrations, and activations appear here.</Empty>}
    </Card>
  </>
}
