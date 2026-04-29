import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { WorkpieceDetailContent } from "@/components/workpiece-detail-content";
import { workpieceRouteParam } from "@/lib/routes";

interface WorkpiecePageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function WorkpieceDetailPage({ params }: WorkpiecePageProps) {
  const { workpiece } = await params;
  const workpieceName = workpieceRouteParam(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={workpieceName} />
      <main className="pl-64">
        <Header title={workpieceName} description="工作区详情" />
        <div className="p-6">
          <WorkpieceDetailContent workpiece={workpieceName} />
        </div>
      </main>
    </div>
  );
}
