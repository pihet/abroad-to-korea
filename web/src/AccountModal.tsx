import { useState, type FormEvent } from 'react'
import { authApi, type AuthUser } from './api'

export function AccountModal({ user, onUser, onClose }: { user: AuthUser | null; onUser: (user: AuthUser | null) => void; onClose: () => void }) {
  const [mode, setMode] = useState<'login' | 'signup' | 'verify'>('login')
  const [email, setEmail] = useState('')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null)
    try {
      if (mode === 'login') {
        onUser(await authApi.login({ email, password })); onClose()
      } else if (mode === 'signup') {
        const result = await authApi.signup({ email, nickname, password })
        if (result.verification_token) setToken(result.verification_token)
        setMessage(result.message); setMode('verify')
      } else {
        await authApi.verifyEmail(token); setMessage('인증됐습니다. 로그인해 주세요.'); setMode('login')
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : '요청에 실패했습니다.') }
    finally { setBusy(false) }
  }
  const social = async (provider: 'google' | 'kakao') => {
    setBusy(true); setMessage(null)
    try { window.location.href = (await authApi.oauthStart(provider)).authorization_url }
    catch (error) { setMessage(error instanceof Error ? error.message : '소셜 로그인을 시작하지 못했습니다.'); setBusy(false) }
  }
  const logout = async () => { setBusy(true); try { await authApi.logout(); onUser(null); onClose() } finally { setBusy(false) } }

  return <div className="account-layer" role="dialog" aria-modal="true" aria-label="계정">
    <section className="account-card">
      <button className="account-close" type="button" onClick={onClose} aria-label="닫기">×</button>
      {user ? <>
        <h2>{user.nickname}</h2><p>{user.email}</p>
        <button className="ig-btn" type="button" disabled={busy} onClick={logout}>로그아웃</button>
      </> : <>
        <h2>{mode === 'signup' ? '회원가입' : mode === 'verify' ? '이메일 인증' : '로그인'}</h2>
        {mode !== 'verify' && <div className="account-social">
          <button type="button" disabled={busy} onClick={() => social('google')}>Google로 계속</button>
          <button type="button" disabled={busy} onClick={() => social('kakao')}>Kakao로 계속</button>
        </div>}
        <form onSubmit={submit}>
          {mode !== 'verify' && <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="이메일" required />}
          {mode === 'signup' && <input value={nickname} onChange={e => setNickname(e.target.value)} minLength={2} maxLength={40} placeholder="닉네임" required />}
          {mode !== 'verify' && <input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={mode === 'signup' ? 10 : undefined} placeholder="비밀번호" required />}
          {mode === 'verify' && <input value={token} onChange={e => setToken(e.target.value)} placeholder="메일의 인증 토큰" required />}
          <button className="ig-btn primary" type="submit" disabled={busy}>{busy ? '처리 중…' : mode === 'signup' ? '가입하기' : mode === 'verify' ? '인증하기' : '로그인'}</button>
        </form>
        {message && <p className="account-message">{message}</p>}
        <button className="account-switch" type="button" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setMessage(null) }}>
          {mode === 'signup' ? '이미 계정이 있어요' : mode === 'verify' ? '로그인으로 돌아가기' : '이메일로 회원가입'}
        </button>
      </>}
    </section>
  </div>
}
