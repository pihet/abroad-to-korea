import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { authApi, ORIGINS, type AuthUser, type RegionRow } from './api'
import { originLabel, shortSido } from './regionLabel'
import './account.css'

// 계정 설정 (로그인한 사람): 프로필 사진 · 닉네임 · 여행 설정(내 취향 반영, 기본 출발지) · 로그인 수단 · 비밀번호 변경 · 로그아웃 · 회원 탈퇴

type Identity = { provider: 'email' | 'google' | 'kakao'; email: string | null }
type Prefs = { enabled: boolean; origin: string | null }  // origin: 도시 이름(서울) 또는 시군구 key(51_강릉시)
const PROVIDER = { email: '이메일', google: 'Google', kakao: '카카오' }

async function call<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
  const d = await r.json().catch(() => null)
  if (!r.ok) {
    const detail = d?.detail
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? (detail[0]?.msg ?? '').replace(/^Value error, /, '') || '입력값을 확인해 주세요.' : '요청에 실패했습니다.')
  }
  return d as T
}

export function AccountSettings({ user, rows, onUser, onClose, onOrigin }: {
  user: AuthUser; rows: RegionRow[]; onUser: (u: AuthUser | null) => void; onClose: () => void; onOrigin: (o: string | null) => void
}) {
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [avatar, setAvatar] = useState<string | null>(null)
  const [q, setQ] = useState('')  // 출발 시군구 찾기
  const fileRef = useRef<HTMLInputElement>(null)
  const [ids, setIds] = useState<Identity[]>([])
  const [nick, setNick] = useState<string | null>(null)   // null 이면 보기, 문자열이면 고치는 중
  const [pw, setPw] = useState({ current: '', next: '' })
  const [pwOpen, setPwOpen] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    call<Prefs & { avatar_url: string | null }>('/api/my/taste').then(d => { setPrefs({ enabled: d.enabled, origin: d.origin }); setAvatar(d.avatar_url) }).catch(() => setPrefs(null))
    call<{ identities: Identity[] }>('/api/auth/identities').then(d => setIds(d.identities)).catch(() => setIds([]))
  }, [])

  const run = async (fn: () => Promise<string | void>) => {
    setBusy(true); setMsg(null)
    try { const text = await fn(); if (text) setMsg({ ok: true, text }) }
    catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : '요청에 실패했습니다.' }) }
    finally { setBusy(false) }
  }
  const savePrefs = (next: Prefs) => run(async () => {
    await call('/api/my/settings', 'PUT', { personal: next.enabled, origin: next.origin })
    setPrefs(next); onOrigin(next.origin); setQ('')
  })
  const upload = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    if (f.size > 5 * 1024 * 1024) { setMsg({ ok: false, text: '5MB 이하 사진만 올릴 수 있어요.' }); return }
    run(async () => {
      const body = new FormData(); body.append('file', f)
      const r = await fetch('/api/my/avatar', { method: 'POST', body })
      const d = await r.json().catch(() => null)
      if (!r.ok) throw new Error(typeof d?.detail === 'string' ? d.detail : '사진을 올리지 못했어요.')
      setAvatar(d.avatar_url); return '프로필 사진을 바꿨어요.'
    })
  }
  const dropAvatar = () => run(async () => { await call('/api/my/avatar', 'DELETE'); setAvatar(null); return '프로필 사진을 지웠어요.' })
  const term = q.trim()
  const matches = term ? rows.filter(r => `${shortSido(r.sido)} ${r.name} ${r.sido}`.includes(term)).slice(0, 8) : []
  const isKey = !!prefs?.origin?.includes('_')
  const saveNick = (e: FormEvent) => { e.preventDefault(); run(async () => {
    onUser(await call<AuthUser>('/api/auth/me', 'PATCH', { nickname: nick })); setNick(null); return '닉네임을 바꿨어요.'
  }) }
  const savePw = (e: FormEvent) => { e.preventDefault(); run(async () => {
    const r = await call<{ message: string }>('/api/auth/password/change', 'POST', { current_password: pw.current, new_password: pw.next })
    setPw({ current: '', next: '' }); setPwOpen(false); return r.message
  }) }
  const unlink = (p: Identity['provider']) => run(async () => {
    await call(`/api/auth/identities/${p}`, 'DELETE'); setIds(ids.filter(i => i.provider !== p)); return `${PROVIDER[p]} 연결을 해제했어요.`
  })
  const logout = () => run(async () => { await authApi.logout(); onUser(null); onClose() })
  const leave = () => run(async () => {
    await call('/api/auth/me', 'DELETE')
    try { localStorage.removeItem('feed-saved') } catch { /* 저장소 없음 */ }
    onUser(null); onClose()
  })
  const hasEmail = ids.some(i => i.provider === 'email')

  return <div className="acs">
    <div className="account-profile">
      <button type="button" className="account-avatar acs-av" onClick={() => fileRef.current?.click()} disabled={busy} aria-label="프로필 사진 바꾸기">
        {avatar ? <img src={avatar} alt="" /> : user.nickname.slice(0, 1)}
      </button>
      <input ref={fileRef} type="file" accept="image/*" hidden onChange={upload} />
      <span className="acs-avlinks">
        <button type="button" className="acs-link" onClick={() => fileRef.current?.click()} disabled={busy}>사진 변경</button>
        {avatar && <button type="button" className="acs-link muted" onClick={dropAvatar} disabled={busy}>삭제</button>}
      </span>
      {nick === null ? <div>
        <h2 id="account-title">{user.nickname} <button type="button" className="acs-link" onClick={() => setNick(user.nickname)}>변경</button></h2>
        <p>{user.email}</p>
      </div> : <form className="acs-row" onSubmit={saveNick}>
        <input value={nick} onChange={e => setNick(e.target.value)} minLength={2} maxLength={40} aria-label="새 닉네임" autoFocus required />
        <button type="submit" disabled={busy}>저장</button>
        <button type="button" className="ghost" onClick={() => setNick(null)}>취소</button>
      </form>}
    </div>

    {msg && <p className={msg.ok ? 'acs-ok' : 'account-message'} role="status">{msg.text}</p>}

    <h3>여행 설정</h3>
    {prefs ? <>
      <div className="acs-item">
        <span>내 취향 반영<small>닮았어요·별로예요·저장을 사진으로 찾기 순서에 반영</small></span>
        <button type="button" role="switch" aria-checked={prefs.enabled} className="acs-switch" disabled={busy}
          onClick={() => savePrefs({ ...prefs, enabled: !prefs.enabled })}><i /></button>
      </div>
      <div className="acs-item col">
        <span>기본 출발지<small>{prefs.origin ? `사진으로 찾기 결과에 '${originLabel(prefs.origin, rows)}에서 ○km'로 보여요` : '고르면 사진으로 찾기 결과에 거리가 보여요'}</small></span>
        <span className="acs-chips">
          {[null, ...ORIGINS].map(o => <button key={o ?? 'none'} type="button" aria-pressed={prefs.origin === o} disabled={busy}
            onClick={() => savePrefs({ ...prefs, origin: o })}>{o ?? '없음'}</button>)}
          {isKey && <button type="button" aria-pressed="true">{originLabel(prefs.origin, rows)}</button>}
        </span>
        <input className="acs-search" value={q} onChange={e => setQ(e.target.value)} placeholder="다른 시군구 찾기 (예: 수원, 해운대)" aria-label="출발 시군구 찾기" />
        {term && <span className="acs-chips">
          {matches.length ? matches.map(r => <button key={r.key} type="button" disabled={busy} onClick={() => savePrefs({ ...prefs, origin: r.key })}>
            {shortSido(r.sido)} {r.name}</button>) : <small>'{term}'에 맞는 시군구가 없어요</small>}
        </span>}
      </div>
    </> : <p className="acs-sub">설정을 불러오지 못했어요.</p>}

    <h3>로그인 수단</h3>
    {ids.map(i => <div className="acs-item" key={i.provider}>
      <span>{PROVIDER[i.provider]}<small>{i.email ?? ''}</small></span>
      {ids.length > 1 && <button type="button" className="acs-link" disabled={busy} onClick={() => unlink(i.provider)}>연결 해제</button>}
    </div>)}
    {ids.length === 1 && <p className="acs-sub">로그인 수단이 하나뿐이라 해제할 수 없어요.</p>}

    {hasEmail && <>
      <h3>비밀번호</h3>
      {!pwOpen ? <button type="button" className="acs-link" onClick={() => setPwOpen(true)}>비밀번호 변경</button> : (
        <form className="account-form" onSubmit={savePw}>
          <label className="account-field"><span className="account-label">현재 비밀번호</span>
            <input type="password" value={pw.current} onChange={e => setPw({ ...pw, current: e.target.value })} placeholder="현재 비밀번호" autoComplete="current-password" required /></label>
          <label className="account-field"><span className="account-label">새 비밀번호</span>
            <input type="password" value={pw.next} onChange={e => setPw({ ...pw, next: e.target.value })} minLength={10} placeholder="새 비밀번호 (10자 이상)" autoComplete="new-password" required /></label>
          <button className="account-submit" type="submit" disabled={busy}>{busy ? '처리 중…' : '비밀번호 바꾸기'}</button>
        </form>
      )}
    </>}

    <button className="account-submit secondary" type="button" disabled={busy} onClick={logout}>로그아웃</button>
    <div className="acs-leave">
      {!leaving ? <button type="button" className="acs-link" onClick={() => setLeaving(true)}>회원 탈퇴</button> : <>
        <p>탈퇴하면 저장한 곳과 설정, 로그인 정보가 지워지고 되돌릴 수 없어요.</p>
        <button type="button" className="danger" disabled={busy} onClick={leave}>탈퇴하기</button>
        <button type="button" className="acs-link" onClick={() => setLeaving(false)}>취소</button>
      </>}
    </div>
  </div>
}
