import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DocumentReviewPage } from "./pages/DocumentReviewPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { FindingEvidencePage } from "./pages/FindingEvidencePage";
import { FindingsPage } from "./pages/FindingsPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<DocumentReviewPage />} />
        <Route path="/findings" element={<FindingsPage />} />
        <Route path="/findings/:findingId" element={<FindingEvidencePage />} />
        <Route path="/audit-log" element={<AuditLogPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
