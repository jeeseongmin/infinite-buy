import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import DashboardPage from './pages/DashboardPage';
import TradesPage from './pages/TradesPage';
import SettingsPage from './pages/SettingsPage';
import StockDetailPage from './pages/StockDetailPage';
import MarketPage from './pages/MarketPage';
import GuidePage from './pages/GuidePage';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/guide" element={<GuidePage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/symbol/:ticker" element={<StockDetailPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
