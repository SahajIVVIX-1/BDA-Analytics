import { BookOpen, Boxes, Cpu, Database, Network, Trophy } from 'lucide-react'
import { Async, PageHeader, TabPanel, Tabs, useTab } from '../components/ui'
import { useApi } from '../hooks/useApi'
import Architecture from './bigdata/Architecture'
import ConceptsTab from './bigdata/ConceptsTab'
import GoldTab from './bigdata/GoldTab'
import LakeTab from './bigdata/LakeTab'
import ShardingTab from './bigdata/ShardingTab'
import SparkTab from './bigdata/SparkTab'

const TABS = [
  { id: 'architecture', label: 'Architecture', icon: Network },
  { id: 'spark', label: 'Spark processing', icon: Cpu },
  { id: 'lake', label: 'Data lake', icon: Database },
  { id: 'gold', label: 'Gold insights', icon: Trophy },
  { id: 'sharding', label: 'Sharding', icon: Boxes },
  { id: 'concepts', label: 'Course concepts', icon: BookOpen },
]

export default function BigDataLab() {
  const [tab, setTab] = useTab(TABS.map((t) => t.id), 'tab', ['view'])
  const res = useApi('/api/bigdata/results')
  const lake = useApi('/api/bigdata/lake', {}, { enabled: tab === 'lake' })
  const live = useApi('/api/bigdata/cluster', {}, { enabled: tab === 'sharding' })
  return (
    <>
      <PageHeader title="Big Data Lab"
        description="Distributed processing with Apache Spark, a bronze / silver / gold Parquet data lake and a sharded MongoDB cluster, measured on the full 2.9M-tweet dataset." />
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Big Data Lab sections" />
      <Async state={res} height={420}>
        {(d) => (
          <TabPanel id={tab}>
            {tab === 'architecture' && <Architecture r={d.results} />}
            {tab === 'spark' && <SparkTab r={d.results} />}
            {tab === 'lake' && <LakeTab r={d.results} lake={lake} />}
            {tab === 'gold' && <GoldTab r={d.results} />}
            {tab === 'sharding' && <ShardingTab r={d.results} live={live} />}
            {tab === 'concepts' && <ConceptsTab r={d.results} />}
          </TabPanel>
        )}
      </Async>
    </>
  )
}
