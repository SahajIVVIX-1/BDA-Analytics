import { Card, KpiCard, Note, PageHeader, SyntheticBadge, Table } from '../components/ui'

// Static description of the loaded dataset. Every figure is taken from docs/dataset.md and the
// ingestion job record of the full build; it does not change with the dashboard filters.

const FACTS = [
  { label: 'Rows read', value: '2,946,207' },
  { label: 'Posts stored', value: '2,944,814', hint: '1,392 duplicate ids and 1 empty tweet removed' },
  { label: 'Accounts', value: '2,843' },
  { label: 'Date range', value: '2012 – 2018', hint: '2012-02-02 to 2018-05-30; 99.5% in 2015-2017' },
  { label: 'Languages', value: '56', hint: '8,320 posts with no language' },
  { label: 'Posts with a country', value: '80.6%', hint: '570,812 unknown' },
]

const SOURCE = [
  ['Source', <a key="s" className="text-accent hover:underline" href="https://github.com/fivethirtyeight/russian-troll-tweets">fivethirtyeight/russian-troll-tweets</a>],
  ['Collected by', 'Darren Linvill and Patrick Warren (Clemson University), published by FiveThirtyEight in 2018'],
  ['Licence', 'Creative Commons Attribution 4.0 (CC BY 4.0)'],
  ['What it is', 'Tweets from accounts that Twitter identified as connected to the Internet Research Agency (IRA)'],
  ['Files', '13 CSV files, about 1 GB'],
]

const FIELDS = [
  ['tweet_id', 'post_id', 'Unique index; duplicates rejected'],
  ['content', 'text, clean_text', 'Cleaned text drives NLP and search'],
  ['publish_date', 'created_at', 'No time zone in the source; UTC assumed'],
  ['language', 'language', 'Language names mapped to ISO 639-1 codes'],
  ['region', 'location.country', 'Account-level country; no city'],
  ['author', 'user.username', ''],
  ['alt_external_id', 'user.user_id', 'external_author_id lost precision in the CSV'],
  ['followers, following, updates', 'user.*', 'Follower count also stored as reach'],
  ['account_category, account_type', 'user.*', 'Researcher-coded themes (RightTroll, LeftTroll, NewsFeed, ...)'],
  ['post_type, retweet', 'post_type, is_retweet', ''],
  ['(none)', 'hashtags, mentions, url_count, emojis', 'Extracted from the text during cleaning'],
]

const YEARS = [
  ['2012', '488'], ['2013', '199'], ['2014', '7,722'], ['2015', '821,443'],
  ['2016', '1,122,936'], ['2017', '984,720'], ['2018', '7,306'],
]

const QUALITY = [
  ['Duplicate tweet_id', '1,392', 'Rejected by the unique index'],
  ['Empty content', '1', 'Rejected'],
  ['Link only (fewer than four words)', '123,874', 'Kept, flagged link_only'],
  ['Mention stuffing (five or more mentions)', '104,415', 'Kept, flagged'],
  ['Hashtag stuffing (five or more hashtags)', '39,176', 'Kept, flagged'],
  ['No text left after cleaning', '32,125', 'Kept, flagged no_text_content'],
]

const code = (v) => <code className="rounded bg-surface-2 px-1 text-xs">{v}</code>

export default function AboutDataset() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="About the dataset"
        description="Where the posts come from, what each field means, how the data was cleaned and what it can and cannot tell you."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {FACTS.map((f) => <KpiCard key={f.label} label={f.label} value={f.value} hint={f.hint} />)}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Source">
          <dl className="space-y-2 text-sm">
            {SOURCE.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[110px_1fr] gap-3">
                <dt className="text-muted">{k}</dt><dd className="text-ink-2">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="What the data can and cannot tell you">
          <ul className="list-disc space-y-2 pl-5 text-sm text-ink-2">
            <li><strong className="text-ink">Not public opinion.</strong> Every account belongs to a coordinated influence operation, so results describe what those accounts posted.</li>
            <li><strong className="text-ink">Sentiment is predicted.</strong> The source has no sentiment labels; English posts are classified by a model trained on TweetEval (test macro-F1 0.58). Other languages are {code('not_analyzed')}.</li>
            <li><strong className="text-ink">Location is account-level</strong> and country only.</li>
            <li><strong className="text-ink">Time zone is assumed UTC</strong>; the source does not state one.</li>
          </ul>
        </Card>
      </div>

      <Card title="Engagement is synthetic" badges={<SyntheticBadge />}>
        <p className="text-sm text-ink-2">
          The source has no like, reply or retweet counts. {code('scripts/synthesize_engagement.py')} generates them from each
          author's real follower count and whether the post is a retweet, with a seed derived from the post id. They do not
          depend on sentiment, topic, hashtags or time, so differences in engagement between groups only reflect follower
          counts. Every value carries {code('engagement.synthetic: true')}. Uploaded datasets with real engagement columns are
          stored with {code('synthetic: false')} and never overwritten.
        </p>
      </Card>

      <Card title="Fields and how they are stored">
        <Table
          dense
          rowKey={(r) => r[0]}
          columns={[
            { key: 'src', label: 'Source column', render: (r) => code(r[0]) },
            { key: 'dst', label: 'Stored as', render: (r) => code(r[1]) },
            { key: 'note', label: 'Notes', render: (r) => r[2] },
          ]}
          rows={FIELDS}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Posts per year">
          <Table
            dense
            rowKey={(r) => r[0]}
            columns={[{ key: 'y', label: 'Year', render: (r) => r[0] }, { key: 'n', label: 'Posts', align: 'right', render: (r) => r[1] }]}
            rows={YEARS}
          />
          <div className="mt-3"><Note>Busiest day: 2016-10-06 with 18,634 posts. Collection gap from about 2017-10-23 to 2017-11-06.</Note></div>
        </Card>
        <Card title="Data quality found during ingestion">
          <Table
            dense
            rowKey={(r) => r[0]}
            columns={[
              { key: 'i', label: 'Issue', render: (r) => r[0] },
              { key: 'n', label: 'Posts', align: 'right', render: (r) => r[1] },
              { key: 'h', label: 'Handling', render: (r) => r[2] },
            ]}
            rows={QUALITY}
          />
          <div className="mt-3"><Note>Flagged posts are kept because spam-like behaviour is part of what the dataset documents. 44% of posts are retweets.</Note></div>
        </Card>
      </div>
    </div>
  )
}
