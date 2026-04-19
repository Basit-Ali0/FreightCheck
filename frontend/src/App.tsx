import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/Toast";
import { AppHeader } from "@/components/layout/AppHeader";
import { ROUTER_FUTURE_FLAGS } from "@/lib/routerFuture";
import { SessionDetailPage } from "@/pages/SessionDetailPage";
import { SessionsPage } from "@/pages/SessionsPage";
import { UploadPage } from "@/pages/UploadPage";

export default function App() {
  return (
    <BrowserRouter future={ROUTER_FUTURE_FLAGS}>
      <ToastProvider>
        <div className="min-h-screen bg-slate-50 text-slate-900">
          <AppHeader />
          <main className="mx-auto max-w-7xl px-6 py-8">
            <Routes>
              <Route path="/" element={<UploadPage />} />
              <Route path="/sessions" element={<SessionsPage />} />
              <Route path="/sessions/:id" element={<SessionDetailPage />} />
            </Routes>
          </main>
        </div>
      </ToastProvider>
    </BrowserRouter>
  );
}
