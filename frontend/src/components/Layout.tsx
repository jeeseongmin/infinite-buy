import { NavLink, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/client';

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  return (
    <div className="app-layout">
      <header className="topbar">
        <div className="topbar-left">
          <h1 className="logo">Infinite Buy</h1>
          <span className="logo-sub">무한매수법 자동화</span>
        </div>
        <nav className="topbar-nav">
          <NavLink to="/" end>대시보드</NavLink>
          <NavLink to="/market">시장</NavLink>
          <NavLink to="/guide">가이드</NavLink>
          <NavLink to="/trades">거래내역</NavLink>
          <NavLink to="/settings">설정</NavLink>
        </nav>
        <div className="topbar-right">
          <span className={`status-dot ${health?.paused ? 'paused' : 'active'}`} />
          <span className="status-text">
            {health?.paused ? '일시정지' : '자동매매 중'}
          </span>
        </div>
      </header>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
