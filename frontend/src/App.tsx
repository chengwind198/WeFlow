import { useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Dashboard } from '@/pages/Dashboard'
import { ArticleCreate } from '@/pages/ArticleCreate'
import { MdPublishCreate } from '@/pages/MdPublishCreate'
import { TaskDetail } from '@/pages/TaskDetail'
import { NewspicCreate } from '@/pages/NewspicCreate'
import { TaskList } from '@/pages/TaskList'
import { ReviewQueue } from '@/pages/ReviewQueue'
import { ReviewDetail } from '@/pages/ReviewDetail'
import { Themes } from '@/pages/Themes'
import { DraftList } from '@/pages/DraftList'
import { DraftEdit } from '@/pages/DraftEdit'
import { MaterialList } from '@/pages/MaterialList'
import { SyncList } from '@/pages/SyncList'
import { SyncCreate } from '@/pages/SyncCreate'
import { SyncDetail } from '@/pages/SyncDetail'
import { Settings } from '@/pages/Settings'
import { useConfigStore } from '@/stores/useConfigStore'
import { getConfig } from '@/lib/api'

export default function App() {
  const loaded = useConfigStore(s => s.loaded)
  const setConfig = useConfigStore(s => s.setConfig)

  // 应用启动时加载配置
  useEffect(() => {
    if (!loaded) {
      getConfig()
        .then(res => { if (res.data) setConfig(res.data) })
        .catch(() => {})
    }
  }, [loaded, setConfig])

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/articles/new" element={<ArticleCreate />} />
        <Route path="/tasks" element={<TaskList />} />
        <Route path="/tasks/:id" element={<TaskDetail />} />
        <Route path="/newspic/new" element={<NewspicCreate />} />
        <Route path="/newspic/:id" element={<TaskDetail />} />
        <Route path="/md/new" element={<MdPublishCreate />} />
        <Route path="/md/:id" element={<TaskDetail />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="/review/:id" element={<ReviewDetail />} />
        <Route path="/themes" element={<Themes />} />
        <Route path="/wechat/drafts" element={<DraftList />} />
        <Route path="/wechat/drafts/new" element={<DraftEdit />} />
        <Route path="/wechat/drafts/:mediaId" element={<DraftEdit />} />
        <Route path="/wechat/materials" element={<MaterialList />} />
        <Route path="/sync" element={<SyncList />} />
        <Route path="/sync/new" element={<SyncCreate />} />
        <Route path="/sync/:id" element={<SyncDetail />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </AppShell>
  )
}
