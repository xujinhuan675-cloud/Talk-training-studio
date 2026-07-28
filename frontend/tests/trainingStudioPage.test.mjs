import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(relativePath), 'utf8')
}

test('TrainingStudioPage keeps training parameters collapsed by default', () => {
  const source = readSource('src/pages/TrainingStudioPage.tsx')
  const css = readSource('src/pages/TrainingStudioPage.css')
  const configStart = source.indexOf('{trainingConfigOpen && (')
  const configEnd = source.indexOf('</section>', configStart)
  const launcherIndex = source.indexOf('<TrainingStudioLauncher')
  const configPanel = source.slice(configStart, configEnd)

  assert.match(source, /trainingConfigOpen, setTrainingConfigOpen\] = useState\(false\)/)
  assert.match(source, /trainingConfigSummary = useMemo/)
  assert.match(source, /tr\('训练参数', 'Training parameters'\)/)
  assert.doesNotMatch(source, /高级训练配置|Advanced training configuration/)
  assert.match(source, /className="training-studio-config-toggle"/)
  assert.match(source, /aria-expanded=\{trainingConfigOpen\}/)
  assert.match(source, /aria-controls="training-studio-config-options"/)
  assert.notEqual(configStart, -1)
  assert.notEqual(configEnd, -1)
  assert.notEqual(launcherIndex, -1)
  assert.ok(configStart < launcherIndex)
  assert.match(configPanel, /<TrainingStudioLauncher value=\{config\}/)
  assert.match(css, /\.training-studio-config-panel/)
  assert.match(css, /\.training-studio-config-toggle\.ui-button/)
  assert.match(css, /\.training-studio-config-summary/)
})
