import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { WorkpiecesContent } from "@/components/workpieces-content";

export default function WorkpiecesPage() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="pl-64">
        <Header title="工作区" description="管理您的运维工作空间" />
        <div className="p-6">
          <WorkpiecesContent />
        </div>
      </main>
    </div>
  );
}
