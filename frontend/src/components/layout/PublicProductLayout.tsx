import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { useI18n } from '../../i18n'
import './PublicProductLayout.css'

interface PublicProductLayoutProps {
  children: ReactNode
}

export default function PublicProductLayout({ children }: PublicProductLayoutProps) {
  const { tr } = useI18n()
  const { requestSignIn } = useAuthContext()
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  const closeMenu = () => setIsMenuOpen(false)

  return (
    <div className="public-product-layout">
      <header className="public-product-header">
        <div className="public-product-header-inner">
          <Link className="public-product-brand" to="/" aria-label="TalkWise">
            <img src="/talkwise-icon.svg" alt="" aria-hidden="true" />
            <span>TalkWise</span>
          </Link>
          <button
            className="public-product-menu-toggle"
            type="button"
            aria-label={isMenuOpen ? tr('关闭导航', 'Close navigation') : tr('打开导航', 'Open navigation')}
            aria-expanded={isMenuOpen}
            onClick={() => setIsMenuOpen((value) => !value)}
          >
            {isMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <nav className={`public-product-nav${isMenuOpen ? ' public-product-nav--open' : ''}`} aria-label={tr('公共导航', 'Public navigation')}>
            <a href="#capabilities" onClick={closeMenu}>{tr('能力', 'Capabilities')}</a>
            <a href="#workflow" onClick={closeMenu}>{tr('训练流程', 'Training flow')}</a>
            <button
              className="public-product-login"
              type="button"
              onClick={() => {
                closeMenu()
                requestSignIn()
              }}
            >
              {tr('登录', 'Sign in')}
            </button>
          </nav>
        </div>
      </header>
      {children}
      <footer className="public-product-footer">
        <span>TalkWise</span>
        <span>{tr('沟通训练工作台', 'Communication training workspace')}</span>
      </footer>
    </div>
  )
}
