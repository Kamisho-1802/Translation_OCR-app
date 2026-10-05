/** ルーティング（DESIGN.md 第8章）。 */
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { ConfigProvider } from './components/ConfigProvider';
import { Layout } from './components/Layout';
import { Detection } from './pages/Detection';
import { History } from './pages/History';
import { Home } from './pages/Home';
import { Translate } from './pages/Translate';

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/detection" element={<Detection />} />
            <Route path="/history" element={<History />} />
            <Route path="/translate" element={<Translate />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}
