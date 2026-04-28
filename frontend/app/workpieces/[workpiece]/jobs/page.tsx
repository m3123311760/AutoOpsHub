import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { JobsContent } from "@/components/jobs-content";
import { workpieceRouteParam } from "@/lib/routes";

interface JobsPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function JobsPage({ params }: JobsPageProps) {
  const { workpiece } = await params;
  const workpieceName = workpieceRouteParam(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={workpieceName} />
      <main className="pl-64">
        <Header title="定时作业" description={`${workpieceName} 的定时作业管理`} />
        <div className="p-6">
          <JobsContent workpiece={workpieceName} />
        </div>
      </main>
    </div>
  );
}
