import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { DashboardContent } from "@/components/dashboard-content";

export default function DashboardPage() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="pl-64">
        <Header title="概览" description="AutoOpsHub 运维自动化平台" />
        <div className="p-6">
          <DashboardContent />
        </div>
      </main>
    </div>
  );
}
