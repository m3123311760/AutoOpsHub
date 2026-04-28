import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { TasksContent } from "@/components/tasks-content";
import { workpieceRouteParam } from "@/lib/routes";

interface TasksPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function TasksPage({ params }: TasksPageProps) {
  const { workpiece } = await params;
  const workpieceName = workpieceRouteParam(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={workpieceName} />
      <main className="pl-64">
        <Header title="任务" description={`${workpieceName} 的任务管理`} />
        <div className="p-6">
          <TasksContent workpiece={workpieceName} />
        </div>
      </main>
    </div>
  );
}
