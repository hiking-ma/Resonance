import { useState } from 'react'
import {
  useConfirmLivePlan,
  useInitializeLivePortfolio,
  useLivePortfolio,
  useSkipLivePlan,
} from '../hooks/useLivePortfolio'
import type { LivePlanKind, LiveTradePlan } from '../api/livePortfolioTypes'

const KIND_LABEL: Record<LivePlanKind, string> = {
  BUY: '买入',
  TOPUP: '加仓',
  REDUCE: '减仓',
  SELL: '清仓',
}

const KIND_COLOR: Record<LivePlanKind, string> = {
  BUY: 'text-red-400',
  TOPUP: 'text-orange-400',
  REDUCE: 'text-sky-400',
  SELL: 'text-green-400',
}

function localDate(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function PlanRow({ plan }: { plan: LiveTradePlan }) {
  const confirm = useConfirmLivePlan()
  const skip = useSkipLivePlan()
  const future = plan.execution_date > localDate()
  const busy = confirm.isPending || skip.isPending
  const error = confirm.error ?? skip.error
  return (
    <div className="border border-gray-800 rounded-lg p-3 bg-gray-950/50">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-sm text-gray-200">
            <span className={`font-medium ${KIND_COLOR[plan.kind]}`}>{KIND_LABEL[plan.kind]}</span>
            <span className="ml-2">{plan.name}（{plan.code}）</span>
            <span className="ml-2 text-amber-400">目标 {plan.target_position_pct}%</span>
          </div>
          <div className="mt-1 text-xs text-gray-500">
            计划 #{plan.id} · 信号日 {plan.signal_date} · 执行日 {plan.execution_date}
          </div>
          <div className="mt-1 text-xs text-gray-400">{plan.reason}</div>
          {future && <div className="mt-1 text-xs text-amber-500">执行日到达后才能确认</div>}
          {error && <div className="mt-1 text-xs text-red-400">{error.message}</div>}
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            disabled={future || busy}
            onClick={() => confirm.mutate(plan.id)}
            className="px-3 py-1.5 rounded text-xs bg-emerald-700 text-white disabled:opacity-40"
          >
            已执行
          </button>
          <button
            disabled={busy}
            onClick={() => skip.mutate(plan.id)}
            className="px-3 py-1.5 rounded text-xs bg-gray-800 text-gray-300 disabled:opacity-40"
          >
            跳过
          </button>
        </div>
      </div>
    </div>
  )
}

function Setup() {
  const [date, setDate] = useState(localDate)
  const initialize = useInitializeLivePortfolio()
  return (
    <div className="max-w-xl bg-gray-900 border border-gray-800 rounded-lg p-5">
      <h3 className="text-white font-medium">初始化实际仓位账本</h3>
      <p className="mt-2 text-sm text-gray-400">
        初始仓位为 0%。系统只响应起始日之后的新策略信号，不追买历史模拟持仓。
      </p>
      <div className="mt-4 flex gap-2">
        <input
          type="date"
          value={date}
          onChange={event => setDate(event.target.value)}
          className="bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 [color-scheme:dark]"
        />
        <button
          disabled={initialize.isPending}
          onClick={() => initialize.mutate(date)}
          className="px-4 py-2 rounded bg-sky-700 text-sm text-white disabled:opacity-40"
        >
          确认以 0% 开始
        </button>
      </div>
      {initialize.error && <div className="mt-2 text-xs text-red-400">{initialize.error.message}</div>}
    </div>
  )
}

export default function LivePortfolio() {
  const query = useLivePortfolio()
  if (query.isLoading) return <div className="text-gray-500 text-center py-10">实际仓位加载中…</div>
  if (query.isError || !query.data) return <div className="text-red-400 text-center py-10">实际仓位加载失败</div>
  const data = query.data
  if (!data.config) return <Setup />

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-xl font-bold text-white">我的仓位</h2>
        <span className="text-xs text-gray-500">
          保守模式 · 起始日 {data.config.inception_date} · 仅手动确认后更新
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500">实际总仓位</div>
          <div className="mt-1 text-xl text-white font-medium">{data.total_position_pct}%</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500">持仓标的</div>
          <div className="mt-1 text-xl text-white font-medium">{data.positions.length}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500">待执行计划</div>
          <div className="mt-1 text-xl text-amber-400 font-medium">{data.pending_plans.length}</div>
        </div>
      </div>

      <section className="mb-5">
        <h3 className="text-sm font-medium text-gray-300 mb-2">当前实际仓位</h3>
        {data.positions.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-sm text-gray-500">当前空仓</div>
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-2">
            {data.positions.map(position => (
              <div key={position.code} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <div className="text-sm text-gray-200">{position.name}（{position.code}）</div>
                <div className="mt-1 text-lg text-amber-400">{position.position_pct}%</div>
                <div className="text-xs text-gray-600">持有自 {position.opened_date}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mb-5">
        <h3 className="text-sm font-medium text-gray-300 mb-2">待执行计划</h3>
        <div className="space-y-2">
          {data.pending_plans.length === 0
            ? <div className="text-sm text-gray-500">暂无待执行计划</div>
            : data.pending_plans.map(plan => <PlanRow key={plan.id} plan={plan} />)}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-medium text-gray-300 mb-2">实际操作历史</h3>
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-2">执行日</th><th className="text-left p-2">标的</th>
              <th className="text-left p-2">计划</th><th className="text-left p-2">结果</th>
            </tr></thead>
            <tbody>{data.history.map(plan => (
              <tr key={plan.id} className="border-b border-gray-800/60">
                <td className="p-2 text-gray-500">{plan.execution_date}</td>
                <td className="p-2 text-gray-300">{plan.code} {plan.name}</td>
                <td className={`p-2 ${KIND_COLOR[plan.kind]}`}>{KIND_LABEL[plan.kind]}至 {plan.target_position_pct}%</td>
                <td className="p-2 text-gray-400">{plan.status === 'confirmed' ? '已执行' : '已跳过'}</td>
              </tr>
            ))}</tbody>
          </table>
          {data.history.length === 0 && <div className="p-4 text-sm text-gray-500">暂无实际操作</div>}
        </div>
      </section>
    </div>
  )
}
