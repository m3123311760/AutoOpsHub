import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { RunbooksContent } from "@/components/runbooks-content";
import { workpieceRouteParam } from "@/lib/routes";

interface RunbooksPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function RunbooksPage({ params }: RunbooksPageProps) {
  const { workpiece } = await params;
  const workpieceName = workpieceRouteParam(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={workpieceName} />
      <main className="pl-64">
        <Header title="运行手册" description={`${workpieceName} 的运行手册管理`} />
        <div className="p-6">
          <RunbooksContent workpiece={workpieceName} />
        </div>
      </main>
    </div>
  );
}
