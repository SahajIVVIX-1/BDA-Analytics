import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { Async, Card, PageHeader, SentimentPill, SourceBadge } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { apiGet } from '../services/api'
import { fmtDateTime, fmtInt, langName } from '../utils/format'

const inp = 'h-9 rounded-lg border border-line bg-surface px-3 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent/40'

function PostDrawer({ id, onClose }) {
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    setState({ loading: true })
    apiGet(`/api/posts/${id}`).then((data) => setState({ data })).catch((error) => setState({ error }))
  }, [id])
  const p = state.data
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-label="Post details">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative h-full w-full max-w-lg overflow-y-auto border-l border-line bg-surface p-5 shadow-xl">
        <button onClick={onClose} aria-label="Close" className="absolute right-4 top-4 text-muted hover:text-ink"><X size={18} /></button>
        <h2 className="text-sm font-semibold text-ink">Post document</h2>
        {state.loading && <div className="skeleton mt-4 h-40" />}
        {state.error && <p className="mt-4 text-sm text-critical">{state.error.message}</p>}
        {p && (
          <div className="mt-4 space-y-4 text-sm">
            <p className="whitespace-pre-wrap text-ink">{p.text}</p>
            <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-xs">
              {[
                ['Author', `@${p.user?.username} (${fmtInt(p.user?.followers)} followers)`],
                ['Account category', p.user?.account_category],
                ['Posted', fmtDateTime(p.created_at)],
                ['Language', langName(p.language)],
                ['Country', p.location?.country || 'Unknown'],
                ['Type', p.post_type],
                ['Sentiment', p.sentiment ? `${p.sentiment.label} (score ${p.sentiment.score}, confidence ${p.sentiment.confidence})` : 'not analysed'],
                ['Topic', p.topic ? `${p.topic.label} (weight ${p.topic.weight})` : 'none'],
                ['Keywords', p.keywords?.join(', ') || '–'],
                ['Hashtags', p.hashtags?.map((h) => `#${h}`).join(' ') || '–'],
                ['Mentions', p.mentions?.map((h) => `@${h}`).join(' ') || '–'],
                ['Engagement', p.engagement ? `${fmtInt(p.engagement.total)}${p.engagement.synthetic ? ' (synthetic)' : ''}` : '–'],
                ['Quality flags', p.quality_flags?.join(', ') || 'none'],
                ['Identical texts', `${fmtInt(p.identical_text_posts)} posts share this cleaned text`],
                ['Cleaned text', p.clean_text],
              ].map(([k, v]) => (
                <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="break-words text-ink-2">{v}</dd></div>
              ))}
            </dl>
            <details>
              <summary className="cursor-pointer text-xs text-accent">Raw MongoDB document</summary>
              <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-surface-2 p-3 text-[11px] text-ink-2">{JSON.stringify(p, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Explorer() {
  const { filters, setFilter, setMany } = useFilters()
  const [params, setParams] = useSearchParams()
  const page = Number(params.get('page') || 1)
  const sort = params.get('sort') || (filters.q ? 'relevance' : 'newest')
  const [q, setQ] = useState(filters.q || '')
  const [hashtag, setHashtag] = useState(filters.hashtag || '')
  const [minEng, setMinEng] = useState(filters.min_engagement || '')
  const [open, setOpen] = useState(null)
  useEffect(() => { setQ(filters.q || ''); setHashtag(filters.hashtag || ''); setMinEng(filters.min_engagement || '') }, [filters.q, filters.hashtag, filters.min_engagement])

  const setPage = (p) => setParams((prev) => { const n = new URLSearchParams(prev); n.set('page', String(p)); return n }, { replace: true })
  const setSort = (s) => setParams((prev) => { const n = new URLSearchParams(prev); n.set('sort', s); n.delete('page'); return n }, { replace: true })
  const posts = useApi('/api/posts', { ...filters, page, page_size: 25, sort: sort === 'relevance' && !filters.q ? 'newest' : sort })

  const submit = (e) => {
    e.preventDefault()
    setMany({ q: q.trim(), hashtag: hashtag.replace(/^#/, '').trim(), min_engagement: minEng, page: '' })
  }
  const total = posts.data?.total
  const pages = total ? Math.min(400, Math.ceil(total / 25)) : 1

  return (
    <>
      <PageHeader title="Data explorer" description="Search and filter the raw post documents. Free-text search uses MongoDB's text index; all other filters use the compound indexes.">
        <SourceBadge meta={posts.data?.meta} />
      </PageHeader>
      <Card>
        <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-60 flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <input aria-label="Search text" className={`${inp} w-full pl-9`} placeholder="Search words in posts (e.g. election, refugees)" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <input aria-label="Hashtag" className={`${inp} w-36`} placeholder="#hashtag" value={hashtag} onChange={(e) => setHashtag(e.target.value)} />
          <input aria-label="Minimum engagement" type="number" min="0" className={`${inp} w-36`} placeholder="Min eng." value={minEng} onChange={(e) => setMinEng(e.target.value)} />
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            <input type="checkbox" checked={!!filters.exclude_retweets} onChange={(e) => setFilter('exclude_retweets', e.target.checked ? 'true' : '')} /> Exclude retweets
          </label>
          {filters.user && <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-1 text-xs text-accent">@{filters.user}<button type="button" aria-label="Remove account filter" onClick={() => setFilter('user', '')}><X size={12} /></button></span>}
          <button className="h-9 rounded-lg bg-accent px-4 text-sm font-medium text-white hover:opacity-90">Search</button>
          <select aria-label="Sort" className={`${inp} w-36`} value={sort} onChange={(e) => setSort(e.target.value)}>
            {filters.q && <option value="relevance">Relevance</option>}
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="engagement">Engagement</option>
          </select>
        </form>
      </Card>

      <Card className="mt-4" title={total !== undefined && total !== null ? `${fmtInt(total)}${posts.data?.total_capped ? '+' : ''} matching posts` : 'Posts'}
        subtitle="Click a post to open its full MongoDB document">
        <Async state={posts} height={500} isEmpty={(x) => !x.items.length}>
          {(x) => (
            <ul className="divide-y divide-line">
              {x.items.map((p) => (
                <li key={p.id}>
                  <button className="w-full px-1 py-3 text-left hover:bg-surface-2" onClick={() => setOpen(p.id)}>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                      <span className="font-medium text-ink-2">@{p.user?.username}</span>
                      <span>{fmtDateTime(p.created_at)}</span>
                      <span>{langName(p.language)}</span>
                      {p.location?.country && <span>{p.location.country}</span>}
                      <SentimentPill label={p.sentiment?.label} />
                      {p.topic && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">{p.topic.label}</span>}
                      {p.is_retweet && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">retweet</span>}
                      <span className="ml-auto tabular">{p.engagement ? `${fmtInt(p.engagement.total)} eng.` : ''}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink">{p.text}</p>
                    {p.hashtags?.length > 0 && <p className="mt-1 text-xs text-accent">{p.hashtags.map((h) => `#${h}`).join(' ')}</p>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Async>
        <div className="mt-3 flex items-center justify-between text-xs text-muted">
          <span>Page {page}{pages ? ` of ${fmtInt(pages)}` : ''}{pages >= 400 ? ' (narrow the filters to go deeper)' : ''}</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 disabled:opacity-40"><ChevronLeft size={14} />Prev</button>
            <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next<ChevronRight size={14} /></button>
          </div>
        </div>
      </Card>
      {open && <PostDrawer id={open} onClose={() => setOpen(null)} />}
    </>
  )
}
