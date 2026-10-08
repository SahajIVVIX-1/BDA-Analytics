import { useEffect, useRef, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { Async, Card, Note, PageHeader, Table } from '../components/ui'
import { useToast } from '../components/Toast'
import { useApi } from '../hooks/useApi'
import { apiPost, apiUpload } from '../services/api'
import { fmtBytes, fmtDateTime, fmtInt } from '../utils/format'

const STATUS_STYLE = {
  completed: 'bg-good/15 text-good', failed: 'bg-critical/15 text-critical', running: 'bg-accent-soft text-accent',
  queued: 'bg-surface-2 text-ink-2', nlp: 'bg-accent-soft text-accent', rollups: 'bg-accent-soft text-accent',
}

export default function Ingestion() {
  const toast = useToast()
  const [file, setFile] = useState(null)
  const [upload, setUpload] = useState(null)
  const [busy, setBusy] = useState(false)
  const [profile, setProfile] = useState('generic')
  const [batch, setBatch] = useState(5000)
  const jobs = useApi('/api/ingestion/jobs', { limit: 20 })
  const inputRef = useRef()

  const active = jobs.data?.some((j) => ['queued', 'running', 'nlp', 'rollups'].includes(j.status))
  useEffect(() => {
    if (!active) return undefined
    const t = setInterval(jobs.retry, 2000)
    return () => clearInterval(t)
  }, [active, jobs.retry])

  const doUpload = async () => {
    if (!file) return
    setBusy(true)
    try {
      const res = await apiUpload('/api/ingestion/upload', file)
      setUpload(res)
      toast(`Uploaded ${res.filename} (${fmtBytes(res.size_bytes)})`)
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const start = async () => {
    setBusy(true)
    try {
      const job = await apiPost('/api/ingestion/start', { upload_id: upload.upload_id, profile, batch_size: Number(batch) })
      toast(`Job ${job.id} started`)
      setUpload(null)
      setFile(null)
      jobs.retry()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="Data ingestion" description="Upload CSV, JSON or JSONL posts (gzip allowed). A background job validates, cleans, deduplicates and bulk-inserts them, then runs NLP and refreshes only the affected days of the summary tables." />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Upload a file" className="xl:col-span-1">
          <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0]); setUpload(null) }}
            className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-line px-4 py-8 text-center">
            <UploadCloud className="text-muted" />
            <p className="text-sm text-ink">{file ? file.name : 'Drop a file here'}</p>
            <p className="text-xs text-muted">{file ? fmtBytes(file.size) : '.csv · .json · .jsonl · .gz'}</p>
            <button onClick={() => inputRef.current.click()} className="mt-1 rounded-lg border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-2">Choose file</button>
            <input ref={inputRef} type="file" accept=".csv,.json,.jsonl,.ndjson,.gz" className="hidden" onChange={(e) => { setFile(e.target.files[0]); setUpload(null) }} />
          </div>
          {file && !upload && <button disabled={busy} onClick={doUpload} className="mt-3 w-full rounded-lg bg-accent py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? 'Uploading…' : 'Upload'}</button>}
          {upload && (
            <div className="mt-4 space-y-3 text-sm">
              <p className="text-xs text-muted">Detected columns: <span className="text-ink-2">{upload.preview_columns.join(', ')}</span></p>
              <label className="block text-xs text-muted">Field mapping
                <select className="mt-1 block h-9 w-full rounded-lg border border-line bg-surface px-2 text-sm text-ink" value={profile} onChange={(e) => setProfile(e.target.value)}>
                  <option value="generic">Generic (id, text, created_at, user, likes, …)</option>
                  <option value="ira538">FiveThirtyEight IRA format</option>
                </select>
              </label>
              <label className="block text-xs text-muted">Batch size
                <input type="number" min="100" max="50000" className="mt-1 block h-9 w-full rounded-lg border border-line bg-surface px-2 text-sm text-ink" value={batch} onChange={(e) => setBatch(e.target.value)} />
              </label>
              <button disabled={busy} onClick={start} className="w-full rounded-lg bg-accent py-2 text-sm font-medium text-white disabled:opacity-50">Start ingestion job</button>
            </div>
          )}
          <div className="mt-4"><Note>Generic mapping accepts common names: id / post_id, text / content, created_at / timestamp, username, followers, likes, comments / replies, shares / retweets, language, country.</Note></div>
        </Card>

        <Card title="Ingestion jobs" subtitle="Statistics come from the ingestion_jobs collection" className="xl:col-span-2">
          <Async state={jobs} height={300} isEmpty={(x) => !x.length}>
            {(x) => (
              <Table dense rowKey={(j) => j.id} rows={x} columns={[
                { key: 'id', label: 'Job', render: (j) => <div><code className="text-xs text-ink">{j.id}</code><p className="text-[11px] text-muted">{fmtDateTime(j.started_at)}</p></div> },
                { key: 'status', label: 'Status', render: (j) => <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[j.status] || ''}`}>{j.status}</span> },
                { key: 'read', label: 'Read', align: 'right', render: (j) => fmtInt(j.stats?.total_read) },
                { key: 'inserted', label: 'Inserted', align: 'right', render: (j) => fmtInt(j.stats?.inserted) },
                { key: 'dup', label: 'Duplicates', align: 'right', render: (j) => fmtInt(j.stats?.duplicates) },
                { key: 'inv', label: 'Invalid', align: 'right', render: (j) => <span title={JSON.stringify(j.stats?.invalid_reasons || {})}>{fmtInt(j.stats?.invalid)}</span> },
                { key: 'time', label: 'Time', align: 'right', render: (j) => (j.stats ? `${j.stats.elapsed_sec.toFixed(1)} s` : '–') },
                { key: 'rate', label: 'Rec/s', align: 'right', render: (j) => fmtInt(j.stats?.records_per_sec) },
              ]} />
            )}
          </Async>
          {jobs.data?.[0]?.stats?.cleaning && (
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-accent">Cleaning statistics of the latest job</summary>
              <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                {Object.entries(jobs.data[0].stats.cleaning).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2 border-b border-line py-1"><dt className="text-muted">{k.replaceAll('_', ' ')}</dt><dd className="tabular text-ink">{fmtInt(v)}</dd></div>
                ))}
              </dl>
            </details>
          )}
        </Card>
      </div>
    </>
  )
}
