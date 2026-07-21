// input: hasUnsaved, saving, onSave, onStartBattle
// output: 底部固定 CTA bar — 保存备用 (ghost) + 开始演练 (primary gradient)
// owner: wanhua.gu
// pos: 表示层 - persona editor 底部 CTA (Story 2.7 AC)；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
import { Rocket, Save, PlusCircle } from 'lucide-react'
import { useI18n } from '../../i18n'
import { Button } from '../ui/button'

interface Props {
  hasUnsaved: boolean
  saving: boolean
  onSave: () => void
  onStartBattle: () => void
  onEnhance?: () => void
  showEnhance?: boolean
}

export default function FloatingCTA({
  hasUnsaved,
  saving,
  onSave,
  onStartBattle,
  onEnhance,
  showEnhance = true,
}: Props) {
  const { tr } = useI18n()

  return (
    <div className="cta">
      {showEnhance && onEnhance && (
        <Button className="btn-ghost" variant="secondary" onClick={onEnhance}>
          <PlusCircle size={14} />
          {tr('追加素材', 'Add Materials')}
        </Button>
      )}
      <Button
        className="btn-ghost"
        variant="secondary"
        onClick={onSave}
        disabled={!hasUnsaved || saving}
      >
        <Save size={14} />
        {saving ? tr('保存中…', 'Saving...') : hasUnsaved ? tr('保存备用', 'Save Draft') : tr('已保存', 'Saved')}
      </Button>
      <Button className="btn-go" variant="primary" onClick={onStartBattle}>
        <Rocket size={14} />
        {tr('开始演练', 'Start Practice')}
      </Button>
    </div>
  )
}
