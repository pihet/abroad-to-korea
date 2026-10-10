import { useState, type FormEvent } from 'react'
import { authApi, type AuthUser, type Origin } from './api'
import { AccountSettings } from './AccountSettings'

type AccountMode = 'login' | 'signup'

export function AccountModal({ user, onUser, onClose, onOrigin }: { user: AuthUser | null; onUser: (user: AuthUser | null) => void; onClose: () => void; onOrigin: (origin: Origin | null) => void }) {
  const [mode, setMode] = useState<AccountMode>('login')
  const [email, setEmail] = useState('')
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage(null)
    try {
      if (mode === 'login') {
        onUser(await authApi.login({ email, password })); onClose()
      } else if (mode === 'signup') {
        const result = await authApi.signup({ email, nickname, password })
        setMessage(result.message); setMode('login')
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : '요청에 실패했습니다.') }
    finally { setBusy(false) }
  }
  const social = async (provider: 'google' | 'kakao') => {
    setBusy(true); setMessage(null)
    try { window.location.href = (await authApi.oauthStart(provider)).authorization_url }
    catch (error) { setMessage(error instanceof Error ? error.message : '소셜 로그인을 시작하지 못했습니다.'); setBusy(false) }
  }
  const changeMode = (next: AccountMode) => { setMode(next); setMessage(null); setShowPassword(false) }

  const title = mode === 'signup' ? '회원가입' : '로그인'
  const subtitle = mode === 'signup' ? '여행지를 저장하고 나만의 목록을 만들어 보세요.'
    : null

  return <div className="account-layer" role="dialog" aria-modal="true" aria-labelledby="account-title">
    <section className="account-card">
      <button className="account-close" type="button" onClick={onClose} aria-label="닫기">×</button>
      {user ? <AccountSettings user={user} onUser={onUser} onClose={onClose} onOrigin={onOrigin} /> : <>
        <header className="account-head">
          <h2 id="account-title">{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </header>

        <form className="account-form" onSubmit={submit}>
          <label className="account-field">
            <span className="account-label">이메일</span>
            <input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="이메일을 입력하세요" autoComplete="email" required />
          </label>
          {mode === 'signup' && <label className="account-field">
            <span className="account-label">닉네임</span>
            <input value={nickname} onChange={event => setNickname(event.target.value)} minLength={2} maxLength={40} placeholder="닉네임을 입력하세요" autoComplete="nickname" required />
          </label>}
          <label className="account-field">
            <span className="account-label">비밀번호</span>
            <span className="account-password">
              <input type={showPassword ? 'text' : 'password'} value={password} onChange={event => setPassword(event.target.value)} minLength={mode === 'signup' ? 10 : undefined} placeholder={mode === 'signup' ? '비밀번호를 입력하세요 (10자 이상)' : '비밀번호를 입력하세요'} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required />
              <button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-5 9.5-5 9.5 5 9.5 5-3.5 5-9.5 5-9.5-5-9.5-5Z"/><circle cx="12" cy="12" r="2.5"/></svg>
              </button>
            </span>
          </label>
          <button className="account-submit" type="submit" disabled={busy}>{busy ? '처리 중…' : mode === 'signup' ? '이메일로 가입하기' : '로그인'}</button>
        </form>

        {message && <p className="account-message" role="status">{message}</p>}
        <footer className="account-foot">
          {mode === 'signup' ? <>이미 계정이 있으신가요? <button type="button" onClick={() => changeMode('login')}>로그인</button></>
            : <button type="button" onClick={() => changeMode('signup')}>회원가입</button>}
        </footer>
        <>
          <div className="account-divider"><span>간편 로그인</span></div>
          <div className="account-social" aria-label="간편 로그인">
            <button className="google" type="button" disabled={busy} onClick={() => social('google')} aria-label="Google로 계속하기">
              <svg className="account-provider-logo google" viewBox="0 0 18 18" aria-hidden="true">
                <path fill="#4285F4" d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.482h4.844a4.14 4.14 0 0 1-1.797 2.716v2.258h2.908c1.702-1.567 2.685-3.874 2.685-6.615Z"/>
                <path fill="#34A853" d="M9 18c2.43 0 4.468-.806 5.955-2.18l-2.908-2.258c-.806.54-1.836.86-3.047.86-2.344 0-4.328-1.585-5.037-3.714H.957v2.333A9 9 0 0 0 9 18Z"/>
                <path fill="#FBBC05" d="M3.963 10.708A5.42 5.42 0 0 1 3.682 9c0-.593.102-1.17.281-1.708V4.959H.957A9 9 0 0 0 0 9c0 1.452.347 2.827.957 4.041l3.006-2.333Z"/>
                <path fill="#EA4335" d="M9 3.578c1.322 0 2.508.455 3.442 1.346l2.578-2.578C13.464.896 11.426 0 9 0A9 9 0 0 0 .957 4.959l3.006 2.333C4.672 5.163 6.656 3.578 9 3.578Z"/>
              </svg>
            </button>
            <button className="kakao" type="button" disabled={busy} onClick={() => social('kakao')} aria-label="카카오로 계속하기">
              <svg className="account-provider-logo kakao" viewBox="0 0 28 26" aria-hidden="true">
                <path fill="#191919" d="M14 2C6.82 2 1 6.49 1 12.03c0 3.55 2.39 6.67 5.99 8.45l-1.53 5.61c-.14.5.43.89.87.6l6.69-4.43c.32.03.65.04.98.04 7.18 0 13-4.49 13-10.27S21.18 2 14 2Z"/>
              </svg>
            </button>
          </div>
        </>
      </>}
    </section>
  </div>
}
