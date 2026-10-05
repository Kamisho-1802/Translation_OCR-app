/** 上部バー＋「三」ドロワーの共通レイアウト（DESIGN.md 第8.1章）。 */
import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

const NAV_ITEMS: { to: string; label: string }[] = [
  { to: '/', label: 'ホーム' },
  { to: '/detection', label: '文字検出' },
  { to: '/history', label: '翻訳履歴' },
  { to: '/translate', label: '翻訳ページ' },
];

export function Layout() {
  const [open, setOpen] = useState(false);

  return (
    <div className="app">
      <header className="topbar">
        <button
          type="button"
          className="hamburger"
          aria-label="メニューを開く"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          ☰
        </button>
        <span className="topbar-title">OCR翻訳アプリ</span>
      </header>

      {open && (
        <div
          className="drawer-backdrop"
          role="presentation"
          onClick={() => setOpen(false)}
        />
      )}

      <nav className={open ? 'drawer open' : 'drawer'} aria-label="メインメニュー">
        <div className="drawer-header">
          <span>メニュー</span>
          <button
            type="button"
            className="drawer-close"
            aria-label="メニューを閉じる"
            onClick={() => setOpen(false)}
          >
            ×
          </button>
        </div>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => (isActive ? 'drawer-link active' : 'drawer-link')}
            onClick={() => setOpen(false)}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
