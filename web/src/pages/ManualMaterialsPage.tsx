import RawSourcesPage from './RawSourcesPage'

export default function ManualMaterialsPage() {
  return (
    <RawSourcesPage
      sourceKind="manual_source"
      title="新增材料"
      subtitle="查看用户手动录入的文章、公告、研报、观点和笔记。"
      emptyTitle="暂无新增材料"
      emptyDescription="点击“新增材料”保存手动录入的文章、公告、研报或笔记。"
    />
  )
}
