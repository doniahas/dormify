import { routes } from './navigation';
import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from '../features/auth/AuthContext';

// Components
import Sidebar from './Sidebar';
import Header from './Header';

// Pages
import LoginPage from '../features/auth/LoginPage';
import HomePage from '../features/dashboard/HomePage';
import BuildingsPage from '../features/inventory/BuildingsPage';
import StudentsPage from '../features/students/StudentsPage';
import UploadPage from '../features/uploads/UploadPage';
import AssistedAllocationPage from '../features/allocation/AssistedAllocationPage';
import AllocationPage from '../features/allocation/AllocationPage';
import AllocationResultsPage from '../features/allocation/AllocationResultsPage';
import TransfersPage from '../features/transfers/TransfersPage';
import ReportsPage from '../features/reports/ReportsPage';
import UsersPage from '../features/staff/UsersPage';
import SettingsPage from '../features/settings/SettingsPage';
import MapPage from '../features/map/MapPage';
// At the top imports:
import AnalysisPage from '../features/analytics/AnalysisPage';
import WhatIfPage from '../features/what-if/WhatIfPage';

// Inside Routes:

// Main Layout with Sidebar + Header
function MainLayout({ language, onLanguageToggle, sidebarCollapsed, onSidebarToggle }) {
  return (
    <div
      className={`app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      dir={language === 'he' ? 'rtl' : 'ltr'}
    >
      <Sidebar collapsed={sidebarCollapsed} onToggle={onSidebarToggle} language={language} />
      <Header language={language} onLanguageToggle={onLanguageToggle} />
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}

// Auth gate for protected area
function ProtectedLayout({ language, onLanguageToggle, sidebarCollapsed, onSidebarToggle }) {
  const { user, loading } = useAuth();

  if (loading) return <div className="loading">Loading...</div>;
  if (!user) return <Navigate to={routes.login} replace />;

  return (
    <MainLayout
      language={language}
      onLanguageToggle={onLanguageToggle}
      sidebarCollapsed={sidebarCollapsed}
      onSidebarToggle={onSidebarToggle}
    />
  );
}

function AppContent() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, loading, language, toggleLanguage } = useAuth();

  const toggleSidebar = () => setSidebarCollapsed((c) => !c);

  return (
    <Routes>
      {/* Login */}
      <Route
  path={routes.login}
  element={
    loading ? (
      <div className="loading">Loading...</div>
    ) : user ? (
      <Navigate to={routes.dashboard} replace />
    ) : (
      <LoginPage
        language={language}
        onLanguageToggle={toggleLanguage}
      />
    )
  }
/>

      {/* Protected app shell */}
      <Route
        element={
          <ProtectedLayout
            language={language}
            onLanguageToggle={toggleLanguage}
            sidebarCollapsed={sidebarCollapsed}
            onSidebarToggle={toggleSidebar}
          />
        }
      >
        <Route path={routes.root} element={<Navigate to={routes.dashboard} replace />} />
        <Route path={routes.dashboard} element={<HomePage language={language} />} />
        {/* Old Data & Statistics page was merged into the unified /analysis page */}
        <Route path={routes.systemOverview} element={<Navigate to={routes.analytics} replace />} />
        <Route path={routes.map} element={<MapPage language={language} />} />
        <Route path={routes.inventory} element={<BuildingsPage />} />
        <Route path={routes.students} element={<StudentsPage />} />
        <Route path={routes.uploads} element={<UploadPage language={language} />} />
        <Route path={routes.assistedAllocation} element={<AssistedAllocationPage language={language} />} />
        {/* Old Accessibility / Special Requests page - preserved as an alias */}
        <Route path={routes.priority} element={<Navigate to={routes.assistedAllocation} replace />} />
        <Route path={routes.allocation} element={<AllocationPage />} />
          <Route path={routes.analytics} element={<AnalysisPage language={language} />} />
          <Route path={routes.whatIf} element={<WhatIfPage language={language} />} />
        <Route path={routes.allocationResults} element={<AllocationResultsPage />} />
        <Route path={routes.transfers} element={<TransfersPage />} />
        <Route path={routes.reports} element={<ReportsPage language={language} />} />
        <Route path={routes.staff} element={<UsersPage language={language} />} />
        <Route
          path={routes.settings}
          element={<SettingsPage language={language} onLanguageToggle={toggleLanguage} />}
        />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to={user ? routes.dashboard : routes.login} replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <AppContent />
      </Router>

      <style>{`
        /* The global reset and body rules live in shared/styles/global.css. */
        .app-layout {
          min-height: 100vh;
        }

        .main-content {
          margin-right: 260px;
          margin-top: 64px;
          min-height: calc(100vh - 64px);
          transition: margin 0.3s ease;
        }

        [dir="ltr"] .main-content {
          margin-right: 0;
          margin-left: 260px;
        }

        .app-layout.sidebar-collapsed .main-content {
          margin-right: 72px;
        }

        [dir="ltr"] .app-layout.sidebar-collapsed .main-content {
          margin-right: 0;
          margin-left: 72px;
        }

        .loading {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100vh;
          font-size: 18px;
          color: #64748b;
        }

        ::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }

        ::-webkit-scrollbar-track {
          background: #f1f5f9;
        }

        ::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>
    </AuthProvider>
  );
}

export default App;